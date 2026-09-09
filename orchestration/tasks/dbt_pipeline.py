"""
GridPulse Orchestration Task: dbt Medallion ELT & Contract Testing
Executes Bronze -> Silver -> Gold data transformations and verifies all 34
automated data contract assertions using dbt-duckdb.
"""

import os
import sys
import time
from typing import Dict, Any

# Add project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def run_dbt_elt_and_tests(run_seeds: bool = True) -> Dict[str, Any]:
    """
    Programmatically triggers the complete dbt Medallion ELT pipeline:
    dbt seed -> dbt run -> dbt test.

    Returns:
        Dict containing execution status, pass/fail counts, and latency duration.
    """
    start_time = time.time()
    from scripts.run_dbt import ensure_directories, invoke_dbt

    ensure_directories()
    results = {}
    overall_success = True

    try:
        # 1. dbt seed (if requested)
        if run_seeds:
            seed_ok = invoke_dbt(["seed"])
            results["seed_success"] = seed_ok
            if not seed_ok:
                overall_success = False

        # 2. dbt run (Bronze -> Silver -> Gold)
        run_ok = invoke_dbt(["run"])
        results["models_run_success"] = run_ok
        if not run_ok:
            overall_success = False

        # 3. dbt test (34 data contract tests)
        test_ok = invoke_dbt(["test"])
        results["tests_success"] = test_ok
        if not test_ok:
            overall_success = False

    except Exception as e:
        overall_success = False
        results["exception"] = str(e)

    duration_s = round(time.time() - start_time, 3)
    status = "SUCCESS" if overall_success else "FAILED"

    return {
        "task": "dbt_run_and_test_task",
        "status": status,
        "success": overall_success,
        "details": results,
        "duration_seconds": duration_s,
        "message": f"dbt Medallion pipeline completed with status {status} in {duration_s}s.",
    }


if __name__ == "__main__":
    res = run_dbt_elt_and_tests()
    print("[DBT TASK OUTPUT]")
    for k, v in res.items():
        print(f"  {k}: {v}")
