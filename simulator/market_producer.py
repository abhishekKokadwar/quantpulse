"""
QuantPulse: High-Throughput Market Kafka Producer
=================================================
Streams multi-asset financial market ticks and Level-2 order book snapshots
to Apache Kafka (KRaft mode).

Core Architectural Invariants:
1. Strict Symbol Partition Keying: `key = symbol.encode('utf-8')` guarantees that
   all trades and order book snapshots for a given asset (e.g. 'BTC/USDT' or 'AAPL')
   land on the exact same Kafka partition in microsecond chronological order.
2. High-Throughput Batching: `compression.type=lz4`, `acks=1`, `linger.ms=5`.
3. Resilient In-Memory Fallback: Operates transparently in offline mock mode when
   the external Kafka broker daemon is offline.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Union

# Prevent OpenBLAS Memory Allocation errors on Windows with multiple processes
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"

script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir in sys.path:
    sys.path.remove(script_dir)

PROJECT_ROOT = os.path.abspath(os.path.join(script_dir, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from simulator.market_simulator import INSTRUMENT_REGISTRY, MarketSimulator, OrderBookSnapshot, TradeTick

DEFAULT_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
TOPIC_TRADES_RAW = os.getenv("KAFKA_TOPIC_TRADES", "market.trades.raw")
TOPIC_ORDERBOOK_L2 = os.getenv("KAFKA_TOPIC_ORDERBOOK", "market.orderbook.l2")
TOPIC_RISK_ALERTS = os.getenv("KAFKA_TOPIC_RISK", "market.risk.alerts")

KAFKA_CLIENT_AVAILABLE = False
try:
    from confluent_kafka import KafkaError, Producer
    KAFKA_CLIENT_AVAILABLE = True
except ImportError:
    KAFKA_CLIENT_AVAILABLE = False


def delivery_callback(err: Any, msg: Any) -> None:
    """Called once per message produced to report delivery status."""
    if err is not None:
        print(f"[KAFKA DELIVERY ERROR] {msg.key() if msg else 'None'}: {err}")


class MarketKafkaProducer:
    """
    Asynchronous, partitioned Kafka producer streaming trade ticks and L2 depth.
    """

    def __init__(
        self,
        bootstrap_servers: str = DEFAULT_BOOTSTRAP_SERVERS,
        client_id: str = "quantpulse-market-producer",
        force_mock: bool = False,
    ):
        self.bootstrap_servers = bootstrap_servers
        self.client_id = client_id
        self.force_mock = force_mock
        self.producer: Optional[Any] = None
        self.is_connected: bool = False
        self.in_memory_buffer: List[Dict[str, Any]] = []
        self.total_emitted: int = 0

        if KAFKA_CLIENT_AVAILABLE and not force_mock:
            try:
                conf = {
                    "bootstrap.servers": self.bootstrap_servers,
                    "client.id": self.client_id,
                    "acks": 1,
                    "retries": 3,
                    "linger.ms": 5,
                    "compression.type": "lz4",
                    "socket.timeout.ms": 2000,
                }
                self.producer = Producer(conf)
                self.is_connected = True
            except Exception as e:
                print(f"[KAFKA PRODUCER NOTICE] Broker unreachable at {bootstrap_servers}: {e}. Operating in memory fallback.")
                self.is_connected = False
        else:
            self.is_connected = False

    def produce_trade(
        self,
        trade: Union[TradeTick, Dict[str, Any]],
        topic: str = TOPIC_TRADES_RAW,
    ) -> bool:
        """
        Publishes a Level-1 execution trade tick.
        Strictly keys message by `symbol` to preserve partition sequence order.
        """
        payload = trade.to_dict() if hasattr(trade, "to_dict") else trade
        symbol = payload["symbol"]
        key_bytes = symbol.encode("utf-8")
        value_bytes = json.dumps(payload).encode("utf-8")

        if self.is_connected and self.producer:
            try:
                self.producer.produce(
                    topic=topic,
                    key=key_bytes,
                    value=value_bytes,
                    on_delivery=delivery_callback,
                )
                self.producer.poll(0)
                self.total_emitted += 1
                return True
            except Exception:
                # Buffer to in-memory on socket disruption
                self.in_memory_buffer.append({"topic": topic, "key": symbol, "payload": payload})
                self.total_emitted += 1
                return False
        else:
            self.in_memory_buffer.append({"topic": topic, "key": symbol, "payload": payload})
            self.total_emitted += 1
            return True

    def produce_orderbook(
        self,
        book: Union[OrderBookSnapshot, Dict[str, Any]],
        topic: str = TOPIC_ORDERBOOK_L2,
    ) -> bool:
        """
        Publishes a Level-2 order book depth snapshot keyed by `symbol`.
        """
        payload = book.to_dict() if hasattr(book, "to_dict") else book
        symbol = payload["symbol"]
        key_bytes = symbol.encode("utf-8")
        value_bytes = json.dumps(payload).encode("utf-8")

        if self.is_connected and self.producer:
            try:
                self.producer.produce(
                    topic=topic,
                    key=key_bytes,
                    value=value_bytes,
                    on_delivery=delivery_callback,
                )
                self.producer.poll(0)
                self.total_emitted += 1
                return True
            except Exception:
                self.in_memory_buffer.append({"topic": topic, "key": symbol, "payload": payload})
                self.total_emitted += 1
                return False
        else:
            self.in_memory_buffer.append({"topic": topic, "key": symbol, "payload": payload})
            self.total_emitted += 1
            return True

    def produce_risk_alert(
        self,
        alert: Dict[str, Any],
        topic: str = TOPIC_RISK_ALERTS,
    ) -> bool:
        """Publishes a high-priority risk or circuit-breaker alert."""
        symbol = alert.get("symbol", "PORTFOLIO")
        key_bytes = symbol.encode("utf-8")
        value_bytes = json.dumps(alert).encode("utf-8")

        if self.is_connected and self.producer:
            try:
                self.producer.produce(
                    topic=topic,
                    key=key_bytes,
                    value=value_bytes,
                    on_delivery=delivery_callback,
                )
                self.producer.poll(0)
                self.total_emitted += 1
                return True
            except Exception:
                self.in_memory_buffer.append({"topic": topic, "key": symbol, "payload": alert})
                self.total_emitted += 1
                return False
        else:
            self.in_memory_buffer.append({"topic": topic, "key": symbol, "payload": alert})
            self.total_emitted += 1
            return True

    def flush(self, timeout: float = 5.0) -> int:
        """Flushes buffered Kafka socket queues."""
        if self.is_connected and self.producer:
            return self.producer.flush(timeout)
        return 0


def start_market_streaming_producer(
    symbols: Optional[List[str]] = None,
    duration_seconds: int = 10,
    ticks_per_second: int = 10,
    bootstrap_servers: str = DEFAULT_BOOTSTRAP_SERVERS,
    force_mock: bool = False,
) -> MarketKafkaProducer:
    """
    Streams simulated high-frequency market data to Kafka.
    """
    target_symbols = symbols or list(INSTRUMENT_REGISTRY.keys())
    sim = MarketSimulator()
    producer = MarketKafkaProducer(bootstrap_servers=bootstrap_servers, force_mock=force_mock)

    mode_str = "KAFKA LIVE" if producer.is_connected else "IN-MEMORY BUFFER"
    print(f"[PRODUCER ACTIVE] Mode: {mode_str} | Symbols: {len(target_symbols)} | Duration: {duration_seconds}s")

    interval = 1.0 / max(1, ticks_per_second)
    total_steps = duration_seconds * ticks_per_second

    start_time = time.perf_counter()
    for _ in range(total_steps):
        for sym in target_symbols:
            sim.step_price(sym, dt_seconds=interval)
            sim.step_spread(sym, dt_seconds=interval)
            book = sim.generate_order_book(sym)
            trade = sim.generate_trade(sym, book=book)

            producer.produce_trade(trade)
            producer.produce_orderbook(book)

        time.sleep(interval)

    producer.flush(timeout=2.0)
    elapsed = time.perf_counter() - start_time
    print(f"[PRODUCER FINISHED] Total Events Emitted: {producer.total_emitted:,} in {elapsed:.2f}s")
    return producer


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="QuantPulse Market Kafka Producer")
    parser.add_argument("--symbols", type=str, default="BTC/USDT,ETH/USDT,AAPL,SPY", help="Comma-separated symbols")
    parser.add_argument("--duration", type=int, default=5, help="Streaming duration in seconds")
    parser.add_argument("--ticks-per-sec", type=int, default=5, help="Cadence of ticks per second")
    parser.add_argument("--mock", action="store_true", help="Force in-memory mock mode")
    args = parser.parse_args()

    symbols_list = args.symbols.split(",")
    start_market_streaming_producer(
        symbols=symbols_list,
        duration_seconds=args.duration,
        ticks_per_second=args.ticks_per_sec,
        force_mock=args.mock,
    )
