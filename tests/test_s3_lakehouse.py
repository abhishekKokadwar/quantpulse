"""
Unit & Integration Tests for Phase 10: Cloud Object Storage Emulation with MinIO (S3 API)
Validates S3 configuration, multi-part uploads, bucket metadata, lifecycle tiering,
and DuckDB S3 query execution with graceful offline fallback.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Add project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from analysis.s3_lakehouse import S3LakehouseManager


class TestS3Lakehouse(unittest.TestCase):
    """Test suite covering S3 Cloud Lakehouse operations and emulation."""

    def setUp(self):
        self.manager = S3LakehouseManager(
            endpoint_url="http://localhost:9000",
            access_key="test_access_key",
            secret_key="test_secret_key",
            bucket_name="gridpulse-test-lakehouse",
            region_name="us-east-1",
        )

    def test_01_s3_configuration(self):
        """Verify S3 client parameter initialization and configuration."""
        self.assertEqual(self.manager.endpoint_url, "http://localhost:9000")
        self.assertEqual(self.manager.bucket_name, "gridpulse-test-lakehouse")
        self.assertEqual(self.manager.access_key, "test_access_key")
        self.assertEqual(self.manager.secret_key, "test_secret_key")
        self.assertIsNotNone(self.manager.get_client())

    def test_02_graceful_offline_handling(self):
        """Verify is_s3_available handles unreachable endpoints gracefully without raising exceptions."""
        # Point to unreachable port to test timeout/offline behavior
        offline_mgr = S3LakehouseManager(endpoint_url="http://127.0.0.1:59999")
        self.assertFalse(offline_mgr.is_s3_available(timeout_sec=0.5))

    def test_03_stats_dictionary_format(self):
        """Verify get_s3_lakehouse_stats returns standard dictionary format regardless of connection."""
        stats = self.manager.get_s3_lakehouse_stats()
        self.assertIn("connected", stats)
        self.assertIn("endpoint_url", stats)
        self.assertIn("bucket_name", stats)
        self.assertIn("total_objects", stats)
        self.assertIn("status_message", stats)
        self.assertIsInstance(stats["connected"], bool)

    def test_04_multipart_upload_structure(self):
        """Verify multipart upload payload and return contract."""
        dummy_data = b"GridPulse Telemetry Record Partition Micro-Batch" * 100
        # If MinIO is offline, test that it returns failed status cleanly
        res = self.manager.upload_bytes_multipart(dummy_data, s3_key="test_raw.parquet")
        self.assertIn("status", res)
        self.assertIn(res["status"], ["COMPLETED", "FAILED"])

    def test_05_lifecycle_tiering_simulation(self):
        """Verify lifecycle tiering simulation returns expected structure."""
        res = self.manager.simulate_lifecycle_tiering()
        self.assertIn("status", res)
        self.assertIn("objects_transitioned", res)
        self.assertIn(res["status"], ["SUCCESS", "SIMULATED"])

    def test_06_duckdb_s3_query_with_local_fallback(self):
        """Verify vectorized DuckDB query succeeds against either S3 or local Parquet fallback."""
        sql = f"SELECT count(*) as total_records FROM read_parquet('s3://{self.manager.bucket_name}/raw_telemetry/**/*.parquet')"
        res = self.manager.query_s3_duckdb(sql)
        self.assertIn("source", res)
        self.assertIn(res["source"], ["S3_OBJECT_STORE", "LOCAL_PARQUET_FALLBACK"])
        self.assertGreater(res["rows"], 0)
        self.assertIn("elapsed_ms", res)
        self.assertIsInstance(res["elapsed_ms"], float)

    def test_07_mocked_s3_operations(self):
        """Verify full S3 lifecycle using mocked boto3 client."""
        mock_client = MagicMock()
        mock_client.list_buckets.return_value = {"Buckets": [{"Name": "gridpulse-test-lakehouse"}]}
        mock_client.head_bucket.return_value = {}
        mock_client.create_multipart_upload.return_value = {"UploadId": "test_upload_123"}
        mock_client.upload_part.return_value = {"ETag": '"etag123"'}
        mock_client.complete_multipart_upload.return_value = {"Location": "s3://gridpulse-test-lakehouse/test.parquet"}
        mock_client.list_objects_v2.return_value = {
            "Contents": [
                {
                    "Key": "raw_telemetry/year=2026/month=03/day=09/part-0.parquet",
                    "Size": 102400,
                    "LastModified": MagicMock(isoformat=lambda: "2026-03-09T10:00:00Z"),
                    "StorageClass": "STANDARD",
                }
            ]
        }

        self.manager._s3_client = mock_client
        try:
            self.assertTrue(self.manager.is_s3_available())
            self.assertTrue(self.manager.ensure_bucket_exists())

            # Test multipart upload
            res_mp = self.manager.upload_bytes_multipart(b"test data payload", s3_key="test.parquet")
            self.assertEqual(res_mp["status"], "COMPLETED")
            self.assertEqual(res_mp["parts_uploaded"], 1)

            # Test object listing
            objects = self.manager.list_s3_objects()
            self.assertEqual(len(objects), 1)
            self.assertEqual(objects[0]["key"], "raw_telemetry/year=2026/month=03/day=09/part-0.parquet")
            self.assertEqual(objects[0]["size_kb"], 100.0)

            # Test lakehouse stats
            stats = self.manager.get_s3_lakehouse_stats()
            self.assertTrue(stats["connected"])
            self.assertEqual(stats["total_objects"], 1)
            self.assertIn("raw_telemetry/", stats["prefixes"])
        finally:
            self.manager._s3_client = None


if __name__ == "__main__":
    unittest.main()
