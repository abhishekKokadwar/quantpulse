"""
QuantPulse: Phase 4 Stream Processing & Market Microstructure Test Suite
========================================================================
Comprehensive unit, invariant, and performance tests for:
1. Mathematical Microstructure Indicators (VWAP, Micro-Price, OFI, Realized Volatility, CVD)
2. Multi-horizon sliding window event bucketing (10s scalping & 5m trend)
3. Event-time watermarking & late tick rejection
4. Dual-sink persistence (Postgres/SQLite hot path & Parquet cold lake)
5. Throughput performance gate (>10,000 events/sec)
"""

from datetime import datetime, timedelta, timezone
import math
import os
import shutil
import sys
import tempfile
import unittest

import duckdb
import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from database.market_db import MarketDatabaseManager
from stream_processor.quant_spark_processor import (
    LocalQuantStreamProcessor,
    QuantMicrostructureAggregate,
    QuantMicrostructureEngine,
)


class TestQuantMicrostructureEngine(unittest.TestCase):
    """Verifies analytical accuracy and boundary constraints for microstructure indicators."""

    def test_vwap_mathematical_precision(self):
        prices = np.array([100.0, 102.0, 101.0, 105.0], dtype=np.float64)
        volumes = np.array([10.0, 20.0, 30.0, 40.0], dtype=np.float64)
        expected_vwap = np.sum(prices * volumes) / np.sum(volumes)
        actual_vwap = QuantMicrostructureEngine.calculate_vwap(prices, volumes)
        self.assertAlmostEqual(actual_vwap, expected_vwap, places=6)
        self.assertEqual(expected_vwap, (1000 + 2040 + 3030 + 4200) / 100.0)

        # Zero / empty volume edge cases
        self.assertEqual(QuantMicrostructureEngine.calculate_vwap(np.array([]), np.array([])), 0.0)
        self.assertEqual(
            QuantMicrostructureEngine.calculate_vwap(np.array([150.0]), np.array([0.0])), 150.0
        )

    def test_micro_price_bounds(self):
        bid_p, ask_p = 100.0, 101.0

        # Case 1: Symmetric depth
        p_micro_sym = QuantMicrostructureEngine.calculate_micro_price(bid_p, 10.0, ask_p, 10.0)
        self.assertAlmostEqual(p_micro_sym, 100.5, places=4)

        # Case 2: Heavy bid depth (buying pressure -> price tends to ask)
        p_micro_bull = QuantMicrostructureEngine.calculate_micro_price(bid_p, 90.0, ask_p, 10.0)
        self.assertGreater(p_micro_bull, 100.5)
        self.assertLessEqual(p_micro_bull, ask_p)

        # Case 3: Heavy ask depth (selling pressure -> price tends to bid)
        p_micro_bear = QuantMicrostructureEngine.calculate_micro_price(bid_p, 10.0, ask_p, 90.0)
        self.assertLess(p_micro_bear, 100.5)
        self.assertGreaterEqual(p_micro_bear, bid_p)

        # Invariant check across extreme values
        for q_bid, q_ask in [(0.01, 1000.0), (1000.0, 0.01), (0.0, 0.0)]:
            p_m = QuantMicrostructureEngine.calculate_micro_price(bid_p, q_bid, ask_p, q_ask)
            self.assertGreaterEqual(p_m, bid_p)
            self.assertLessEqual(p_m, ask_p)

    def test_order_flow_imbalance_bounds_and_dynamics(self):
        # Static OFI
        self.assertAlmostEqual(QuantMicrostructureEngine.calculate_order_flow_imbalance(50.0, 50.0), 0.0)
        self.assertAlmostEqual(QuantMicrostructureEngine.calculate_order_flow_imbalance(100.0, 0.0), 1.0)
        self.assertAlmostEqual(QuantMicrostructureEngine.calculate_order_flow_imbalance(0.0, 100.0), -1.0)

        # Dynamic OFI (Cont-Kukanov-Stoikov)
        # Bid price increases: full new bid size is added
        ofi_up = QuantMicrostructureEngine.calculate_dynamic_ofi(
            prev_bid_price=100.0, prev_bid_size=10.0,
            prev_ask_price=101.0, prev_ask_size=10.0,
            curr_bid_price=100.5, curr_bid_size=15.0,
            curr_ask_price=101.0, curr_ask_size=10.0,
        )
        self.assertEqual(ofi_up, 15.0)

        # Ask price decreases: ask queue aggressively pushed down
        ofi_down = QuantMicrostructureEngine.calculate_dynamic_ofi(
            prev_bid_price=100.0, prev_bid_size=10.0,
            prev_ask_price=101.0, prev_ask_size=10.0,
            curr_bid_price=100.0, curr_bid_size=10.0,
            curr_ask_price=100.5, curr_ask_size=20.0,
        )
        self.assertEqual(ofi_down, -20.0)

    def test_cumulative_volume_delta(self):
        quantities = np.array([5.0, 3.0, 2.0, 10.0], dtype=np.float64)
        sides = np.array(["BUY", "SELL", "BUY", "SELL"])
        # BUY = 5 + 2 = 7; SELL = 3 + 10 = 13; CVD = 7 - 13 = -6
        cvd = QuantMicrostructureEngine.calculate_cumulative_volume_delta(quantities, sides)
        self.assertEqual(cvd, -6.0)

    def test_realized_volatility_calculation(self):
        # Flat prices -> zero volatility
        flat_prices = np.array([100.0, 100.0, 100.0, 100.0])
        vol_flat = QuantMicrostructureEngine.calculate_realized_volatility(flat_prices, window_sec=10.0)
        self.assertEqual(vol_flat, 0.0)

        # Jumping prices -> non-zero annualized volatility
        jumpy_prices = np.array([100.0, 102.0, 99.0, 103.5, 101.0])
        vol_jumpy = QuantMicrostructureEngine.calculate_realized_volatility(jumpy_prices, window_sec=10.0)
        self.assertGreater(vol_jumpy, 0.0)
        # Less than 2 prices
        self.assertEqual(QuantMicrostructureEngine.calculate_realized_volatility(np.array([100.0])), 0.0)


class TestLocalQuantStreamProcessor(unittest.TestCase):
    """Verifies sliding window bucketing, watermarking, dual sinks, and performance."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_market.db")
        self.lake_dir = os.path.join(self.temp_dir, "lake")
        self.db = MarketDatabaseManager(f"sqlite:///{self.db_path.replace(os.sep, '/')}")
        self.db.init_db()
        self.db.seed_dimensions()
        self.processor = LocalQuantStreamProcessor(
            db_manager=self.db,
            lake_output_dir=self.lake_dir,
            watermark_seconds=10.0,
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_sliding_window_aggregation_10s_and_5m(self):
        base_time = datetime(2026, 9, 12, 10, 0, 0, tzinfo=timezone.utc)
        sym = "BTC/USDT"

        # Ingest 30 trades spanning 30 seconds (1 trade per second)
        for i in range(30):
            t_time = base_time + timedelta(seconds=i)
            self.processor.ingest_trade({
                "trade_id": str(i),
                "symbol": sym,
                "exchange": "BINANCE",
                "timestamp": t_time.isoformat(),
                "price": 60000.0 + (i * 10.0),
                "quantity": 1.0,
                "side": "BUY" if i % 2 == 0 else "SELL",
            })
            self.processor.ingest_orderbook({
                "snapshot_id": i,
                "symbol": sym,
                "exchange": "BINANCE",
                "timestamp": t_time.isoformat(),
                "bid_price_1": 60000.0 + (i * 10.0),
                "bid_size_1": 5.0,
                "ask_price_1": 60001.0 + (i * 10.0),
                "ask_size_1": 5.0,
            })

        # Evaluate window at T = 30s
        eval_time = base_time + timedelta(seconds=29)

        # 10s horizon: trades from second 19 to 29 (11 ticks)
        agg_10s = self.processor.compute_symbol_window(
            symbol=sym,
            window_end=eval_time,
            window_seconds=10.0,
            horizon_label="10s",
        )
        self.assertIsNotNone(agg_10s)
        self.assertEqual(agg_10s.horizon, "10s")
        self.assertGreater(agg_10s.trade_count, 0)
        self.assertLessEqual(agg_10s.trade_count, 11)
        self.assertAlmostEqual(agg_10s.order_flow_imbalance, 0.0, places=3)
        self.assertGreaterEqual(agg_10s.micro_price, 60000.0)

        # 5m horizon: should contain all 30 trades
        agg_5m = self.processor.compute_symbol_window(
            symbol=sym,
            window_end=eval_time,
            window_seconds=300.0,
            horizon_label="5m",
        )
        self.assertIsNotNone(agg_5m)
        self.assertEqual(agg_5m.trade_count, 30)
        self.assertEqual(agg_5m.total_volume, 30.0)

    def test_watermark_late_arriving_tick_handling(self):
        base_time = datetime(2026, 9, 12, 10, 0, 0, tzinfo=timezone.utc)
        sym = "ETH/USDT"

        # Ingest current tick at T = 20s
        t20 = base_time + timedelta(seconds=20)
        accepted_current = self.processor.ingest_trade({
            "trade_id": "1",
            "symbol": sym,
            "timestamp": t20.isoformat(),
            "price": 3000.0,
            "quantity": 1.0,
            "side": "BUY",
        })
        self.assertTrue(accepted_current)

        # Tick at T = 15s (within 10s watermark: 20 - 10 = 10s) -> should be ACCEPTED
        t15 = base_time + timedelta(seconds=15)
        accepted_recent = self.processor.ingest_trade({
            "trade_id": "2",
            "symbol": sym,
            "timestamp": t15.isoformat(),
            "price": 2995.0,
            "quantity": 1.0,
            "side": "BUY",
        })
        self.assertTrue(accepted_recent)

        # Tick at T = 5s (outside 10s watermark: 20 - 10 = 10s) -> should be DROPPED
        t5 = base_time + timedelta(seconds=5)
        accepted_late = self.processor.ingest_trade({
            "trade_id": "3",
            "symbol": sym,
            "timestamp": t5.isoformat(),
            "price": 2980.0,
            "quantity": 1.0,
            "side": "BUY",
        })
        self.assertFalse(accepted_late)

    def test_dual_sink_hot_and_cold(self):
        now = datetime.utcnow()
        aggs = [
            QuantMicrostructureAggregate(
                window_start=now - timedelta(seconds=10),
                window_end=now,
                symbol="NVDA",
                horizon="10s",
                vwap=120.50,
                order_flow_imbalance=0.25,
                micro_price=120.52,
                realized_volatility=0.35,
                cumulative_volume_delta=450.0,
                trade_count=18,
                total_volume=1200.0,
            ),
            QuantMicrostructureAggregate(
                window_start=now - timedelta(seconds=10),
                window_end=now,
                symbol="AAPL",
                horizon="10s",
                vwap=225.10,
                order_flow_imbalance=-0.15,
                micro_price=225.08,
                realized_volatility=0.22,
                cumulative_volume_delta=-200.0,
                trade_count=12,
                total_volume=800.0,
            ),
        ]

        # 1. Hot path persistence
        rows_inserted = self.processor.sink_hot_path(aggs)
        self.assertEqual(rows_inserted, 2)

        df_nvda = self.db.get_latest_quant_aggregates("NVDA", horizon="10s", limit=5)
        self.assertEqual(len(df_nvda), 1)
        self.assertAlmostEqual(float(df_nvda.iloc[0]["vwap"]), 120.50, places=2)
        self.assertAlmostEqual(float(df_nvda.iloc[0]["micro_price"]), 120.52, places=2)
        self.assertEqual(int(df_nvda.iloc[0]["trade_count"]), 18)

        # 2. Cold path persistence
        parquet_file = self.processor.sink_cold_path(aggs)
        self.assertTrue(os.path.exists(parquet_file))

        # Query written parquet via DuckDB to verify format
        con = duckdb.connect()
        duck_df = con.execute(f"SELECT * FROM read_parquet('{parquet_file}')").df()
        self.assertEqual(len(duck_df), 2)
        self.assertIn("vwap", duck_df.columns)
        self.assertIn("cumulative_volume_delta", duck_df.columns)

    def test_stream_processor_throughput_performance_gate(self):
        """
        Performance Invariant: Local streaming engine must process > 10,000 events/sec.
        """
        import time

        sym = "BTC/USDT"
        now = datetime.now(timezone.utc)
        n_events = 15000

        start_t = time.time()
        for i in range(n_events):
            t_event = now + timedelta(milliseconds=i)
            self.processor.ingest_trade({
                "trade_id": str(i),
                "symbol": sym,
                "timestamp": t_event,
                "price": 60000.0 + (i % 50),
                "quantity": 1.0,
                "side": "BUY" if i % 2 == 0 else "SELL",
            })

        duration = time.time() - start_t
        throughput = n_events / max(duration, 0.001)

        print(f"\n[STREAM BENCHMARK] Ingested {n_events} trades in {duration:.4f}s ({throughput:,.1f} events/sec)")
        self.assertGreater(throughput, 10000.0, "Throughput must exceed 10,000 events/second")


if __name__ == "__main__":
    unittest.main()
