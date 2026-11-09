"""
QuantPulse Standalone Pipeline Runner & Orchestration Engine (Phase 9)
Executes the full QuantPulse DAG locally without requiring external Airflow daemons,
capturing task execution times, status codes, SLA compliance, and persisting run history.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

# Add project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

RUNS_HISTORY_FILE = os.path.join(PROJECT_ROOT, "data", "orchestration", "runs.json")


class PipelineRunner:
    """
    Executes and tracks DAG tasks sequentially according to topological dependency order.
    """

    def __init__(self, history_file: str = RUNS_HISTORY_FILE):
        self.history_file = history_file
        os.makedirs(os.path.dirname(self.history_file), exist_ok=True)

    def get_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Returns recent pipeline execution records."""
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r") as f:
                    data = json.load(f)
                    return data[:limit]
            except Exception:
                return []
        return []

    def _save_run_record(self, record: Dict[str, Any]):
        """Appends run record to history file."""
        history = []
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r") as f:
                    history = json.load(f)
            except Exception:
                history = []
        history.insert(0, record)
        history = history[:100]  # retain 100 runs
        try:
            with open(self.history_file, "w") as f:
                json.dump(history, f, indent=2, default=str)
        except Exception as e:
            print(f"[RUNNER WARNING] Could not persist run history: {e}")

    def run_task(self, task_name: str) -> Dict[str, Any]:
        """Runs an individual task by name."""
        print(f"\n[RUNNER] Executing Task: {task_name}")
        start = time.time()

        if task_name in ("freshness", "sensor_freshness_task"):
            from orchestration.tasks.freshness import check_sensor_freshness
            res = check_sensor_freshness()
        elif task_name in ("compaction", "lakehouse_compaction_task"):
            from orchestration.tasks.compaction import run_lakehouse_compaction
            res = run_lakehouse_compaction()
        elif task_name in ("dbt", "dbt_run_and_test_task"):
            from orchestration.tasks.dbt_pipeline import run_dbt_elt_and_tests
            res = run_dbt_elt_and_tests()
        elif task_name in ("retrain", "model_retrain_task"):
            from orchestration.tasks.model_retraining import retrain_forecaster_model
            res = retrain_forecaster_model()
        elif task_name in ("sla", "sla_miss_alert_task"):
            from orchestration.tasks.sla_monitor import evaluate_sla_and_alert
            # Evaluate using standard mock/baseline
            res = evaluate_sla_and_alert({}, overall_duration=0.0)
        else:
            raise ValueError(f"Unknown task name: {task_name}")

        dur = round(time.time() - start, 3)
        res["runner_duration"] = dur
        print(f"[RUNNER] Task '{task_name}' finished in {dur}s -> Status: {res.get('status')}")
        return res

    def run_pipeline(
        self,
        skip_dbt_seed: bool = False,
        allow_retrain: bool = True,
        webhook_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes the end-to-end QuantPulse orchestration DAG:
        1. sensor_freshness_task
        2. lakehouse_compaction_task
        3. dbt_run_and_test_task
        4. model_retrain_task
        5. sla_miss_alert_task
        """
        pipeline_start = time.time()
        run_id = f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        print(f"\n{'='*70}")
        print(f"[START] [QUANTPULSE PIPELINE RUNNER] Starting Run ID: {run_id}")
        print(f"{'='*70}")

        task_results: Dict[str, Dict[str, Any]] = {}
        pipeline_failed = False

        # --- Task 1: Sensor Freshness ---
        print("\n--- [Step 1/5] Checking Telemetry Freshness ---")
        try:
            from orchestration.tasks.freshness import check_sensor_freshness
            t1 = check_sensor_freshness()
            task_results["sensor_freshness_task"] = t1
            print(f"  Status: {t1.get('status')} | Lag: {t1.get('lag_seconds')}s | Source: {t1.get('source')}")
        except Exception as e:
            task_results["sensor_freshness_task"] = {"status": "FAILED", "duration_seconds": 0.0, "message": str(e)}
            pipeline_failed = True

        # --- Task 2: Lakehouse Compaction ---
        print("\n--- [Step 2/5] Lakehouse In-Place Compaction ---")
        try:
            from orchestration.tasks.compaction import run_lakehouse_compaction
            t2 = run_lakehouse_compaction()
            task_results["lakehouse_compaction_task"] = t2
            print(f"  Status: {t2.get('status')} | Duration: {t2.get('duration_seconds')}s")
        except Exception as e:
            task_results["lakehouse_compaction_task"] = {"status": "FAILED", "duration_seconds": 0.0, "message": str(e)}

        # --- Task 3: dbt Medallion ELT & Contract Testing ---
        print("\n--- [Step 3/5] Executing dbt Medallion ELT & Data Contracts ---")
        try:
            from orchestration.tasks.dbt_pipeline import run_dbt_elt_and_tests
            t3 = run_dbt_elt_and_tests(run_seeds=not skip_dbt_seed)
            task_results["dbt_run_and_test_task"] = t3
            print(f"  Status: {t3.get('status')} | Duration: {t3.get('duration_seconds')}s")
            if not t3.get("success", False):
                pipeline_failed = True
        except Exception as e:
            task_results["dbt_run_and_test_task"] = {"status": "FAILED", "duration_seconds": 0.0, "message": str(e)}
            pipeline_failed = True

        # --- Task 4: ML Forecaster Retraining ---
        print("\n--- [Step 4/5] Retraining 24h AI Forecaster ---")
        if allow_retrain and not pipeline_failed:
            try:
                from orchestration.tasks.model_retraining import retrain_forecaster_model
                t4 = retrain_forecaster_model()
                task_results["model_retrain_task"] = t4
                print(f"  Status: {t4.get('status')} | Model: {t4.get('model_name')} | Metrics: {t4.get('metrics')}")
            except Exception as e:
                task_results["model_retrain_task"] = {"status": "FAILED", "duration_seconds": 0.0, "message": str(e)}
        else:
            task_results["model_retrain_task"] = {
                "status": "SKIPPED",
                "duration_seconds": 0.0,
                "message": "Skipped due to upstream pipeline failure or config.",
            }
            print("  Status: SKIPPED")

        # --- Task 5: SLA Monitoring & Alert Dispatch ---
        overall_duration = round(time.time() - pipeline_start, 3)
        print("\n--- [Step 5/5] SLA Latency & Quality Monitoring ---")
        try:
            from orchestration.tasks.sla_monitor import evaluate_sla_and_alert
            t5 = evaluate_sla_and_alert(
                task_results=task_results,
                overall_duration=overall_duration,
                webhook_url=webhook_url,
            )
            task_results["sla_miss_alert_task"] = t5
            print(f"  Compliance: {'COMPLIANT' if t5.get('compliant') else 'BREACH/FAILURE'} | Duration: {overall_duration}s")
        except Exception as e:
            task_results["sla_miss_alert_task"] = {"status": "FAILED", "duration_seconds": 0.0, "message": str(e)}

        overall_status = "SUCCESS" if not pipeline_failed and all(
            r.get("status") in ("SUCCESS", "SKIPPED") for r in task_results.values()
        ) else "FAILED"

        record = {
            "run_id": run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": overall_status,
            "duration_seconds": overall_duration,
            "tasks": task_results,
            "sla_compliant": task_results.get("sla_miss_alert_task", {}).get("compliant", False),
        }

        self._save_run_record(record)

        print(f"\n{'='*70}")
        print(f"[DONE] [QUANTPULSE PIPELINE COMPLETED] Status: {overall_status} in {overall_duration}s")
        print(f"{'='*70}\n")
        return record


def main():
    parser = argparse.ArgumentParser(description="QuantPulse Standalone Pipeline Runner")
    parser.add_argument("--run-all", action="store_true", help="Execute complete end-to-end pipeline")
    parser.add_argument("--task", type=str, choices=["freshness", "compaction", "dbt", "retrain", "sla"], help="Run individual task")
    parser.add_argument("--status", action="store_true", help="View recent pipeline run status")
    parser.add_argument("--limit", type=int, default=5, help="Number of historical runs to display")
    args = parser.parse_args()

    runner = PipelineRunner()

    if args.status:
        history = runner.get_history(limit=args.limit)
        if not history:
            print("[STATUS] No prior pipeline runs found.")
        else:
            print(f"\nRecent {len(history)} Pipeline Runs:")
            for h in history:
                print(f"  • {h['run_id']} | Status: {h['status']} | Duration: {h['duration_seconds']}s | SLA Compliant: {h['sla_compliant']}")
        return

    if args.task:
        runner.run_task(args.task)
        return

    if args.run_all or len(sys.argv) == 1:
        runner.run_pipeline()


if __name__ == "__main__":
    main()
