"""
GridPulse Orchestration Task: Lakehouse Compaction
Triggers periodic micro-batch Parquet file coalescing and native Delta Lake
OPTIMIZE in-place compaction to prevent the 'small file problem' and maximize scan throughput.
"""

import os
import sys
import time
from typing import Dict, Any

# Add project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def run_lakehouse_compaction(compact_delta: bool = True, compact_raw_parquet: bool = True) -> Dict[str, Any]:
    """
    Executes in-place compaction across both the raw Parquet lake and the Delta Lakehouse.

    Args:
        compact_delta: Whether to execute Delta Lake OPTIMIZE.
        compact_raw_parquet: Whether to coalesce raw Parquet micro-batches.

    Returns:
        Dict containing compaction metrics, files processed, and execution duration.
    """
    start_time = time.time()
    delta_result = {}
    parquet_result = {}
    errors = []

    # 1. Delta Lake In-Place Compaction (OPTIMIZE)
    if compact_delta:
        try:
            from analysis.delta_lakehouse import DeltaLakehouseManager
            mgr = DeltaLakehouseManager()
            # If table doesn't exist yet, initialize it
            if not mgr.is_initialized():
                mgr.initialize_from_parquet()
            delta_result = mgr.optimize_and_compact()
        except Exception as e:
            errors.append(f"Delta compaction error: {str(e)}")

    # 2. Raw Parquet Lake Compaction
    if compact_raw_parquet:
        try:
            from scripts.compact_lake import run_compaction, DEFAULT_LAKE_PATH
            if os.path.exists(DEFAULT_LAKE_PATH):
                parquet_result = run_compaction(DEFAULT_LAKE_PATH)
            else:
                parquet_result = {"status": "SKIPPED", "message": "Raw lake path does not exist."}
        except Exception as e:
            errors.append(f"Raw parquet compaction error: {str(e)}")

    duration_s = round(time.time() - start_time, 3)
    status = "SUCCESS" if not errors else "PARTIAL_SUCCESS" if (delta_result or parquet_result) else "FAILED"

    return {
        "task": "lakehouse_compaction_task",
        "status": status,
        "delta_compaction": delta_result,
        "raw_parquet_compaction": parquet_result,
        "errors": errors,
        "duration_seconds": duration_s,
        "message": f"Compaction finished with status {status} in {duration_s}s. Delta version: {delta_result.get('version', 'N/A')}.",
    }


if __name__ == "__main__":
    res = run_lakehouse_compaction()
    print("[COMPACTION TASK OUTPUT]")
    for k, v in res.items():
        print(f"  {k}: {v}")
