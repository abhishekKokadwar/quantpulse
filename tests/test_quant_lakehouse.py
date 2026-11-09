"""
QuantPulse: Phase 5 Columnar Lakehouse & DuckDB Engine Test Suite
=================================================================
Validates:
1. Columnar lake metadata extraction and partition discovery
2. Vectorized DuckDB OHLCV aggregation for arbitrary timeframes (100ms to 1d)
3. Kyle's Lambda (Price Impact) and Amihud Illiquidity factor metrics
4. Cross-sectional return correlation matrix invariants (symmetry, diagonal=1.0)
5. Small-file compactor coalescing and deduplication
6. Sub-15ms vectorized query execution performance gate
"""

from datetime import datetime, timedelta, timezone
import os
import shutil
import sys
import tempfile
import time
import unittest

import duckdb
import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from analysis.quant_lakehouse import QuantLakehouseManager, sanitize_symbol
from scripts.compact_market_lake import compact_partition_directory, run_compaction_pipeline
from simulator.tick_lake_exporter import TickLakeExporter


class TestQuantLakehouseEngine(unittest.TestCase):
    """Verifies DuckDB vectorized query performance, OHLCV accuracy, and microstructure factors."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp()
        cls.lake_dir = os.path.join(cls.temp_dir, "raw_ticks")
        cls.exporter = TickLakeExporter(lake_root=cls.lake_dir)
        cls.manager = QuantLakehouseManager(lake_root=cls.lake_dir)

        # Seed synthetic ticks across 3 instruments: BTC/USDT, ETH/USDT, NVDA
        base_time = datetime(2026, 9, 12, 12, 0, 0, tzinfo=timezone.utc)
        ticks: List[dict] = []

        # BTC/USDT: 300 ticks spanning 5 minutes
        for i in range(300):
            ts = base_time + timedelta(seconds=i)
            price = 60000.0 + (i * 2.5) + (10.0 if i % 10 == 0 else -5.0)
            ticks.append({
                "trade_id": f"btc_{i}",
                "symbol": "BTC/USDT",
                "asset_class": "crypto",
                "exchange": "BINANCE",
                "timestamp": ts.isoformat(),
                "price": price,
                "quantity": 0.5 + (i % 3) * 0.2,
                "side": "BUY" if i % 2 == 0 else "SELL",
                "is_buyer_maker": i % 2 != 0,
                "liquidation": False,
                "notional_usd": price * (0.5 + (i % 3) * 0.2),
            })

        # ETH/USDT: 300 ticks
        for i in range(300):
            ts = base_time + timedelta(seconds=i)
            price = 3200.0 + (i * 0.3)
            ticks.append({
                "trade_id": f"eth_{i}",
                "symbol": "ETH/USDT",
                "asset_class": "crypto",
                "exchange": "BINANCE",
                "timestamp": ts.isoformat(),
                "price": price,
                "quantity": 2.0,
                "side": "BUY" if i % 3 != 0 else "SELL",
                "is_buyer_maker": False,
                "liquidation": False,
                "notional_usd": price * 2.0,
            })

        # NVDA: 300 ticks
        for i in range(300):
            ts = base_time + timedelta(seconds=i)
            price = 120.0 + (i * 0.05)
            ticks.append({
                "trade_id": f"nvda_{i}",
                "symbol": "NVDA",
                "asset_class": "equities",
                "exchange": "NASDAQ",
                "timestamp": ts.isoformat(),
                "price": price,
                "quantity": 50.0,
                "side": "BUY" if i % 2 == 0 else "SELL",
                "is_buyer_maker": False,
                "liquidation": False,
                "notional_usd": price * 50.0,
            })

        cls.exporter.export_to_parquet(ticks)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_lakehouse_metadata_extraction(self):
        meta = self.manager.get_lake_metadata()
        self.assertTrue(meta["exists"])
        self.assertGreaterEqual(meta["total_files"], 1)
        self.assertGreaterEqual(meta["total_records"], 900)
        self.assertEqual(meta["symbols_count"], 3)
        self.assertIn("BTC/USDT", meta["symbols"])
        self.assertIn("NVDA", meta["symbols"])
        self.assertIn("crypto", meta["asset_classes"])
        self.assertIn("equities", meta["asset_classes"])

    def test_duckdb_vectorized_ohlcv_accuracy(self):
        df_1m = self.manager.query_ohlcv(symbol="BTC/USDT", timeframe="1m")
        self.assertFalse(df_1m.empty)
        self.assertIn("bucket_time", df_1m.columns)
        self.assertIn("open", df_1m.columns)
        self.assertIn("high", df_1m.columns)
        self.assertIn("low", df_1m.columns)
        self.assertIn("close", df_1m.columns)
        self.assertIn("vwap", df_1m.columns)
        self.assertIn("volume", df_1m.columns)
        self.assertIn("trade_count", df_1m.columns)

        # Invariant checks per bar
        for _, row in df_1m.iterrows():
            self.assertGreaterEqual(row["high"], row["low"])
            self.assertGreaterEqual(row["high"], row["open"])
            self.assertGreaterEqual(row["high"], row["close"])
            self.assertLessEqual(row["low"], row["open"])
            self.assertLessEqual(row["low"], row["close"])
            self.assertGreaterEqual(row["vwap"], row["low"])
            self.assertLessEqual(row["vwap"], row["high"])
            self.assertGreater(row["trade_count"], 0)

    def test_arbitrary_candlestick_timeframes(self):
        for tf in ["100ms", "500ms", "1s", "5s", "15s", "1m", "5m"]:
            df = self.manager.query_ohlcv(symbol="ETH/USDT", timeframe=tf)
            self.assertFalse(df.empty, f"Failed to generate OHLCV for timeframe '{tf}'")
            # Verify timestamps are strictly ascending
            ts_series = pd.to_datetime(df["bucket_time"])
            self.assertTrue(ts_series.is_monotonic_increasing)

    def test_kyles_lambda_and_amihud_illiquidity(self):
        df_lambda = self.manager.query_kyles_lambda(symbol="BTC/USDT", timeframe="1m")
        self.assertFalse(df_lambda.empty)
        self.assertIn("kyles_lambda", df_lambda.columns)
        self.assertTrue((df_lambda["kyles_lambda"] >= 0.0).all())

        df_amihud = self.manager.query_amihud_illiquidity(symbol="NVDA", timeframe="1m")
        self.assertFalse(df_amihud.empty)
        self.assertIn("amihud_ratio", df_amihud.columns)
        self.assertTrue((df_amihud["amihud_ratio"] >= 0.0).all())

    def test_cross_sectional_correlation_matrix_invariants(self):
        symbols = ["BTC/USDT", "ETH/USDT", "NVDA"]
        corr = self.manager.query_cross_sectional_correlation(symbols, timeframe="1s", lookback_bars=100)

        # 1. Dimension invariant
        self.assertEqual(corr.shape, (3, 3))

        # 2. Diagonal invariant: corr(X, X) == 1.0
        for s in symbols:
            self.assertAlmostEqual(corr.loc[s, s], 1.0, places=4)

        # 3. Symmetry invariant: corr(X, Y) == corr(Y, X)
        for s1 in symbols:
            for s2 in symbols:
                self.assertAlmostEqual(corr.loc[s1, s2], corr.loc[s2, s1], places=4)
                # Bounded in [-1.0, 1.0]
                self.assertGreaterEqual(corr.loc[s1, s2], -1.0)
                self.assertLessEqual(corr.loc[s1, s2], 1.0)

    def test_vectorized_query_performance_gate(self):
        """Performance Invariant: DuckDB scan latency must be sub-15ms."""
        bench = self.manager.benchmark_query_throughput(symbol="BTC/USDT")
        print(f"\n[DUCKDB SCAN GATE] {bench['rows_scanned']} rows scanned in {bench['latency_ms']:.3f} ms "
              f"({bench['scan_rate_rows_per_sec']:,.1f} rows/sec)")
        self.assertTrue(bench["sub_15ms_pass"], f"Scan latency {bench['latency_ms']}ms exceeded 15ms gate")


class TestMarketLakeCompactor(unittest.TestCase):
    """Verifies that fragmented streaming Parquet files are coalesced and deduplicated."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.part_dir = os.path.join(self.temp_dir, "asset_class=crypto", "symbol_clean=SOL-USDT", "year=2026", "month=09", "day=12")
        os.makedirs(self.part_dir, exist_ok=True)

        base_t = datetime(2026, 9, 12, 10, 0, 0, tzinfo=timezone.utc)
        # Create 3 micro-batch Parquet parts
        for part_idx in range(3):
            file_p = os.path.join(self.part_dir, f"part_{part_idx}.parquet")
            rows = []
            for i in range(10):
                idx = part_idx * 10 + i
                rows.append({
                    "trade_id": f"sol_{idx}",
                    "symbol": "SOL/USDT",
                    "exchange": "BINANCE",
                    "timestamp": (base_t + timedelta(seconds=idx)).isoformat(),
                    "price": 140.0 + i * 0.1,
                    "quantity": 10.0,
                    "side": "BUY",
                })
            df = pd.DataFrame(rows)
            df.to_parquet(file_p, engine="pyarrow", compression="snappy", index=False)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_compactor_coalescing_and_retention(self):
        files_before = [f for f in os.listdir(self.part_dir) if f.endswith(".parquet")]
        self.assertEqual(len(files_before), 3)

        # Run compaction
        res = compact_partition_directory(self.part_dir, min_files=2)
        self.assertEqual(res["status"], "COMPACTED")
        self.assertEqual(res["files_before"], 3)
        self.assertEqual(res["files_after"], 1)
        self.assertEqual(res["rows_after"], 30)

        # Verify only 1 compacted file remains
        files_after = [f for f in os.listdir(self.part_dir) if f.endswith(".parquet")]
        self.assertEqual(len(files_after), 1)
        self.assertTrue(files_after[0].startswith("compacted_trades_"))

        # Verify row integrity and chronological sort via DuckDB
        con = duckdb.connect()
        df = con.execute(f"SELECT * FROM read_parquet('{os.path.join(self.part_dir, files_after[0]).replace(os.sep, '/')}')").df()
        con.close()

        self.assertEqual(len(df), 30)
        ts_series = pd.to_datetime(df["timestamp"])
        self.assertTrue(ts_series.is_monotonic_increasing)


if __name__ == "__main__":
    unittest.main()
