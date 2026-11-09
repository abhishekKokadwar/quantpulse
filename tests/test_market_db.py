"""
QuantPulse: Automated Test Suite for Phase 2 Relational Market Database
======================================================================
Validates:
1. Financial 3NF star schema initialization and 42-instrument + 8-exchange seeding.
2. High-throughput bulk trade tick and Level-2 order book snapshot ingestion.
3. Real-time portfolio position accounting: weighted average entry price,
   mark-to-market unrealized PnL, and realized PnL on position reductions.
4. Pre/post-trade risk event audit logging and circuit breaker storage.
5. SQL pushdown time-bucketed OHLCV candle aggregations with VWAP.
6. Market database metadata and statistics reporting.
"""

import os
import unittest
from datetime import datetime, timedelta, timezone

import pandas as pd

from database.market_db import MarketDatabaseManager
from simulator.market_simulator import MarketSimulator


class TestMarketDatabase(unittest.TestCase):

    def setUp(self):
        # Use an isolated in-memory SQLite database for deterministic unit testing
        self.db = MarketDatabaseManager(db_url="sqlite:///:memory:")
        self.db.init_db()
        self.sim = MarketSimulator(seed=42)

    # -------------------------------------------------------------------------
    # 1. Dimension Seeding Tests
    # -------------------------------------------------------------------------
    def test_seed_42_instruments_and_8_exchanges(self):
        n_inst, n_exch = self.db.seed_dimensions()
        self.assertEqual(n_inst, 42)
        self.assertEqual(n_exch, 8)

        stats = self.db.get_market_db_stats()
        self.assertEqual(stats["instruments_count"], 42)
        self.assertEqual(stats["exchanges_count"], 8)

    # -------------------------------------------------------------------------
    # 2. Trade Tick Ingestion & Queries
    # -------------------------------------------------------------------------
    def test_bulk_insert_trade_ticks(self):
        self.db.seed_dimensions()
        ticks = [
            self.sim.generate_trade("BTC/USDT").to_dict()
            for _ in range(25)
        ] + [
            self.sim.generate_trade("AAPL").to_dict()
            for _ in range(25)
        ]

        inserted = self.db.insert_trade_ticks(ticks)
        self.assertEqual(inserted, 50)

        stats = self.db.get_market_db_stats()
        self.assertEqual(stats["trades_count"], 50)

        # Query recent trades
        recent = self.db.query_recent_trades(symbol="BTC/USDT", limit=10)
        self.assertEqual(len(recent), 10)
        self.assertEqual(recent.iloc[0]["symbol"], "BTC/USDT")
        self.assertGreater(recent.iloc[0]["price"], 0.0)

    # -------------------------------------------------------------------------
    # 3. Order Book L2 Snapshot Ingestion & Retrieval
    # -------------------------------------------------------------------------
    def test_bulk_insert_orderbook_snapshots(self):
        self.db.seed_dimensions()
        snapshots = [
            self.sim.generate_order_book("ETH/USDT").to_dict()
            for _ in range(10)
        ]
        inserted = self.db.insert_orderbook_snapshots(snapshots)
        self.assertEqual(inserted, 10)

        stats = self.db.get_market_db_stats()
        self.assertEqual(stats["snapshots_count"], 10)

        latest = self.db.query_latest_orderbook("ETH/USDT")
        self.assertIsNotNone(latest)
        self.assertEqual(latest["symbol"], "ETH/USDT")
        self.assertGreater(latest["ask_price_1"], latest["bid_price_1"])
        self.assertIn("bids", latest["depth_json"])
        self.assertIn("asks", latest["depth_json"])

    # -------------------------------------------------------------------------
    # 4. Real-Time Portfolio Position Accounting & Mark-to-Market
    # -------------------------------------------------------------------------
    def test_portfolio_position_accounting_long_and_unrealized_pnl(self):
        self.db.seed_dimensions()

        # Step 1: Buy 2 BTC at $60,000, mark at $64,000
        pos1 = self.db.update_portfolio_fill(
            symbol="BTC/USDT",
            side="BUY",
            fill_price=60000.0,
            fill_qty=2.0,
            current_mark_price=64000.0,
        )
        self.assertEqual(pos1["net_quantity"], 2.0)
        self.assertEqual(pos1["avg_entry_price"], 60000.0)
        self.assertEqual(pos1["unrealized_pnl"], 8000.0)  # 2 * (64000 - 60000)
        self.assertEqual(pos1["realized_pnl"], 0.0)
        self.assertEqual(pos1["total_notional"], 128000.0)

        # Step 2: Buy 1 more BTC at $66,000 (weighted avg entry becomes (120000 + 66000) / 3 = $62,000)
        pos2 = self.db.update_portfolio_fill(
            symbol="BTC/USDT",
            side="BUY",
            fill_price=66000.0,
            fill_qty=1.0,
            current_mark_price=65000.0,
        )
        self.assertEqual(pos2["net_quantity"], 3.0)
        self.assertEqual(pos2["avg_entry_price"], 62000.0)
        self.assertEqual(pos2["unrealized_pnl"], 9000.0)  # 3 * (65000 - 62000)

    def test_portfolio_position_accounting_sell_and_realized_pnl(self):
        self.db.seed_dimensions()

        # Buy 2 BTC at $60,000
        self.db.update_portfolio_fill(
            symbol="BTC/USDT",
            side="BUY",
            fill_price=60000.0,
            fill_qty=2.0,
            current_mark_price=60000.0,
        )

        # Sell 1 BTC at $65,000 (realizes $5,000 profit)
        pos_sell = self.db.update_portfolio_fill(
            symbol="BTC/USDT",
            side="SELL",
            fill_price=65000.0,
            fill_qty=1.0,
            current_mark_price=65000.0,
        )
        self.assertEqual(pos_sell["net_quantity"], 1.0)
        self.assertEqual(pos_sell["avg_entry_price"], 60000.0)
        self.assertEqual(pos_sell["realized_pnl"], 5000.0)  # 1 * (65000 - 60000)
        self.assertEqual(pos_sell["unrealized_pnl"], 5000.0)  # remaining 1 BTC: 1 * (65000 - 60000)

    # -------------------------------------------------------------------------
    # 5. Risk Event Logging & Circuit Breakers
    # -------------------------------------------------------------------------
    def test_risk_event_logging(self):
        self.db.seed_dimensions()
        ev1 = self.db.log_risk_event(
            symbol="NVDA",
            risk_rule="VOLATILITY_SPIKE",
            severity="WARNING",
            metric_value=0.55,
            threshold_value=0.45,
            description="Intraday annualized volatility breached 45% threshold.",
            details={"annualized_vol": 0.55, "rolling_window": "5m"},
        )
        self.assertGreaterEqual(ev1, 1)

        ev2 = self.db.log_risk_event(
            symbol="BTC/USDT",
            risk_rule="MAX_DRAWDOWN",
            severity="CIRCUIT_BREAKER",
            metric_value=-0.035,
            threshold_value=-0.030,
            description="Hourly portfolio drawdown breached -3.0% circuit breaker limit.",
            details={"action_taken": "THROTTLE_SIZING_50_PCT"},
        )
        self.assertGreaterEqual(ev2, 1)

        stats = self.db.get_market_db_stats()
        self.assertEqual(stats["risk_events_count"], 2)

    # -------------------------------------------------------------------------
    # 6. SQL Pushdown OHLCV Candle Aggregation
    # -------------------------------------------------------------------------
    def test_sql_pushdown_ohlcv_aggregation(self):
        self.db.seed_dimensions()
        base_time = datetime(2026, 9, 12, 10, 0, 0, tzinfo=timezone.utc)

        # Insert deterministic ticks
        ticks = [
            {"symbol": "AAPL", "exchange": "NASDAQ", "timestamp": base_time + timedelta(seconds=5), "price": 220.0, "quantity": 10.0, "side": "BUY"},
            {"symbol": "AAPL", "exchange": "NASDAQ", "timestamp": base_time + timedelta(seconds=20), "price": 225.0, "quantity": 20.0, "side": "BUY"},
            {"symbol": "AAPL", "exchange": "NASDAQ", "timestamp": base_time + timedelta(seconds=40), "price": 218.0, "quantity": 15.0, "side": "BUY"},
            {"symbol": "AAPL", "exchange": "NASDAQ", "timestamp": base_time + timedelta(seconds=55), "price": 222.0, "quantity": 5.0, "side": "BUY"},
        ]
        self.db.insert_trade_ticks(ticks)

        df_ohlcv = self.db.query_ohlcv_pushdown("AAPL", bucket_minutes=1)
        self.assertEqual(len(df_ohlcv), 1)

        bar = df_ohlcv.iloc[0]
        self.assertEqual(bar["open"], 220.0)
        self.assertEqual(bar["high"], 225.0)
        self.assertEqual(bar["low"], 218.0)
        self.assertEqual(bar["close"], 222.0)
        self.assertEqual(bar["volume"], 50.0)
        self.assertEqual(bar["trade_count"], 4)
        # Expected VWAP = (220*10 + 225*20 + 218*15 + 222*5) / 50 = (2200 + 4500 + 3270 + 1110) / 50 = 11080 / 50 = 221.6
        self.assertAlmostEqual(bar["vwap"], 221.6, places=2)


if __name__ == "__main__":
    unittest.main()
