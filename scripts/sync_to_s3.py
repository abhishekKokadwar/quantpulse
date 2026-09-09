"""
GridPulse S3 Object Storage CLI Synchronization Utility (Phase 10)
Synchronizes local lakehouse partitions to MinIO/S3, inspects bucket objects,
and executes S3 lifecycle tiering.
"""

import argparse
import os
import sys
import time

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from analysis.s3_lakehouse import get_s3_lakehouse


def main():
    parser = argparse.ArgumentParser(description="GridPulse S3 Cloud Lakehouse Synchronizer")
    parser.add_argument("--status", action="store_true", help="Check S3/MinIO connection and bucket statistics")
    parser.add_argument("--sync-all", action="store_true", help="Synchronize local Parquet & Delta Lake partitions to S3")
    parser.add_argument("--list-objects", action="store_true", help="List objects stored in S3 bucket")
    parser.add_argument("--tier-archive", action="store_true", help="Simulate S3 lifecycle policy transitioning to cold tier")
    parser.add_argument("--query-s3", action="store_true", help="Run a sample vectorized DuckDB query over S3")
    parser.add_argument("--prefix", type=str, default="raw_telemetry", help="S3 prefix to filter or sync")
    args = parser.parse_args()

    s3 = get_s3_lakehouse()

    if args.status or len(sys.argv) == 1:
        stats = s3.get_s3_lakehouse_stats()
        print(f"\n{'='*70}")
        print(f"[STATUS] GridPulse S3 Cloud Object Storage Gateway")
        print(f"{'='*70}")
        print(f"  • Connected:        {stats['connected']}")
        print(f"  • S3 Endpoint:      {stats['endpoint_url']}")
        print(f"  • Target Bucket:    {stats['bucket_name']}")
        print(f"  • Total S3 Objects: {stats['total_objects']}")
        print(f"  • Total Footprint:  {stats.get('total_mb', 0)} MB ({stats['total_bytes']} bytes)")
        print(f"  • Active Prefixes:  {', '.join(stats.get('prefixes', [])) or 'None'}")
        print(f"  • Message:          {stats['status_message']}")
        print(f"{'='*70}\n")
        if not stats["connected"]:
            print("[NOTE] To start the local MinIO S3 cluster, run:")
            print("       docker-compose up -d minio minio-init\n")
        return

    if args.sync_all:
        print(f"\n[SYNC] Initiating S3 Synchronization for prefix '{args.prefix}'...")
        res = s3.sync_local_lake_to_s3(s3_prefix=args.prefix)
        print(f"  • Status:           {res.get('status')}")
        print(f"  • Files Uploaded:   {res.get('uploaded_files', 0)}")
        print(f"  • Data Transferred: {round(res.get('total_bytes', 0) / 1024, 1)} KB")
        print(f"  • Elapsed:          {res.get('elapsed_seconds', 0)}s")
        if res.get("errors"):
            print(f"  • Errors:           {res['errors'][:3]}")
        return

    if args.list_objects:
        objects = s3.list_s3_objects(prefix=args.prefix, max_keys=30)
        print(f"\n[OBJECTS] Listing S3 Objects (Prefix: '{args.prefix}'):")
        if not objects:
            print("  No objects found or S3 endpoint offline.")
        for o in objects:
            print(f"  • {o['key']} ({o['size_kb']} KB, {o['storage_class']}, Modified: {o['last_modified'][:19]})")
        print(f"  Total items: {len(objects)}\n")
        return

    if args.tier_archive:
        print(f"\n[LIFECYCLE] Executing S3 Object Lifecycle Policy simulation...")
        res = s3.simulate_lifecycle_tiering()
        print(f"  • Status:               {res.get('status')}")
        print(f"  • Objects Transitioned: {res.get('objects_transitioned', 0)}")
        print(f"  • Target Archive Tier:  {res.get('target_prefix')} ({res.get('storage_class')})")
        print(f"  • Elapsed:              {res.get('elapsed_seconds', 0)}s\n")
        return

    if args.query_s3:
        sql = f"SELECT count(*) as total_records, avg(power_kw) as avg_kw FROM read_parquet('s3://{s3.bucket_name}/raw_telemetry/**/*.parquet')"
        print(f"\n[QUERY] Executing DuckDB S3 SQL: {sql}")
        res = s3.query_s3_duckdb(sql)
        print(f"  • Execution Source: {res.get('source')}")
        print(f"  • Query Latency:    {res.get('elapsed_ms')} ms")
        if "dataframe" in res:
            print(f"  • Result:\n{res['dataframe']}\n")
        return


if __name__ == "__main__":
    main()
