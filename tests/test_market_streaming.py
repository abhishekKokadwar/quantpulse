"""
QuantPulse: Automated Test Suite for Phase 3 Market Ingestion & Streaming
========================================================================
Validates:
1. Multi-exchange normalization protocol (Binance, Coinbase Advanced, Alpaca SIP).
2. Strict symbol partition keying ensuring FIFO sequential order per asset.
3. Asynchronous Kafka producer serialization and in-memory mock buffering.
4. High-velocity consumer micro-batch accumulation and automated database persistence.
5. Real-time portfolio fill tracking and mark-to-market dispatch.
6. Flash crash & sudden volatility price jump risk detection.
7. Full end-to-end streaming ingestion pipeline: Simulator -> Exchange -> Producer -> Consumer -> Database.
"""

import os
import unittest
from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy import text
from consumer.market_consumer import MarketKafkaConsumer
from database.market_db import MarketDatabaseManager
from simulator.exchange_connectors import (
    AlpacaConnector,
    BinanceConnector,
    CoinbaseConnector,
    MockExchangeGateway,
)
from simulator.market_producer import (
    TOPIC_ORDERBOOK_L2,
    TOPIC_TRADES_RAW,
    MarketKafkaProducer,
)
from simulator.market_simulator import MarketSimulator


class TestMarketStreaming(unittest.TestCase):

    def setUp(self):
        # In-memory database manager for clean, isolated testing
        self.db = MarketDatabaseManager(db_url="sqlite:///:memory:")
        self.db.init_db()
        self.db.seed_dimensions()
        self.sim = MarketSimulator(seed=101)

    # -------------------------------------------------------------------------
    # 1. Exchange Connector Normalization Tests
    # -------------------------------------------------------------------------
    def test_binance_trade_normalization(self):
        connector = BinanceConnector()
        raw_msg = {
            "e": "trade",
            "E": 1672531200000,
            "s": "BTCUSDT",
            "t": 888123,
            "p": "64500.50",
            "q": "0.2500",
            "b": 101,
            "a": 102,
            "T": 1672531200000,
            "m": True,  # Buyer is maker -> Seller is aggressor ('SELL')
        }
        tick = connector.normalize_trade(raw_msg)
        self.assertEqual(tick.symbol, "BTC/USDT")
        self.assertEqual(tick.exchange, "BINANCE")
        self.assertEqual(tick.trade_id, 888123)
        self.assertEqual(tick.price, 64500.50)
        self.assertEqual(tick.quantity, 0.25)
        self.assertEqual(tick.side, "SELL")
        self.assertTrue(tick.is_buyer_maker)
        self.assertEqual(tick.notional_usd, round(64500.50 * 0.25, 2))

    def test_coinbase_trade_normalization(self):
        connector = CoinbaseConnector()
        raw_msg = {
            "type": "match",
            "trade_id": 999456,
            "product_id": "BTC-USD",
            "price": "64200.00",
            "size": "0.1000",
            "side": "buy",
            "time": "2026-09-12T10:15:30.123456Z",
        }
        tick = connector.normalize_trade(raw_msg)
        self.assertEqual(tick.symbol, "BTC/USD")
        self.assertEqual(tick.exchange, "COINBASE")
        self.assertEqual(tick.trade_id, 999456)
        self.assertEqual(tick.price, 64200.00)
        self.assertEqual(tick.quantity, 0.10)
        self.assertEqual(tick.side, "BUY")
        self.assertFalse(tick.is_buyer_maker)

    def test_alpaca_trade_normalization(self):
        connector = AlpacaConnector()
        raw_msg = {
            "T": "t",
            "S": "AAPL",
            "i": 555123,
            "x": "NASDAQ",
            "p": 224.50,
            "s": 100,
            "t": "2026-09-12T14:30:00.000Z",
            "side": "BUY",
        }
        tick = connector.normalize_trade(raw_msg)
        self.assertEqual(tick.symbol, "AAPL")
        self.assertEqual(tick.exchange, "NASDAQ")
        self.assertEqual(tick.trade_id, 555123)
        self.assertEqual(tick.price, 224.50)
        self.assertEqual(tick.quantity, 100.0)
        self.assertEqual(tick.notional_usd, 22450.00)

    # -------------------------------------------------------------------------
    # 2. Strict Partition Keying & Producer Tests
    # -------------------------------------------------------------------------
    def test_strict_symbol_partition_keying(self):
        producer = MarketKafkaProducer(force_mock=True)
        trade1 = self.sim.generate_trade("BTC/USDT")
        trade2 = self.sim.generate_trade("BTC/USDT")
        trade_aapl = self.sim.generate_trade("AAPL")

        producer.produce_trade(trade1)
        producer.produce_trade(trade2)
        producer.produce_trade(trade_aapl)

        self.assertEqual(len(producer.in_memory_buffer), 3)
        # Verify keys
        self.assertEqual(producer.in_memory_buffer[0]["key"], "BTC/USDT")
        self.assertEqual(producer.in_memory_buffer[1]["key"], "BTC/USDT")
        self.assertEqual(producer.in_memory_buffer[2]["key"], "AAPL")
        # Ensure identical symbols have strictly identical partition keys
        self.assertEqual(
            producer.in_memory_buffer[0]["key"].encode("utf-8"),
            producer.in_memory_buffer[1]["key"].encode("utf-8"),
        )

    # -------------------------------------------------------------------------
    # 3. Consumer Micro-Batching & Database Auto-Sink Tests
    # -------------------------------------------------------------------------
    def test_consumer_micro_batch_and_db_persistence(self):
        consumer = MarketKafkaConsumer(db_manager=self.db, batch_size=20, force_mock=True)

        # Generate 45 trades and 25 books
        events = []
        for _ in range(45):
            t = self.sim.generate_trade("ETH/USDT").to_dict()
            events.append({"topic": TOPIC_TRADES_RAW, "payload": t})
        for _ in range(25):
            b = self.sim.generate_order_book("ETH/USDT").to_dict()
            events.append({"topic": TOPIC_ORDERBOOK_L2, "payload": b})

        total = consumer.consume_from_mock_stream(events)
        self.assertEqual(total, 70)

        # Verify database row counts
        stats = self.db.get_market_db_stats()
        self.assertEqual(stats["trades_count"], 45)
        self.assertEqual(stats["snapshots_count"], 25)

    # -------------------------------------------------------------------------
    # 4. Live Portfolio Fill Tracking Tests
    # -------------------------------------------------------------------------
    def test_consumer_live_portfolio_fill_tracking(self):
        consumer = MarketKafkaConsumer(db_manager=self.db, force_mock=True)
        consumer.track_portfolio_symbol("BTC/USDT")

        # Ingest buy fill
        buy_tick = {
            "symbol": "BTC/USDT",
            "exchange": "BINANCE",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "price": 60000.0,
            "quantity": 2.0,
            "side": "BUY",
            "is_buyer_maker": False,
            "notional_usd": 120000.0,
        }
        consumer.process_message(TOPIC_TRADES_RAW, buy_tick)
        consumer.flush()

        # Ingest sell fill
        sell_tick = {
            "symbol": "BTC/USDT",
            "exchange": "BINANCE",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "price": 65000.0,
            "quantity": 1.0,
            "side": "SELL",
            "is_buyer_maker": True,
            "notional_usd": 65000.0,
        }
        consumer.process_message(TOPIC_TRADES_RAW, sell_tick)
        consumer.flush()

        stats = self.db.get_market_db_stats()
        self.assertEqual(stats["positions_count"], 1)

        # Verify portfolio state
        with self.db.engine.connect() as conn:
            pos = conn.execute(text("SELECT net_quantity, realized_pnl FROM portfolio_positions WHERE symbol = 'BTC/USDT'")).fetchone()
            self.assertEqual(pos[0], 1.0)
            self.assertEqual(pos[1], 5000.0)

    # -------------------------------------------------------------------------
    # 5. Flash Crash & Sudden Price Jump Sentinel Tests
    # -------------------------------------------------------------------------
    def test_consumer_flash_spike_risk_detection(self):
        consumer = MarketKafkaConsumer(db_manager=self.db, force_mock=True)

        tick1 = {
            "symbol": "SOL/USDT",
            "exchange": "BINANCE",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "price": 140.0,
            "quantity": 10.0,
            "side": "BUY",
            "notional_usd": 1400.0,
        }
        # Sudden +10% price spike
        tick2 = {
            "symbol": "SOL/USDT",
            "exchange": "BINANCE",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "price": 155.0,
            "quantity": 10.0,
            "side": "BUY",
            "notional_usd": 1550.0,
        }

        consumer.process_message(TOPIC_TRADES_RAW, tick1)
        consumer.process_message(TOPIC_TRADES_RAW, tick2)
        consumer.flush()

        stats = self.db.get_market_db_stats()
        self.assertGreaterEqual(stats["risk_events_count"], 1)

    # -------------------------------------------------------------------------
    # 6. End-to-End Streaming Ingestion Pipeline Test
    # -------------------------------------------------------------------------
    def test_end_to_end_streaming_pipeline(self):
        gateway = MockExchangeGateway(self.sim)
        producer = MarketKafkaProducer(force_mock=True)
        consumer = MarketKafkaConsumer(db_manager=self.db, force_mock=True)

        # 1. Gateway generates events across 5 symbols
        symbols = ["BTC/USDT", "ETH/USDT", "AAPL", "SPY", "EUR/USD"]
        for sym in symbols:
            event = gateway.generate_simulated_exchange_event(sym)
            producer.produce_trade(event["normalized_trade"])
            producer.produce_orderbook(event["normalized_book"])

        self.assertEqual(len(producer.in_memory_buffer), 10)  # 5 trades + 5 books

        # 2. Feed buffered messages to consumer
        consumer.consume_from_mock_stream(producer.in_memory_buffer)

        # 3. Assert database storage
        stats = self.db.get_market_db_stats()
        self.assertEqual(stats["trades_count"], 5)
        self.assertEqual(stats["snapshots_count"], 5)


if __name__ == "__main__":
    unittest.main()
