"""
QuantPulse: High-Performance Historical Tick Replay Engine
==========================================================
Replays synthesized or historical tick streams and Level-2 order book snapshots
for algorithmic backtesting, streaming Kafka producer injection, or real-time simulation.

Modes supported:
1. 'realtime': Emits ticks respecting actual historical inter-arrival latencies.
2. 'accelerated': Replays at Nx speed (e.g. 10x, 100x) via calibrated time scaling.
3. 'batch': Emits ticks as fast as memory/CPU allows for high-throughput backtests.
"""

import csv
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Generator, Iterator, List, Optional

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from simulator.market_simulator import MarketSimulator


class HistoricalTickReplayEngine:
    """
    High-performance financial tick replay engine supporting realtime,
    accelerated, and batch playback of multi-asset market data.
    """

    def __init__(
        self,
        simulator: Optional[MarketSimulator] = None,
        source_records: Optional[List[Dict[str, Any]]] = None,
        speed_multiplier: float = 1.0,
        mode: str = "batch",  # 'batch', 'accelerated', 'realtime'
    ):
        self.simulator = simulator or MarketSimulator()
        self.source_records = source_records
        self.speed_multiplier = max(0.001, speed_multiplier)
        self.mode = mode
        self.is_running = False
        self.total_emitted = 0

    @classmethod
    def from_csv(cls, csv_path: str, mode: str = "batch", speed_multiplier: float = 1.0) -> "HistoricalTickReplayEngine":
        """Loads historical ticks from a CSV file into the replay engine."""
        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"Historical tick CSV not found: {csv_path}")

        records: List[Dict[str, Any]] = []
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Cast numeric fields
                for num_col in ["price", "quantity", "notional_usd", "spread", "mid_price", "micro_price", "order_flow_imbalance"]:
                    if num_col in row and row[num_col] != "":
                        try:
                            row[num_col] = float(row[num_col])
                        except ValueError:
                            pass
                records.append(row)

        return cls(source_records=records, mode=mode, speed_multiplier=speed_multiplier)

    def stream(
        self,
        symbols: Optional[List[str]] = None,
        duration_seconds: int = 60,
        ticks_per_second: int = 10,
        callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Streams market events either from pre-loaded historical records or by
        advancing the internal MarketSimulator in the specified playback mode.
        """
        self.is_running = True
        self.total_emitted = 0
        start_wall_time = time.perf_counter()

        # Branch 1: Replay from source records
        if self.source_records is not None and len(self.source_records) > 0:
            target_records = self.source_records
            if symbols:
                sym_set = set(symbols)
                target_records = [r for r in self.source_records if r.get("symbol") in sym_set]

            prev_ts = None
            for record in target_records:
                if not self.is_running:
                    break

                # Handle timing for realtime / accelerated
                if self.mode in ("realtime", "accelerated"):
                    curr_ts_str = record.get("timestamp")
                    if curr_ts_str:
                        try:
                            curr_ts = datetime.fromisoformat(curr_ts_str)
                            if prev_ts is not None:
                                dt_delta = (curr_ts - prev_ts).total_seconds()
                                if dt_delta > 0:
                                    sleep_sec = dt_delta / self.speed_multiplier if self.mode == "accelerated" else dt_delta
                                    # Cap max sleep to 1s to prevent hanging
                                    time.sleep(min(1.0, sleep_sec))
                            prev_ts = curr_ts
                        except Exception:
                            pass

                self.total_emitted += 1
                if callback:
                    callback(record)
                yield record

        # Branch 2: Synthetic on-the-fly streaming from MarketSimulator
        else:
            tick_gen = self.simulator.generate_tick_stream(
                symbols=symbols,
                duration_seconds=duration_seconds,
                ticks_per_second=ticks_per_second,
            )

            for event in tick_gen:
                if not self.is_running:
                    break

                if self.mode in ("realtime", "accelerated"):
                    interval = 1.0 / max(1, ticks_per_second)
                    sleep_time = interval / self.speed_multiplier if self.mode == "accelerated" else interval
                    time.sleep(min(0.5, sleep_time))

                self.total_emitted += 1
                if callback:
                    callback(event)
                yield event

        self.is_running = False

    def stop(self) -> None:
        """Stops the active streaming replay."""
        self.is_running = False


if __name__ == "__main__":
    replay = HistoricalTickReplayEngine(mode="batch")
    count = 0
    start = time.perf_counter()
    for tick in replay.stream(symbols=["BTC/USDT", "AAPL"], duration_seconds=5, ticks_per_second=100):
        count += 1
    elapsed = time.perf_counter() - start
    print(f"Replay completed: {count} events emitted in {elapsed:.4f}s ({count / max(0.001, elapsed):.1f} ticks/sec).")
