"""
GridPulse Orchestration Task: SLA Monitor & Failure Alert Dispatcher
Enforces task-level and pipeline-level latency budgets, identifies SLA breaches
or task failures, and dispatches structured incident webhook alerts to Slack/Teams/Discord.
"""

import os
import sys
import time
from typing import Dict, Any, List, Optional

# Add project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

DEFAULT_SLA_BUDGETS = {
    "sensor_freshness_task": 10.0,
    "lakehouse_compaction_task": 45.0,
    "dbt_run_and_test_task": 35.0,
    "model_retrain_task": 60.0,
    "overall_pipeline": 150.0,
}


def evaluate_sla_and_alert(
    task_results: Dict[str, Dict[str, Any]],
    overall_duration: float,
    sla_budgets: Optional[Dict[str, float]] = None,
    webhook_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Analyzes task results and durations against SLA budgets, triggering an incident
    webhook if latency limits are exceeded or any critical task fails.

    Returns:
        Dict containing SLA evaluation metrics and alert status.
    """
    budgets = {**DEFAULT_SLA_BUDGETS, **(sla_budgets or {})}
    sla_breaches = []
    failed_tasks = []

    for task_name, res in task_results.items():
        duration = res.get("duration_seconds", 0.0)
        budget = budgets.get(task_name, 60.0)
        status = res.get("status", "UNKNOWN")

        if duration > budget:
            sla_breaches.append({
                "task": task_name,
                "actual_seconds": duration,
                "budget_seconds": budget,
                "excess_seconds": round(duration - budget, 2),
            })

        if status not in ("SUCCESS", "SKIPPED"):
            failed_tasks.append({
                "task": task_name,
                "status": status,
                "message": res.get("message", "Task did not complete successfully."),
            })

    # Check overall pipeline SLA
    overall_budget = budgets.get("overall_pipeline", 150.0)
    if overall_duration > overall_budget:
        sla_breaches.append({
            "task": "overall_pipeline",
            "actual_seconds": overall_duration,
            "budget_seconds": overall_budget,
            "excess_seconds": round(overall_duration - overall_budget, 2),
        })

    has_issue = bool(sla_breaches or failed_tasks)
    alert_dispatched = False
    dispatch_details = {}

    if has_issue:
        # Build incident alert payload
        from consumer.webhook_dispatcher import format_slack_card, get_default_webhook_url, _record_dispatch_history
        import requests

        url = webhook_url or get_default_webhook_url()
        fields = [
            {"name": "Pipeline Run Duration", "value": f"{overall_duration:.2f}s (Budget: {overall_budget}s)", "short": True},
            {"name": "Status", "value": "SLA BREACH / TASK FAILURE" if failed_tasks else "SLA LATENCY BREACH", "short": True},
        ]

        if failed_tasks:
            fail_text = "\n".join([f"• *{f['task']}:* {f['status']} - {f['message']}" for f in failed_tasks])
            fields.append({"name": "Failed Tasks", "value": fail_text, "short": False})

        if sla_breaches:
            breach_text = "\n".join([f"• *{b['task']}:* {b['actual_seconds']}s (Budget: {b['budget_seconds']}s, +{b['excess_seconds']}s)" for b in sla_breaches])
            fields.append({"name": "SLA Latency Breaches", "value": breach_text, "short": False})

        title = "ORCHESTRATION PIPELINE INCIDENT" if failed_tasks else "PIPELINE SLA LATENCY BREACH"
        payload = format_slack_card(
            title=title,
            color="#ef4444" if failed_tasks else "#f59e0b",
            fields=fields,
            summary="The automated QuantPulse orchestration pipeline detected task failures or SLA latency breaches.",
            username="QuantPulse Orchestrator",
            icon_emoji=":rotating_light:" if failed_tasks else ":warning:",
        )

        # Dispatch
        dispatch_status = "SIMULATED_SUCCESS"
        if url and url.startswith("http"):
            try:
                resp = requests.post(url, json=payload, timeout=5)
                dispatch_status = "DELIVERED" if resp.status_code == 200 else f"HTTP_{resp.status_code}"
            except Exception as e:
                dispatch_status = f"ERROR_{str(e)[:30]}"

        record = {
            "timestamp": time.time(),
            "event_type": "ORCHESTRATION_SLA_ALERT",
            "title": title,
            "status": dispatch_status,
            "failed_tasks": len(failed_tasks),
            "sla_breaches": len(sla_breaches),
            "overall_duration": overall_duration,
        }
        _record_dispatch_history(record)
        alert_dispatched = True
        dispatch_details = {"status": dispatch_status, "record": record}

    status = "INCIDENT_ALERT_TRIGGERED" if has_issue else "SUCCESS"
    return {
        "task": "sla_miss_alert_task",
        "status": status,
        "compliant": not has_issue,
        "failed_tasks": failed_tasks,
        "sla_breaches": sla_breaches,
        "alert_dispatched": alert_dispatched,
        "dispatch_details": dispatch_details,
        "budgets": budgets,
        "duration_seconds": 0.05,
        "message": "All pipeline tasks compliant with SLA budgets." if not has_issue else f"Found {len(failed_tasks)} failed tasks and {len(sla_breaches)} SLA latency breaches.",
    }


if __name__ == "__main__":
    mock_results = {
        "sensor_freshness_task": {"duration_seconds": 2.1, "status": "SUCCESS"},
        "lakehouse_compaction_task": {"duration_seconds": 4.5, "status": "SUCCESS"},
        "dbt_run_and_test_task": {"duration_seconds": 8.0, "status": "SUCCESS"},
        "model_retrain_task": {"duration_seconds": 12.0, "status": "SUCCESS"},
    }
    res = evaluate_sla_and_alert(mock_results, overall_duration=26.6)
    print("[SLA MONITOR OUTPUT]")
    for k, v in res.items():
        print(f"  {k}: {v}")
