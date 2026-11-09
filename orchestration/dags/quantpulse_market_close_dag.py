"""
QuantPulse Market Close Orchestration DAG (Apache Airflow 2.x)
Orchestrates market tick freshness audits, lakehouse Delta OPTIMIZE compaction,
dbt Medallion ELT transformations with financial data contract assertions,
automated alpha model forecaster retraining, and SLA observability alerting.
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Dict, Any

# Ensure project root is available
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# -------------------------------------------------------------------------
# Apache Airflow Import & Mock Compatibility Layer
# Ensures the DAG can be inspected, tested, and validated both inside Airflow
# containers and within lightweight local developer environments.
# -------------------------------------------------------------------------
try:
    from airflow import DAG
    from airflow.operators.python import PythonOperator
    from airflow.operators.empty import EmptyOperator
    AIRFLOW_AVAILABLE = True
except ImportError:
    AIRFLOW_AVAILABLE = False

    class DummyTask:
        def __init__(self, task_id: str, python_callable=None, op_kwargs=None, retries=0, retry_delay=None, **kwargs):
            self.task_id = task_id
            self.python_callable = python_callable
            self.op_kwargs = op_kwargs or {}
            self.retries = retries
            self.retry_delay = retry_delay
            self.upstream_list = []
            self.downstream_list = []
            self.extra_kwargs = kwargs

        def __rshift__(self, other):
            if isinstance(other, (list, tuple)):
                for o in other:
                    self.__rshift__(o)
                return other
            if other not in self.downstream_list:
                self.downstream_list.append(other)
            if self not in other.upstream_list:
                other.upstream_list.append(self)
            return other

        def __lshift__(self, other):
            if isinstance(other, (list, tuple)):
                for o in other:
                    self.__lshift__(o)
                return other
            if other not in self.upstream_list:
                self.upstream_list.append(other)
            if self not in other.downstream_list:
                other.downstream_list.append(self)
            return other

    PythonOperator = DummyTask  # type: ignore
    EmptyOperator = DummyTask   # type: ignore

    class DAG:
        def __init__(self, dag_id: str, default_args=None, schedule=None, schedule_interval=None, start_date=None, catchup=False, max_active_runs=1, tags=None, on_failure_callback=None, sla_miss_callback=None, **kwargs):
            self.dag_id = dag_id
            self.default_args = default_args or {}
            self.schedule_interval = schedule or schedule_interval
            self.start_date = start_date
            self.catchup = catchup
            self.max_active_runs = max_active_runs
            self.tags = tags or []
            self.on_failure_callback = on_failure_callback
            self.sla_miss_callback = sla_miss_callback
            self.tasks = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass


# -------------------------------------------------------------------------
# Callback Functions for Incidents & SLA Misses
# -------------------------------------------------------------------------
def quantpulse_on_failure_callback(context: Dict[str, Any]):
    """Dispatches a critical incident alert card to the configured webhook."""
    try:
        from consumer.webhook_dispatcher import format_slack_card, get_default_webhook_url
        import requests
        task_id = context.get("task_instance", {}).get("task_id", "Unknown Task") if hasattr(context.get("task_instance"), "task_id") else "Pipeline Task"
        exception = str(context.get("exception", "Execution failure"))
        url = get_default_webhook_url()
        if url and url.startswith("http"):
            payload = format_slack_card(
                title=f"AIRFLOW DAG FAILURE: {task_id}",
                color="#ef4444",
                fields=[
                    {"name": "Task ID", "value": str(task_id), "short": True},
                    {"name": "Execution Time", "value": datetime.now(timezone.utc).isoformat(), "short": True},
                    {"name": "Error Details", "value": exception[:500], "short": False},
                ],
                summary=f"Airflow task '{task_id}' failed in DAG 'quantpulse_market_close_pipeline'.",
                username="Airflow Orchestrator",
                icon_emoji=":fire:",
            )
            requests.post(url, json=payload, timeout=5)
    except Exception:
        pass


def quantpulse_sla_miss_callback(dag, task_list, blocking_task_list, slas, blocking_tis):
    """Dispatches an SLA latency breach alert card to the configured webhook."""
    try:
        from consumer.webhook_dispatcher import format_slack_card, get_default_webhook_url
        import requests
        url = get_default_webhook_url()
        if url and url.startswith("http"):
            payload = format_slack_card(
                title="AIRFLOW SLA LATENCY BREACH",
                color="#f59e0b",
                fields=[
                    {"name": "DAG ID", "value": str(getattr(dag, "dag_id", "quantpulse_market_close_pipeline")), "short": True},
                    {"name": "Impacted Tasks", "value": str(task_list), "short": False},
                ],
                summary="One or more tasks breached their configured SLA latency budget.",
                username="Airflow Orchestrator",
                icon_emoji=":stopwatch:",
            )
            requests.post(url, json=payload, timeout=5)
    except Exception:
        pass


# -------------------------------------------------------------------------
# Default Arguments
# -------------------------------------------------------------------------
default_args = {
    "owner": "quantpulse-ops",
    "depends_on_past": False,
    "start_date": datetime(2026, 1, 1, tzinfo=timezone.utc),
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=1),
    "on_failure_callback": quantpulse_on_failure_callback,
    "sla": timedelta(seconds=120),
}


# -------------------------------------------------------------------------
# Python Callable Wrappers
# -------------------------------------------------------------------------
def task_wrapper_freshness(**kwargs) -> Dict[str, Any]:
    from orchestration.tasks.freshness import check_sensor_freshness
    res = check_sensor_freshness(max_lag_seconds=900.0)
    if not res.get("freshness_ok", False) and not res.get("is_historical_dataset", False):
        raise ValueError(f"Sensor freshness SLA breached: {res.get('message')}")
    return res


def task_wrapper_compaction(**kwargs) -> Dict[str, Any]:
    from orchestration.tasks.compaction import run_lakehouse_compaction
    res = run_lakehouse_compaction(compact_delta=True, compact_raw_parquet=True)
    if res.get("status") == "FAILED":
        raise RuntimeError(f"Lakehouse compaction failed: {res.get('errors')}")
    return res


def task_wrapper_dbt(**kwargs) -> Dict[str, Any]:
    from orchestration.tasks.dbt_pipeline import run_dbt_elt_and_tests
    res = run_dbt_elt_and_tests(run_seeds=True)
    if not res.get("success", False):
        raise RuntimeError(f"dbt Medallion ELT pipeline failed: {res.get('message')}")
    return res


def task_wrapper_retrain(**kwargs) -> Dict[str, Any]:
    from orchestration.tasks.model_retraining import retrain_forecaster_model
    res = retrain_forecaster_model()
    if res.get("status") == "FAILED":
        raise RuntimeError(f"Forecaster retraining failed: {res.get('error')}")
    return res


def task_wrapper_sla(**kwargs) -> Dict[str, Any]:
    from orchestration.tasks.sla_monitor import evaluate_sla_and_alert
    ti = kwargs.get("ti")
    task_results = {}
    if ti:
        for t_id in ["sensor_freshness_task", "lakehouse_compaction_task", "dbt_run_and_test_task", "model_retrain_task"]:
            try:
                task_results[t_id] = ti.xcom_pull(task_ids=t_id) or {}
            except Exception:
                task_results[t_id] = {}

    return evaluate_sla_and_alert(task_results=task_results, overall_duration=60.0)


# -------------------------------------------------------------------------
# Main DAG Definition
# -------------------------------------------------------------------------
dag = DAG(
    dag_id="quantpulse_market_close_pipeline",
    default_args=default_args,
    description="Automated QuantPulse Market Lakehouse Orchestrator",
    schedule_interval="*/15 * * * *",
    catchup=False,
    max_active_runs=1,
    tags=["quantpulse", "finance", "lakehouse", "dbt", "ml"],
    sla_miss_callback=quantpulse_sla_miss_callback,
)

sensor_freshness_task = PythonOperator(
    task_id="sensor_freshness_task",
    python_callable=task_wrapper_freshness,
    dag=dag,
)

lakehouse_compaction_task = PythonOperator(
    task_id="lakehouse_compaction_task",
    python_callable=task_wrapper_compaction,
    dag=dag,
)

dbt_run_and_test_task = PythonOperator(
    task_id="dbt_run_and_test_task",
    python_callable=task_wrapper_dbt,
    dag=dag,
)

model_retrain_task = PythonOperator(
    task_id="model_retrain_task",
    python_callable=task_wrapper_retrain,
    dag=dag,
)

sla_miss_alert_task = PythonOperator(
    task_id="sla_miss_alert_task",
    python_callable=task_wrapper_sla,
    dag=dag,
)

# -------------------------------------------------------------------------
# Define DAG Dependency Graph
# -------------------------------------------------------------------------
# Freshness -> Compaction -> dbt ELT & Tests -> Model Retraining & SLA Monitor
sensor_freshness_task >> lakehouse_compaction_task >> dbt_run_and_test_task
dbt_run_and_test_task >> model_retrain_task
dbt_run_and_test_task >> sla_miss_alert_task
model_retrain_task >> sla_miss_alert_task
