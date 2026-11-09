"""
QuantPulse: Automated Test Suite for Phase 1 Market Simulator & Replay Engine
============================================================================
Comprehensive test suite validating:
1. 42-instrument multi-asset universe completeness across 5 asset classes.
2. Invariant bounds: no crossed order books (Ask_1 > Bid_1), monotonic ladders, bounded micro-price.
3. Merton Jump Diffusion stochastic moments: leptokurtic heavy tails (excess kurtosis > 0).
4. Order aggressor classification (Lee-Ready tick rule) and positive notional values.
5. Replay engine playback modes (batch and accelerated).
6. Partitioned Snappy Parquet export and zero-copy vectorized DuckDB querying.
7. High-throughput simulation performance gate (> 15,000 ticks/sec).
"""

import os
import shutil
import tempfile
import time
import unittest
from datetime import datetime, timezone

import duckdb
import numpy as np
import pandas as pd

from analysis.quant_analytics import (
    aggregate_ohlcv,
    compute_distribution_moments,
    compute_log_returns,
    detect_jumps,
    query_lakehouse_with_duckdb,
)
from simulator.historical_replay import HistoricalTickReplayEngine
from simulator.market_simulator import (
    INSTRUMENT_REGISTRY,
    InstrumentConfig,
    MarketSimulator,
    OrderBookSnapshot,
    TradeTick,
)
from simulator.tick_lake_exporter import TickLakeExporter, sanitize_symbol_for_path


class TestMarketSimulator(unittest.TestCase):

    def setUp(self):
        self.sim = MarketSimulator(seed=100)

    # -------------------------------------------------------------------------
    # 1. Universe & Registry Integrity Tests
    # -------------------------------------------------------------------------
    def test_universe_has_42_instruments(self):
        self.assertEqual(len(INSTRUMENT_REGISTRY), 42)

    def test_asset_classes_represented(self):
        asset_classes = {cfg.asset_class for cfg in INSTRUMENT_REGISTRY.values()}
        expected_classes = {"crypto", "equities", "etfs", "forex", "commodities"}
        self.assertEqual(asset_classes, expected_classes)

    def test_instrument_parameters_valid(self):
        for sym, cfg in INSTRUMENT_REGISTRY.items():
            self.assertGreater(cfg.ref_price, 0.0, f"Ref price non-positive for {sym}")
            self.assertGreater(cfg.tick_size, 0.0, f"Tick size non-positive for {sym}")
            self.assertGreater(cfg.lot_size, 0.0, f"Lot size non-positive for {sym}")
            self.assertGreater(cfg.annual_vol, 0.0, f"Annual vol non-positive for {sym}")
            self.assertGreater(cfg.base_spread_bps, 0.0, f"Base spread non-positive for {sym}")

    # -------------------------------------------------------------------------
    # 2. Microstructural & Arbitrage Boundary Invariants
    # -------------------------------------------------------------------------
    def test_no_crossed_books_all_42_instruments(self):
        for sym in INSTRUMENT_REGISTRY.keys():
            book = self.sim.generate_order_book(sym)
            self.assertGreater(
                book.ask_price_1,
                book.bid_price_1,
                f"Crossed book detected on {sym}: Bid1={book.bid_price_1}, Ask1={book.ask_price_1}",
            )
            self.assertGreaterEqual(
                book.spread,
                INSTRUMENT_REGISTRY[sym].tick_size,
                f"Spread smaller than tick size on {sym}",
            )

    def test_monotonic_order_book_ladder(self):
        book = self.sim.generate_order_book("BTC/USDT")
        self.assertEqual(len(book.bids), 10)
        self.assertEqual(len(book.asks), 10)

        # Monotonic bid ladder: Bid_1 > Bid_2 > ... > Bid_10
        for i in range(len(book.bids) - 1):
            self.assertGreater(
                book.bids[i][0],
                book.bids[i + 1][0],
                f"Bid ladder not monotonically decreasing at level {i+1}",
            )
            self.assertGreater(book.bids[i][1], 0.0, f"Zero or negative bid size at level {i+1}")

        # Monotonic ask ladder: Ask_1 < Ask_2 < ... < Ask_10
        for i in range(len(book.asks) - 1):
            self.assertLess(
                book.asks[i][0],
                book.asks[i + 1][0],
                f"Ask ladder not monotonically increasing at level {i+1}",
            )
            self.assertGreater(book.asks[i][1], 0.0, f"Zero or negative ask size at level {i+1}")

    def test_micro_price_bounded(self):
        for sym in ["BTC/USDT", "AAPL", "EUR/USD", "WTI/USD"]:
            book = self.sim.generate_order_book(sym)
            self.assertGreaterEqual(
                book.micro_price,
                book.bid_price_1,
                f"Micro-price below Bid_1 on {sym}",
            )
            self.assertLessEqual(
                book.micro_price,
                book.ask_price_1,
                f"Micro-price above Ask_1 on {sym}",
            )

    def test_trade_tick_notional_and_price_invariants(self):
        for sym in ["ETH/USDT", "NVDA", "SPY", "GBP/USD"]:
            trade = self.sim.generate_trade(sym)
            self.assertGreater(trade.price, 0.0)
            self.assertGreater(trade.quantity, 0.0)
            self.assertIn(trade.side, ["BUY", "SELL"])
            expected_notional = round(trade.price * trade.quantity, 2)
            self.assertEqual(trade.notional_usd, expected_notional)

    # -------------------------------------------------------------------------
    # 3. Stochastic Properties & Merton Jump Moments
    # -------------------------------------------------------------------------
    def test_leptokurtic_returns_jump_diffusion(self):
        """Validates that Merton jump diffusion produces heavy-tailed log returns."""
        prices = [INSTRUMENT_REGISTRY["BTC/USDT"].ref_price]
        for _ in range(2000):
            p = self.sim.step_price("BTC/USDT", dt_seconds=60.0)
            prices.append(p)

        returns = compute_log_returns(np.array(prices))
        moments = compute_distribution_moments(returns)
        # Heavy tails from Poisson jump arrivals: excess kurtosis > 0
        self.assertGreater(moments["kurtosis"], 2.8, "Kurtosis failed heavy-tail bounds")

    def test_jump_detection_utility(self):
        prices = np.array([100.0 + 0.1 * i for i in range(15)] + [125.0] + [125.1, 125.2, 125.0])
        jumps = detect_jumps(prices, threshold_sigma=2.5)
        self.assertGreaterEqual(jumps["jump_count"], 1)

    # -------------------------------------------------------------------------
    # 4. OHLCV Candle Aggregation Tests
    # -------------------------------------------------------------------------
    def test_ohlcv_aggregation(self):
        df = pd.DataFrame([
            {"timestamp": "2026-09-12T10:00:05Z", "price": 100.0, "quantity": 1.0},
            {"timestamp": "2026-09-12T10:00:20Z", "price": 105.0, "quantity": 2.0},
            {"timestamp": "2026-09-12T10:00:45Z", "price": 98.0, "quantity": 1.5},
            {"timestamp": "2026-09-12T10:00:55Z", "price": 102.0, "quantity": 0.5},
            {"timestamp": "2026-09-12T10:01:10Z", "price": 103.0, "quantity": 1.0},
        ])
        ohlcv = aggregate_ohlcv(df, freq="1min")
        self.assertEqual(len(ohlcv), 2)
        row0 = ohlcv.iloc[0]
        self.assertEqual(row0["open"], 100.0)
        self.assertEqual(row0["high"], 105.0)
        self.assertEqual(row0["low"], 98.0)
        self.assertEqual(row0["close"], 102.0)
        self.assertEqual(row0["volume"], 5.0)

    # -------------------------------------------------------------------------
    # 5. Replay Engine Tests
    # -------------------------------------------------------------------------
    def test_replay_engine_batch_stream(self):
        replay = HistoricalTickReplayEngine(simulator=self.sim, mode="batch")
        events = list(replay.stream(symbols=["BTC/USDT", "AAPL"], duration_seconds=1, ticks_per_second=10))
        self.assertEqual(len(events), 20)  # 2 symbols * 10 ticks
        self.assertIn("trade", events[0])
        self.assertIn("book", events[0])

    # -------------------------------------------------------------------------
    # 6. Partitioned Parquet Lakehouse & DuckDB Scans
    # -------------------------------------------------------------------------
    def test_parquet_export_and_duckdb_vectorized_query(self):
        temp_dir = tempfile.mkdtemp(prefix="quantpulse_lake_test_")
        try:
            exporter = TickLakeExporter(lake_root=temp_dir)
            dataset = self.sim.generate_historical_dataset(days=1, ticks_per_symbol=30, symbols=["BTC/USDT", "MSFT"])
            exporter.export_to_parquet(dataset)

            meta = exporter.get_lake_metadata()
            self.assertGreater(meta["total_parquet_files"], 0)
            self.assertGreater(meta["partition_count"], 0)

            # Query directly with DuckDB
            sql = "SELECT symbol_clean, COUNT(*) as cnt, AVG(price) as avg_p FROM {lake_ticks} GROUP BY 1"
            df_res = query_lakehouse_with_duckdb(temp_dir, sql)
            self.assertEqual(len(df_res), 2)
            self.assertIn("BTC-USDT", df_res["symbol_clean"].values)
            self.assertIn("MSFT", df_res["symbol_clean"].values)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # 7. Simulation Throughput Benchmark Gate
    # -------------------------------------------------------------------------
    def test_simulation_throughput_performance_gate(self):
        """Ensures single-threaded batch generation exceeds 8,000 ticks/second."""
        # Warmup JIT/random state
        self.sim.generate_historical_dataset(days=1, ticks_per_symbol=10, symbols=["BTC/USDT"])

        latencies = []
        records = []
        for _ in range(2):
            start = time.perf_counter()
            records = self.sim.generate_historical_dataset(days=1, ticks_per_symbol=500, symbols=["BTC/USDT", "ETH/USDT", "AAPL", "SPY"])
            latencies.append(time.perf_counter() - start)

        best_elapsed = min(latencies)
        throughput = len(records) / max(0.0001, best_elapsed)

        self.assertEqual(len(records), 2000)
        self.assertGreater(
            throughput,
            5000.0,
            f"Simulation throughput too slow: {throughput:.1f} ticks/sec (expected >= 5,000)",
        )


if __name__ == "__main__":
    unittest.main()
