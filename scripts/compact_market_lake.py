"""
QuantPulse: High-Frequency Market Lakehouse Small-File Compactor (Phase 5)
=========================================================================
Coalesces fragmented streaming micro-batch Parquet parts into unified, sorted,
and deduplicated daily columnar files.

Solves the distributed streaming "small-file problem", eliminating OS file descriptor
exhaustion and maximizing columnar row group compression & dictionary encoding.
"""

import argparse
import glob
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

DEFAULT_LAKE_PATH = os.path.join(PROJECT_ROOT, "data", "lake", "raw_ticks")


def find_leaf_partition_dirs(lake_root: str) -> List[str]:
    """
    Finds all leaf directories that contain Parquet files within the lake partition hierarchy.
    """
    leaf_dirs = set()
    for root, _, files in os.walk(lake_root):
        if any(f.endswith(".parquet") for f in files):
            leaf_dirs.add(root)
    return sorted(list(leaf_dirs))


def compact_partition_directory(
    partition_dir: str,
    min_files: int = 2,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Compacts multiple Parquet files within a single partition directory
    into a single consolidated Snappy Parquet file.
    Deduplicates records and sorts chronologically.
    """
    all_files = [
        os.path.join(partition_dir, f)
        for f in os.listdir(partition_dir)
        if f.endswith(".parquet")
    ]
    # Filter files that need compaction (non-compacted or if forced)
    uncompacted_files = [f for f in all_files if not os.path.basename(f).startswith("compacted_")]

    files_to_merge = uncompacted_files if len(uncompacted_files) >= min_files else []
    if not files_to_merge and min_files == 1 and len(all_files) >= 1:
        # Forced compaction mode
        files_to_merge = all_files

    if not files_to_merge or len(files_to_merge) < min_files:
        return {
            "partition": partition_dir,
            "status": "SKIPPED",
            "files_before": len(all_files),
            "files_after": len(all_files),
            "bytes_before": sum(os.path.getsize(f) for f in all_files),
            "bytes_after": sum(os.path.getsize(f) for f in all_files),
            "rows_before": 0,
            "rows_after": 0,
        }

    bytes_before = sum(os.path.getsize(f) for f in files_to_merge)
    files_before = len(files_to_merge)

    if dry_run:
        return {
            "partition": partition_dir,
            "status": "DRY_RUN",
            "files_before": files_before,
            "files_after": 1,
            "bytes_before": bytes_before,
            "bytes_after": bytes_before,
            "rows_before": 0,
            "rows_after": 0,
        }

    # Execute compaction via DuckDB
    con = duckdb.connect()
    file_list_sql = ", ".join(f"'{f.replace(os.sep, '/')}'" for f in files_to_merge)
    ts_now = int(time.time())
    output_compacted_path = os.path.join(partition_dir, f"compacted_trades_{ts_now}.snappy.parquet")
    temp_compacted_path = os.path.join(partition_dir, f"temp_{ts_now}.parquet")

    try:
        # Deduplicate on symbol, timestamp, trade_id and sort chronologically
        query = f"""
            COPY (
                SELECT DISTINCT *
                FROM read_parquet([{file_list_sql}], union_by_name=true)
                ORDER BY timestamp ASC
            ) TO '{temp_compacted_path.replace(os.sep, '/')}' (FORMAT PARQUET, CODEC 'SNAPPY');
        """
        con.execute(query)

        # Count rows
        count_res = con.execute(f"SELECT COUNT(*) FROM read_parquet('{temp_compacted_path.replace(os.sep, '/')}')").fetchone()
        rows_after = int(count_res[0]) if count_res else 0
    finally:
        con.close()

    # Rename temp to final
    if os.path.exists(output_compacted_path):
        os.remove(output_compacted_path)
    os.rename(temp_compacted_path, output_compacted_path)

    # Safely remove old uncompacted files
    for f in files_to_merge:
        if os.path.abspath(f) != os.path.abspath(output_compacted_path):
            try:
                os.remove(f)
            except Exception as e:
                print(f"[WARN] Failed to delete compacted source file {f}: {e}")

    bytes_after = os.path.getsize(output_compacted_path)

    return {
        "partition": partition_dir,
        "status": "COMPACTED",
        "files_before": files_before,
        "files_after": 1,
        "bytes_before": bytes_before,
        "bytes_after": bytes_after,
        "rows_after": rows_after,
        "compacted_file": output_compacted_path,
    }


def run_compaction_pipeline(
    lake_root: str = DEFAULT_LAKE_PATH,
    asset_class: Optional[str] = None,
    symbol: Optional[str] = None,
    min_files: int = 2,
    dry_run: bool = False,
) -> List[Dict[str, Any]]:
    """
    Executes compaction across all eligible partitions in the lakehouse.
    """
    leaf_dirs = find_leaf_partition_dirs(lake_root)

    # Filter by asset class or symbol if requested
    filtered_dirs = []
    for d in leaf_dirs:
        norm_d = d.replace(os.sep, "/")
        if asset_class and f"asset_class={asset_class}" not in norm_d:
            continue
        if symbol:
            clean_sym = symbol.replace("/", "-")
            if f"symbol_clean={clean_sym}" not in norm_d:
                continue
        filtered_dirs.append(d)

    results: List[Dict[str, Any]] = []
    for d in filtered_dirs:
        res = compact_partition_directory(d, min_files=min_files, dry_run=dry_run)
        results.append(res)

    return results


def main():
    parser = argparse.ArgumentParser(description="QuantPulse Market Lakehouse Small-File Compactor")
    parser.add_argument("--lake-dir", default=DEFAULT_LAKE_PATH, help="Path to raw_ticks lake root")
    parser.add_argument("--asset-class", default=None, help="Optional asset class filter (e.g. crypto)")
    parser.add_argument("--symbol", default=None, help="Optional symbol filter (e.g. BTC/USDT)")
    parser.add_argument("--min-files", type=int, default=2, help="Minimum uncompacted files to trigger compaction")
    parser.add_argument("--dry-run", action="store_true", help="Report candidate partitions without modifying files")
    args = parser.parse_args()

    print("\n========================================================")
    print(" [QuantPulse] Market Lakehouse Small-File Compactor")
    print("========================================================")
    print(f"Lake Root:   {args.lake_dir}")
    print(f"Min Files:   {args.min_files}")
    print(f"Dry Run:     {args.dry_run}")
    print("--------------------------------------------------------\n")

    results = run_compaction_pipeline(
        lake_root=args.lake_dir,
        asset_class=args.asset_class,
        symbol=args.symbol,
        min_files=args.min_files,
        dry_run=args.dry_run,
    )

    compacted_count = sum(1 for r in results if r["status"] == "COMPACTED")
    skipped_count = sum(1 for r in results if r["status"] == "SKIPPED")
    dry_count = sum(1 for r in results if r["status"] == "DRY_RUN")

    total_bytes_saved = sum(max(0, r["bytes_before"] - r["bytes_after"]) for r in results if r["status"] == "COMPACTED")

    print(f"Partitions Inspected: {len(results)}")
    print(f"Compacted:            {compacted_count}")
    print(f"Skipped:              {skipped_count}")
    if dry_run:
        print(f"Dry Run Candidates:   {dry_count}")
    print(f"Storage Reclaimed:    {total_bytes_saved / 1024:.2f} KB\n")


if __name__ == "__main__":
    main()
