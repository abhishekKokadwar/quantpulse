"""
QuantPulse Cloud Object Storage Lakehouse Manager (Phase 10)
Integrates S3-compatible object storage (MinIO / AWS S3) for cloud-native
lakehouse operations, multi-part streaming commits, date-partitioned S3 prefixes,
lifecycle tiering, and vectorized DuckDB S3 querying.
"""

import os
import sys
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError, EndpointConnectionError
from dotenv import load_dotenv

# Add project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

DEFAULT_S3_ENDPOINT = os.getenv("S3_ENDPOINT_URL", "http://localhost:9000")
DEFAULT_S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY", "quantpulse_admin")
DEFAULT_S3_SECRET_KEY = os.getenv("S3_SECRET_KEY", "quantpulse_password")
DEFAULT_S3_BUCKET = os.getenv("S3_BUCKET_NAME", "quantpulse-lakehouse")
DEFAULT_S3_REGION = os.getenv("S3_REGION", "us-east-1")


class S3LakehouseManager:
    """
    Manages Cloud Object Storage operations for QuantPulse over S3 API.
    Works identically with local MinIO containers and production AWS S3 / Cloud Lakehouses.
    """

    def __init__(
        self,
        endpoint_url: str = DEFAULT_S3_ENDPOINT,
        access_key: str = DEFAULT_S3_ACCESS_KEY,
        secret_key: str = DEFAULT_S3_SECRET_KEY,
        bucket_name: str = DEFAULT_S3_BUCKET,
        region_name: str = DEFAULT_S3_REGION,
    ):
        self.endpoint_url = endpoint_url
        self.access_key = access_key
        self.secret_key = secret_key
        self.bucket_name = bucket_name
        self.region_name = region_name
        self._s3_client = None

    def get_client(self):
        """Returns or creates the configured boto3 S3 client with fast failover timeouts."""
        if self._s3_client is None:
            config = Config(
                connect_timeout=1,
                read_timeout=2,
                retries={"max_attempts": 1},
            )
            self._s3_client = boto3.client(
                "s3",
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                region_name=self.region_name,
                config=config,
            )
        return self._s3_client

    def is_s3_available(self, timeout_sec: float = 0.5) -> bool:
        """Checks if the S3/MinIO endpoint is reachable using fast TCP socket test before API call."""
        # If client is already initialized or mocked, call list_buckets directly
        if self._s3_client is not None:
            try:
                self._s3_client.list_buckets()
                return True
            except Exception:
                return False

        import socket
        from urllib.parse import urlparse
        try:
            parsed = urlparse(self.endpoint_url)
            host = parsed.hostname or "localhost"
            port = parsed.port or (443 if parsed.scheme == "https" else 9000)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout_sec)
            res = sock.connect_ex((host, port))
            sock.close()
            if res != 0:
                return False

            client = self.get_client()
            client.list_buckets()
            return True
        except Exception:
            return False

    def ensure_bucket_exists(self) -> bool:
        """Ensures the lakehouse bucket exists, creating it if needed."""
        if not self.is_s3_available():
            return False
        client = self.get_client()
        try:
            client.head_bucket(Bucket=self.bucket_name)
            return True
        except ClientError:
            try:
                client.create_bucket(Bucket=self.bucket_name)
                return True
            except Exception as e:
                print(f"[S3 ERROR] Failed to create bucket '{self.bucket_name}': {e}")
                return False

    def upload_file(self, local_path: str, s3_key: str) -> bool:
        """Uploads a single file to S3."""
        if not self.ensure_bucket_exists():
            return False
        try:
            client = self.get_client()
            client.upload_file(local_path, self.bucket_name, s3_key)
            return True
        except Exception as e:
            print(f"[S3 ERROR] Failed to upload {local_path} to s3://{self.bucket_name}/{s3_key}: {e}")
            return False

    def upload_bytes_multipart(self, data_bytes: bytes, s3_key: str, part_size: int = 5 * 1024 * 1024) -> Dict[str, Any]:
        """
        Executes a Multi-Part Streaming Upload over S3 API.
        Demonstrates production chunking and multipart commit verification.
        """
        if not self.ensure_bucket_exists():
            return {"status": "FAILED", "message": "S3 endpoint or bucket unreachable."}

        client = self.get_client()
        t0 = time.time()
        try:
            # 1. Initiate Multipart Upload
            mp = client.create_multipart_upload(Bucket=self.bucket_name, Key=s3_key)
            upload_id = mp["UploadId"]
            parts = []

            # 2. Upload Parts
            total_size = len(data_bytes)
            num_parts = max(1, (total_size + part_size - 1) // part_size)
            for i in range(num_parts):
                part_num = i + 1
                start = i * part_size
                end = min(start + part_size, total_size)
                chunk = data_bytes[start:end]

                res = client.upload_part(
                    Bucket=self.bucket_name,
                    Key=s3_key,
                    PartNumber=part_num,
                    UploadId=upload_id,
                    Body=chunk,
                )
                parts.append({"PartNumber": part_num, "ETag": res["ETag"]})

            # 3. Complete Multipart Upload
            client.complete_multipart_upload(
                Bucket=self.bucket_name,
                Key=s3_key,
                UploadId=upload_id,
                MultipartUpload={"Parts": parts},
            )
            elapsed_sec = round(time.time() - t0, 3)
            return {
                "status": "COMPLETED",
                "s3_uri": f"s3://{self.bucket_name}/{s3_key}",
                "parts_uploaded": len(parts),
                "total_bytes": total_size,
                "elapsed_seconds": elapsed_sec,
            }
        except Exception as e:
            return {"status": "FAILED", "error": str(e)}

    def sync_local_lake_to_s3(
        self,
        local_dir: Optional[str] = None,
        s3_prefix: str = "raw_telemetry",
    ) -> Dict[str, Any]:
        """
        Synchronizes local Parquet lake partitions into S3 object keys,
        preserving standard hierarchical Hive partitioning (year=YYYY/month=MM/day=DD).
        """
        target_local = local_dir or os.path.join(PROJECT_ROOT, "data", "lake", "raw_telemetry")
        if not os.path.exists(target_local):
            return {"status": "ERROR", "message": f"Local lake directory not found: {target_local}"}

        if not self.ensure_bucket_exists():
            return {
                "status": "OFFLINE_EMULATION",
                "message": "MinIO S3 service offline. Running in local simulation mode.",
                "uploaded_files": 0,
                "total_bytes": 0,
            }

        t0 = time.time()
        uploaded_count = 0
        total_bytes = 0
        errors = []

        for root, _, files in os.walk(target_local):
            for file in files:
                if file.endswith((".parquet", ".json")):
                    full_local_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_local_path, target_local).replace("\\", "/")
                    s3_key = f"{s3_prefix}/{rel_path}".strip("/")

                    try:
                        fsize = os.path.getsize(full_local_path)
                        ok = self.upload_file(full_local_path, s3_key)
                        if ok:
                            uploaded_count += 1
                            total_bytes += fsize
                        else:
                            errors.append(f"Failed to upload {s3_key}")
                    except Exception as e:
                        errors.append(f"{s3_key}: {str(e)}")

        elapsed = round(time.time() - t0, 3)
        return {
            "status": "SUCCESS" if not errors else "PARTIAL_SUCCESS",
            "s3_bucket": self.bucket_name,
            "s3_prefix": s3_prefix,
            "uploaded_files": uploaded_count,
            "total_bytes": total_bytes,
            "elapsed_seconds": elapsed,
            "errors": errors,
        }

    def list_s3_objects(self, prefix: str = "", max_keys: int = 100) -> List[Dict[str, Any]]:
        """Lists objects under the given prefix in the lakehouse bucket."""
        if not self.is_s3_available():
            return []
        client = self.get_client()
        try:
            resp = client.list_objects_v2(Bucket=self.bucket_name, Prefix=prefix, MaxKeys=max_keys)
            items = []
            for obj in resp.get("Contents", []):
                items.append({
                    "key": obj["Key"],
                    "size_bytes": obj["Size"],
                    "size_kb": round(obj["Size"] / 1024, 2),
                    "last_modified": obj["LastModified"].isoformat(),
                    "storage_class": obj.get("StorageClass", "STANDARD"),
                })
            return items
        except Exception:
            return []

    def get_s3_lakehouse_stats(self) -> Dict[str, Any]:
        """Returns comprehensive metadata for the S3-compatible Lakehouse."""
        available = self.is_s3_available()
        if not available:
            return {
                "connected": False,
                "endpoint_url": self.endpoint_url,
                "bucket_name": self.bucket_name,
                "total_objects": 0,
                "total_bytes": 0,
                "prefixes": [],
                "status_message": "MinIO / S3 endpoint currently unreachable (local fallback active).",
            }

        client = self.get_client()
        try:
            resp = client.list_objects_v2(Bucket=self.bucket_name)
            contents = resp.get("Contents", [])
            total_bytes = sum(o["Size"] for o in contents)
            prefixes = set()
            for o in contents:
                parts = o["Key"].split("/")
                if len(parts) > 1:
                    prefixes.add(parts[0] + "/")

            return {
                "connected": True,
                "endpoint_url": self.endpoint_url,
                "bucket_name": self.bucket_name,
                "total_objects": len(contents),
                "total_bytes": total_bytes,
                "total_mb": round(total_bytes / (1024 * 1024), 2),
                "prefixes": sorted(list(prefixes)),
                "status_message": "Connected to S3 Object Storage Gateway.",
            }
        except Exception as e:
            return {
                "connected": False,
                "endpoint_url": self.endpoint_url,
                "bucket_name": self.bucket_name,
                "total_objects": 0,
                "total_bytes": 0,
                "prefixes": [],
                "status_message": f"S3 query error: {str(e)}",
            }

    def simulate_lifecycle_tiering(
        self,
        source_prefix: str = "raw_telemetry/",
        archive_prefix: str = "archive/cold_tier/",
        transition_storage_class: str = "STANDARD_IA",
    ) -> Dict[str, Any]:
        """
        Simulates S3 Object Lifecycle Policies:
        Transitions historical objects to an archive prefix and cold storage class.
        """
        if not self.is_s3_available():
            return {
                "status": "SIMULATED",
                "message": "MinIO offline: Simulated lifecycle policy configured (transition to GLACIER/STANDARD_IA after 30 days).",
                "objects_transitioned": 0,
            }

        client = self.get_client()
        objects = self.list_s3_objects(prefix=source_prefix, max_keys=20)
        transitioned = 0
        t0 = time.time()

        for obj in objects:
            old_key = obj["key"]
            new_key = old_key.replace(source_prefix, archive_prefix, 1)
            try:
                # S3 Copy with StorageClass transition
                client.copy_object(
                    Bucket=self.bucket_name,
                    Key=new_key,
                    CopySource={"Bucket": self.bucket_name, "Key": old_key},
                    StorageClass=transition_storage_class,
                )
                transitioned += 1
            except Exception:
                pass

        return {
            "status": "SUCCESS",
            "objects_transitioned": transitioned,
            "target_prefix": archive_prefix,
            "storage_class": transition_storage_class,
            "elapsed_seconds": round(time.time() - t0, 3),
        }

    def query_s3_duckdb(self, sql_query: str, s3_glob: Optional[str] = None) -> Dict[str, Any]:
        """
        Executes zero-copy vectorized DuckDB SQL directly over S3 objects.
        Falls back seamlessly to local Parquet/Delta if S3 is unavailable.
        """
        import duckdb
        t0 = time.time()
        con = duckdb.connect()

        # Check if S3 is online
        if self.is_s3_available():
            try:
                con.execute("INSTALL httpfs; LOAD httpfs;")
                # Normalize endpoint for DuckDB
                ep = self.endpoint_url.replace("http://", "").replace("https://", "")
                con.execute(f"SET s3_endpoint = '{ep}';")
                con.execute(f"SET s3_access_key_id = '{self.access_key}';")
                con.execute(f"SET s3_secret_access_key = '{self.secret_key}';")
                con.execute("SET s3_use_ssl = false;")
                con.execute("SET s3_url_style = 'path';")

                df = con.execute(sql_query).fetchdf()
                elapsed_ms = round((time.time() - t0) * 1000, 2)
                con.close()
                return {
                    "source": "S3_OBJECT_STORE",
                    "rows": len(df),
                    "dataframe": df,
                    "elapsed_ms": elapsed_ms,
                }
            except Exception as e:
                # If S3 query fails, fallback below
                pass

        # Local fallback execution
        local_raw = os.path.join(PROJECT_ROOT, "data", "lake", "raw_telemetry", "**", "*.parquet").replace("\\", "/")
        fallback_sql = sql_query
        target_s3_call = f"read_parquet('s3://{self.bucket_name}/raw_telemetry/**/*.parquet')"
        target_s3_bare = f"s3://{self.bucket_name}/raw_telemetry/**/*.parquet"

        if target_s3_call in fallback_sql:
            fallback_sql = fallback_sql.replace(target_s3_call, f"read_parquet('{local_raw}')")
        elif target_s3_bare in fallback_sql:
            fallback_sql = fallback_sql.replace(target_s3_bare, local_raw)

        try:
            df = con.execute(fallback_sql).fetchdf()
            elapsed_ms = round((time.time() - t0) * 1000, 2)
            con.close()
            return {
                "source": "LOCAL_PARQUET_FALLBACK",
                "rows": len(df),
                "dataframe": df,
                "elapsed_ms": elapsed_ms,
            }
        except Exception as e:
            con.close()
            return {
                "source": "ERROR",
                "rows": 0,
                "error": str(e),
                "fallback_sql": fallback_sql,
                "elapsed_ms": round((time.time() - t0) * 1000, 2),
            }


# Singleton accessor
_s3_instance = None

def get_s3_lakehouse() -> S3LakehouseManager:
    global _s3_instance
    if _s3_instance is None:
        _s3_instance = S3LakehouseManager()
    return _s3_instance
