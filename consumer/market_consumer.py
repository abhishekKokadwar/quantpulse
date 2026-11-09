"""
QuantPulse: Decoupled Market Consumer & Relational OLTP Sink
============================================================
Consumes real-time trade ticks and Level-2 order book snapshots from Kafka,
micro-batches records to maximize database write throughput, automatically
updates live portfolio mark-to-market positions, and audits risk anomalies.

Core Responsibilities:
1. Micro-Batch Accumulation: Batches events up to `batch_size` or flushes on interval.
2. Relational OLTP Persistence: Sinks clean records into `database/market_db.py`.
3. Portfolio Fill Dispatch: Updates running position state and PnL.
4. Flash Crash Sentinel: Audits sudden intraday price spikes (> 3%) and logs risk events.
5. In-Memory Mock Testing: Supports consuming from in-memory queues when Kafka is offline.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

# Prevent OpenBLAS Memory Allocation errors on Windows with multiple processes
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"

script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir in sys.path:
    sys.path.remove(script_dir)

PROJECT_ROOT = os.path.abspath(os.path.join(script_dir, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from database.market_db import MarketDatabaseManager

DEFAULT_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
TOPIC_TRADES_RAW = os.getenv("KAFKA_TOPIC_TRADES", "market.trades.raw")
TOPIC_ORDERBOOK_L2 = os.getenv("KAFKA_TOPIC_ORDERBOOK", "market.orderbook.l2")
DEFAULT_GROUP_ID = os.getenv("KAFKA_GROUP_ID", "quantpulse-market-consumer-group")

KAFKA_CLIENT_AVAILABLE = False
try:
    from confluent_kafka import Consumer, KafkaError
    KAFKA_CLIENT_AVAILABLE = True
except ImportError:
    KAFKA_CLIENT_AVAILABLE = False


class MarketKafkaConsumer:
    """
    High-velocity market consumer with micro-batching and database persistence.
    """

    def __init__(
        self,
        db_manager: Optional[MarketDatabaseManager] = None,
        bootstrap_servers: str = DEFAULT_BOOTSTRAP_SERVERS,
        group_id: str = DEFAULT_GROUP_ID,
        batch_size: int = 50,
        flush_interval_sec: float = 0.5,
        force_mock: bool = False,
    ):
        self.db = db_manager or MarketDatabaseManager()
        self.bootstrap_servers = bootstrap_servers
        self.group_id = group_id
        self.batch_size = batch_size
        self.flush_interval_sec = flush_interval_sec
        self.force_mock = force_mock

        self.trade_batch: List[Dict[str, Any]] = []
        self.orderbook_batch: List[Dict[str, Any]] = []
        self.last_flush_time: float = time.perf_counter()

        self.is_running: bool = False
        self.total_consumed: int = 0
        self.tracked_symbols: set = set()
        self.last_prices: Dict[str, float] = {}

        self.consumer: Optional[Any] = None
        self.is_connected: bool = False

        if KAFKA_CLIENT_AVAILABLE and not force_mock:
            try:
                conf = {
                    "bootstrap.servers": self.bootstrap_servers,
                    "group.id": self.group_id,
                    "auto.offset.reset": "earliest",
                    "enable.auto.commit": True,
                    "socket.timeout.ms": 2000,
                }
                self.consumer = Consumer(conf)
                self.is_connected = True
            except Exception as e:
                print(f"[KAFKA CONSUMER NOTICE] Broker unreachable at {bootstrap_servers}: {e}. Mock mode enabled.")
                self.is_connected = False
        else:
            self.is_connected = False

    def track_portfolio_symbol(self, symbol: str) -> None:
        """Enables live portfolio fill accounting for the specified symbol."""
        self.tracked_symbols.add(symbol)

    def process_message(self, topic: str, payload: Dict[str, Any]) -> None:
        """
        Processes a single message, checks risk conditions, updates portfolio fills,
        and enqueues the record into the appropriate micro-batch buffer.
        """
        symbol = payload.get("symbol", "UNKNOWN")

        # 1. Flash Crash & Sudden Spike Sentinel
        if topic == TOPIC_TRADES_RAW:
            price = float(payload.get("price", 0.0))
            if symbol in self.last_prices and self.last_prices[symbol] > 0:
                prev_p = self.last_prices[symbol]
                pct_change = abs(price - prev_p) / prev_p
                if pct_change >= 0.035:  # 3.5% sudden tick jump
                    self.db.log_risk_event(
                        symbol=symbol,
                        risk_rule="FLASH_SPIKE_DETECTED",
                        severity="WARNING",
                        metric_value=pct_change * 100.0,
                        threshold_value=3.5,
                        description=f"Sudden {pct_change * 100.0:.2f}% price shift from ${prev_p} to ${price}.",
                        details={"prev_price": prev_p, "new_price": price},
                    )
            self.last_prices[symbol] = price

            # 2. Portfolio Fill Accounting
            if symbol in self.tracked_symbols:
                self.db.update_portfolio_fill(
                    symbol=symbol,
                    side=payload.get("side", "BUY"),
                    fill_price=price,
                    fill_qty=float(payload.get("quantity", 1.0)),
                    current_mark_price=price,
                )

            self.trade_batch.append(payload)

        elif topic == TOPIC_ORDERBOOK_L2:
            self.orderbook_batch.append(payload)

        self.total_consumed += 1

        # Check micro-batch flush triggers
        now = time.perf_counter()
        if (
            len(self.trade_batch) >= self.batch_size
            or len(self.orderbook_batch) >= self.batch_size
            or (now - self.last_flush_time) >= self.flush_interval_sec
        ):
            self.flush()

    def flush(self) -> Tuple[int, int]:
        """Flushes micro-batch buffers directly into the database."""
        n_trades = 0
        n_books = 0

        if self.trade_batch:
            n_trades = self.db.insert_trade_ticks(self.trade_batch)
            self.trade_batch.clear()

        if self.orderbook_batch:
            n_books = self.db.insert_orderbook_snapshots(self.orderbook_batch)
            self.orderbook_batch.clear()

        self.last_flush_time = time.perf_counter()
        return n_trades, n_books

    def consume_from_mock_stream(self, event_stream: List[Dict[str, Any]]) -> int:
        """
        Consumes an in-memory event stream directly for deterministic unit testing.
        """
        for event in event_stream:
            topic = event.get("topic", TOPIC_TRADES_RAW)
            payload = event.get("payload", event)
            self.process_message(topic, payload)

        self.flush()
        return self.total_consumed

    def start(
        self,
        topics: Optional[List[str]] = None,
        max_messages: Optional[int] = None,
        poll_timeout: float = 1.0,
    ) -> None:
        """
        Starts the continuous Kafka consumer polling loop.
        """
        if not self.is_connected or not self.consumer:
            print("[KAFKA CONSUMER ERROR] Cannot start polling: Kafka broker is offline.")
            return

        target_topics = topics or [TOPIC_TRADES_RAW, TOPIC_ORDERBOOK_L2]
        self.consumer.subscribe(target_topics)
        self.is_running = True
        print(f"[CONSUMER STARTED] Subscribed to {target_topics} | Group: {self.group_id}")

        try:
            while self.is_running:
                msg = self.consumer.poll(poll_timeout)
                if msg is None:
                    # Flush on idle timeout if buffer holds records
                    now = time.perf_counter()
                    if (now - self.last_flush_time) >= self.flush_interval_sec:
                        self.flush()
                    continue

                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    else:
                        print(f"[KAFKA CONSUMER ERROR] {msg.error()}")
                        break

                topic = msg.topic()
                val_bytes = msg.value()
                if val_bytes:
                    try:
                        payload = json.loads(val_bytes.decode("utf-8"))
                        self.process_message(topic, payload)
                    except Exception as e:
                        print(f"[CONSUMER DECODE ERROR] {e}")

                if max_messages and self.total_consumed >= max_messages:
                    break

        except KeyboardInterrupt:
            print("[CONSUMER] Stopping on user interrupt.")
        finally:
            self.flush()
            if self.consumer:
                self.consumer.close()
            self.is_running = False
            print(f"[CONSUMER STOPPED] Total consumed: {self.total_consumed}")

    def stop(self) -> None:
        """Stops the active consumer polling loop."""
        self.is_running = False


if __name__ == "__main__":
    consumer = MarketKafkaConsumer(force_mock=True)
    print("QuantPulse Market Kafka Consumer initialized (Mock Mode).")
