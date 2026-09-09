"""
Unit & Integration Tests for Phase 9: Workflow Orchestration & Pipeline Automation
Validates Airflow DAG structure, task execution, dependency graphs, SLA budgets, and run persistence.
"""

import os
import sys
import unittest
from datetime import datetime, timezone

# Add project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


class TestWorkflowOrchestration(unittest.TestCase):
    """Test suite covering GridPulse pipeline orchestration components."""

    def test_01_dag_structure_and_dependencies(self):
        """Verify Apache Airflow DAG topology, task IDs, and dependency connections."""
        from orchestration.dags.gridpulse_orchestrator_dag import (
            dag,
            sensor_freshness_task,
            lakehouse_compaction_task,
            dbt_run_and_test_task,
            model_retrain_task,
            sla_miss_alert_task,
        )

        self.assertEqual(dag.dag_id, "gridpulse_end_to_end_pipeline")
        self.assertEqual(dag.schedule_interval, "*/15 * * * *")
        self.assertIn("gridpulse", dag.tags)
        self.assertIn("lakehouse", dag.tags)

        # Check task IDs
        self.assertEqual(sensor_freshness_task.task_id, "sensor_freshness_task")
        self.assertEqual(lakehouse_compaction_task.task_id, "lakehouse_compaction_task")
        self.assertEqual(dbt_run_and_test_task.task_id, "dbt_run_and_test_task")
        self.assertEqual(model_retrain_task.task_id, "model_retrain_task")
        self.assertEqual(sla_miss_alert_task.task_id, "sla_miss_alert_task")

        # Check dependencies:
        # sensor_freshness >> lakehouse_compaction >> dbt
        self.assertIn(lakehouse_compaction_task, sensor_freshness_task.downstream_list)
        self.assertIn(sensor_freshness_task, lakehouse_compaction_task.upstream_list)

        self.assertIn(dbt_run_and_test_task, lakehouse_compaction_task.downstream_list)
        self.assertIn(lakehouse_compaction_task, dbt_run_and_test_task.upstream_list)

        # dbt >> model_retrain & dbt >> sla_miss_alert
        self.assertIn(model_retrain_task, dbt_run_and_test_task.downstream_list)
        self.assertIn(sla_miss_alert_task, dbt_run_and_test_task.downstream_list)

    def test_02_sensor_freshness_task(self):
        """Verify sensor freshness evaluation against lakehouse/database."""
        from orchestration.tasks.freshness import check_sensor_freshness

        res = check_sensor_freshness(max_lag_seconds=900.0)
        self.assertEqual(res["task"], "sensor_freshness_task")
        self.assertIn(res["status"], ["SUCCESS", "LAG_BREACH"])
        self.assertIn("duration_seconds", res)
        self.assertIn("freshness_ok", res)
        self.assertIsInstance(res["duration_seconds"], float)

    def test_03_lakehouse_compaction_task(self):
        """Verify lakehouse in-place compaction task execution."""
        from orchestration.tasks.compaction import run_lakehouse_compaction

        res = run_lakehouse_compaction(compact_delta=True, compact_raw_parquet=False)
        self.assertEqual(res["task"], "lakehouse_compaction_task")
        self.assertIn(res["status"], ["SUCCESS", "PARTIAL_SUCCESS"])
        self.assertIn("duration_seconds", res)
        self.assertIsInstance(res["duration_seconds"], float)

    def test_04_dbt_task(self):
        """Verify programmatic execution of dbt transformations and contract assertions."""
        from orchestration.tasks.dbt_pipeline import run_dbt_elt_and_tests

        res = run_dbt_elt_and_tests(run_seeds=False)
        self.assertEqual(res["task"], "dbt_run_and_test_task")
        self.assertIn("status", res)
        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "SUCCESS")
        self.assertTrue(res["details"].get("models_run_success", False))
        self.assertTrue(res["details"].get("tests_success", False))

    def test_05_model_retraining_task(self):
        """Verify automated ML demand forecaster retraining and regression KPIs."""
        from orchestration.tasks.model_retraining import retrain_forecaster_model

        res = retrain_forecaster_model()
        self.assertEqual(res["task"], "model_retrain_task")
        self.assertIn(res["status"], ["SUCCESS", "KPI_DEGRADATION"])
        self.assertIn("metrics", res)
        if res["status"] == "SUCCESS":
            self.assertTrue(res["promoted"])
            self.assertIn("MAE", res["metrics"])
            self.assertIn("RMSE", res["metrics"])
            self.assertLessEqual(res["metrics"]["MAE"], 120.0)

    def test_06_sla_monitoring_and_alerting(self):
        """Verify latency budget enforcement, failure detection, and incident alerting."""
        from orchestration.tasks.sla_monitor import evaluate_sla_and_alert

        # Scenario A: All compliant
        compliant_tasks = {
            "sensor_freshness_task": {"duration_seconds": 1.5, "status": "SUCCESS"},
            "lakehouse_compaction_task": {"duration_seconds": 3.0, "status": "SUCCESS"},
            "dbt_run_and_test_task": {"duration_seconds": 5.0, "status": "SUCCESS"},
            "model_retrain_task": {"duration_seconds": 8.0, "status": "SUCCESS"},
        }
        res_ok = evaluate_sla_and_alert(compliant_tasks, overall_duration=17.5)
        self.assertEqual(res_ok["task"], "sla_miss_alert_task")
        self.assertEqual(res_ok["status"], "SUCCESS")
        self.assertTrue(res_ok["compliant"])
        self.assertFalse(res_ok["alert_dispatched"])

        # Scenario B: Latency breach on dbt task (budget is 35s, simulated 50s)
        breached_tasks = {
            "sensor_freshness_task": {"duration_seconds": 1.5, "status": "SUCCESS"},
            "dbt_run_and_test_task": {"duration_seconds": 50.0, "status": "SUCCESS"},
        }
        res_breach = evaluate_sla_and_alert(breached_tasks, overall_duration=55.0)
        self.assertFalse(res_breach["compliant"])
        self.assertEqual(res_breach["status"], "INCIDENT_ALERT_TRIGGERED")
        self.assertTrue(res_breach["alert_dispatched"])
        self.assertGreater(len(res_breach["sla_breaches"]), 0)
        self.assertEqual(res_breach["sla_breaches"][0]["task"], "dbt_run_and_test_task")

    def test_07_pipeline_runner_history_tracking(self):
        """Verify pipeline runner history tracking and state persistence."""
        from orchestration.pipeline_runner import PipelineRunner
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            temp_history_file = tf.name

        try:
            runner = PipelineRunner(history_file=temp_history_file)
            initial_history = runner.get_history()
            self.assertEqual(len(initial_history), 0)

            # Record a dummy execution
            test_record = {
                "run_id": "test_run_001",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "SUCCESS",
                "duration_seconds": 12.34,
                "tasks": {},
                "sla_compliant": True,
            }
            runner._save_run_record(test_record)

            loaded_history = runner.get_history()
            self.assertEqual(len(loaded_history), 1)
            self.assertEqual(loaded_history[0]["run_id"], "test_run_001")
            self.assertEqual(loaded_history[0]["status"], "SUCCESS")
        finally:
            if os.path.exists(temp_history_file):
                try:
                    os.remove(temp_history_file)
                except Exception:
                    pass


if __name__ == "__main__":
    unittest.main()
