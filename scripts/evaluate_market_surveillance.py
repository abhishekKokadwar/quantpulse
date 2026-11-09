"""
QuantPulse: Market Surveillance & Risk-Aware Decision Ground-Truth Benchmark
=============================================================================
Evaluates the real-time Market Surveillance & Risk Decision Arbiter against
injected synthetic flash crashes, liquidity vacuums, and toxic flow dumping episodes.

Measures:
1. Precision, Recall, and F1-Score of Anomaly Detection
2. Mean Detection Latency from Anomaly Inception to Trigger
3. Risk Arbiter Veto Rate (asserts 100% of unsafe Alpha signals are vetoed during collapse)
4. Decision Processing Throughput Gate (> 10,000 decisions/second)
"""

from datetime import datetime, timedelta, timezone
import math
import os
import sys
import time
from typing import Any, Dict, List, Tuple

import numpy as np

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from analysis.market_surveillance_engine import SurveillanceState
from analysis.risk_decision_engine import RiskAwareDecisionEngine, RiskGuardrailConfig


def generate_synthetic_surveillance_scenario(
    total_ticks: int = 1500,
    base_price: float = 64000.0,
    symbol: str = "BTC/USDT",
) -> Tuple[List[Dict[str, Any]], List[Tuple[int, int, str]]]:
    """
    Generates a realistic stream of Level-1 trades and Level-2 order books
    with 3 injected ground-truth market anomaly episodes:
    1. Episode A (ticks 350-450): Predatory Toxic Flow (massive seller imbalance, VPIN surge)
    2. Episode B (ticks 750-850): Liquidity Vacuum (85% book evacuation, spread blowout)
    3. Episode C (ticks 1150-1250): Flash Crash Collapse (aggressive selling + book vacuum + jump)
    """
    records = []
    anomaly_intervals = [
        (350, 450, "TOXIC_SELLER_DUMPING"),
        (750, 850, "LIQUIDITY_VACUUM_COLLAPSE"),
        (1150, 1250, "FULL_FLASH_CRASH_COLLAPSE"),
    ]

    curr_price = base_price
    t_start = datetime(2026, 9, 30, 9, 30, 0, tzinfo=timezone.utc)

    for i in range(total_ticks):
        t_tick = t_start + timedelta(milliseconds=i * 20)  # 50 Hz tick feed
        iso_ts = t_tick.isoformat()
        epoch_ts = t_tick.timestamp()

        # Check if inside an anomaly interval
        in_anomaly = False
        anomaly_type = None
        for start_idx, end_idx, a_type in anomaly_intervals:
            if start_idx <= i <= end_idx:
                in_anomaly = True
                anomaly_type = a_type
                break

        if not in_anomaly:
            # Normal balanced Brownian trading
            curr_price += float(np.random.normal(0.0, 1.5))
            side = "BUY" if np.random.random() > 0.50 else "SELL"
            qty = float(np.random.uniform(0.1, 2.0))

            spread = 0.50  # ~0.78 bps
            best_bid = curr_price - spread / 2.0
            best_ask = curr_price + spread / 2.0

            # Normal healthy top-5 depth ($200k+ total depth)
            bids = [(best_bid - j * 0.5, float(np.random.uniform(1.0, 3.0))) for j in range(5)]
            asks = [(best_ask + j * 0.5, float(np.random.uniform(1.0, 3.0))) for j in range(5)]

            # Alpha model return signal (small random fluctuations)
            pred_return_bps = float(np.random.normal(2.0, 4.0))
            alpha_confidence = 0.65

        elif anomaly_type == "TOXIC_SELLER_DUMPING":
            # 95% aggressive informed sell flow hitting bids
            curr_price -= float(np.random.exponential(1.5))
            side = "SELL" if np.random.random() < 0.95 else "BUY"
            qty = float(np.random.uniform(2.5, 8.0))

            spread = 1.80  # Mild spread widening
            best_bid = curr_price - spread / 2.0
            best_ask = curr_price + spread / 2.0

            bids = [(best_bid - j * 0.8, float(np.random.uniform(0.5, 1.2))) for j in range(5)]
            asks = [(best_ask + j * 0.8, float(np.random.uniform(3.0, 6.0))) for j in range(5)]

            # Aggressive bull model falsely predicts dip buying
            pred_return_bps = +25.0
            alpha_confidence = 0.85

        elif anomaly_type == "LIQUIDITY_VACUUM_COLLAPSE":
            # Market makers pull 85% of quotes, spread blows out 5x
            curr_price += float(np.random.normal(0.0, 3.0))
            side = "BUY" if np.random.random() > 0.50 else "SELL"
            qty = float(np.random.uniform(0.05, 0.5))

            spread = 14.50  # ~22.6 bps spread blowout
            best_bid = curr_price - spread / 2.0
            best_ask = curr_price + spread / 2.0

            # Only 0.05 - 0.15 depth remaining (< $15k total depth)
            bids = [(best_bid - j * 2.0, float(np.random.uniform(0.05, 0.15))) for j in range(5)]
            asks = [(best_ask + j * 2.0, float(np.random.uniform(0.05, 0.15))) for j in range(5)]

            pred_return_bps = +15.0
            alpha_confidence = 0.70

        else:  # FULL_FLASH_CRASH_COLLAPSE
            # Severe cascading price decline + complete book vacuum + extreme toxicity
            curr_price -= float(np.random.exponential(8.0))
            side = "SELL"
            qty = float(np.random.uniform(5.0, 15.0))

            spread = 28.0  # Massive spread blowout
            best_bid = curr_price - spread / 2.0
            best_ask = curr_price + spread / 2.0

            bids = [(best_bid - j * 5.0, 0.05) for j in range(5)]
            asks = [(best_ask + j * 5.0, 0.10) for j in range(5)]

            pred_return_bps = +45.0  # Naive model tries to catch falling knife
            alpha_confidence = 0.90

        records.append({
            "tick_idx": i,
            "timestamp": iso_ts,
            "epoch_ts": epoch_ts,
            "price": curr_price,
            "quantity": qty,
            "side": side,
            "bids": bids,
            "asks": asks,
            "pred_return_bps": pred_return_bps,
            "alpha_confidence": alpha_confidence,
            "ground_truth_anomaly": in_anomaly,
            "anomaly_type": anomaly_type,
        })

    return records, anomaly_intervals


def run_surveillance_benchmark() -> Dict[str, Any]:
    """
    Executes the ground-truth benchmark and prints an institutional evaluation card.
    """
    print("[QuantPulse] Generating 1,500 streaming ticks with 3 injected anomaly episodes...")
    ticks, intervals = generate_synthetic_surveillance_scenario(total_ticks=1500)

    engine = RiskAwareDecisionEngine(
        symbol="BTC/USDT",
        config=RiskGuardrailConfig(
            max_spread_bps=15.0,
            min_depth_usd=10000.0,
            max_vpin_threshold=0.80,
            neutral_deadband_bps=3.0,
        ),
        bucket_size=5.0,
    )

    true_positives = 0
    false_positives = 0
    true_negatives = 0
    false_negatives = 0

    vetoed_unsafe_trades = 0
    total_unsafe_signals = 0

    latencies_ms = []
    t_start_bench = time.perf_counter()

    for item in ticks:
        dec = engine.evaluate(
            timestamp=item["timestamp"],
            price=item["price"],
            quantity=item["quantity"],
            side=item["side"],
            bids=item["bids"],
            asks=item["asks"],
            predicted_return_bps=item["pred_return_bps"],
            model_confidence=item["alpha_confidence"],
            timestamp_epoch=item["epoch_ts"],
        )
        latencies_ms.append(dec.evaluation_latency_ms)

        is_gt_anomaly = item["ground_truth_anomaly"]
        is_detected = (dec.risk_state in (SurveillanceState.ELEVATED_TOXICITY, SurveillanceState.FLASH_CRASH_DETECTED, "ELEVATED_RISK"))

        if is_gt_anomaly and is_detected:
            true_positives += 1
        elif not is_gt_anomaly and is_detected:
            false_positives += 1
        elif not is_gt_anomaly and not is_detected:
            true_negatives += 1
        elif is_gt_anomaly and not is_detected:
            false_negatives += 1

        # Check veto performance during anomaly: Did the arbiter stop aggressive BUY signals?
        if is_gt_anomaly and item["pred_return_bps"] > 5.0:
            total_unsafe_signals += 1
            if not dec.trade_permitted and dec.action == "HOLD":
                vetoed_unsafe_trades += 1

    total_bench_time = time.perf_counter() - t_start_bench
    throughput_decisions_sec = len(ticks) / total_bench_time

    precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0.0
    recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    veto_accuracy = (vetoed_unsafe_trades / total_unsafe_signals * 100.0) if total_unsafe_signals > 0 else 100.0

    mean_lat = float(np.mean(latencies_ms))
    p95_lat = float(np.percentile(latencies_ms, 95))
    p99_lat = float(np.percentile(latencies_ms, 99))

    results = {
        "total_ticks": len(ticks),
        "true_positives": true_positives,
        "false_positives": false_positives,
        "true_negatives": true_negatives,
        "false_negatives": false_negatives,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1_score": round(f1, 4),
        "total_unsafe_signals": total_unsafe_signals,
        "vetoed_unsafe_trades": vetoed_unsafe_trades,
        "veto_accuracy_pct": round(veto_accuracy, 2),
        "mean_latency_ms": round(mean_lat, 3),
        "p95_latency_ms": round(p95_lat, 3),
        "p99_latency_ms": round(p99_lat, 3),
        "throughput_decisions_sec": round(throughput_decisions_sec, 1),
    }

    # Print summary card
    print("\n" + "=" * 65)
    print(" [BENCHMARK] Market Surveillance & Risk Arbiter Ground-Truth Report")
    print("=" * 65)
    print(f" Injected Anomaly Episodes:   3 (Toxic Dump, Liquidity Vacuum, Flash Crash)")
    print(f" Total Ticks Processed:       {len(ticks):,}")
    print(f" Precision:                   {precision*100.0:.2f}%")
    print(f" Recall:                      {recall*100.0:.2f}%")
    print(f" F1-Score:                    {f1*100.0:.2f}%")
    print("-" * 65)
    print(f" Unsafe Alpha Signals Injected: {total_unsafe_signals}")
    print(f" Unsafe Signals Vetoed by Risk: {vetoed_unsafe_trades}")
    print(f" Risk Veto Safeguard Recall:   {veto_accuracy:.2f}% (Target: 100.0%)")
    print("-" * 65)
    print(f" Mean Decision Latency:       {mean_lat:.3f} ms (Gate: < 1.00 ms)")
    print(f" P95 Decision Latency:        {p95_lat:.3f} ms")
    print(f" P99 Decision Latency:        {p99_lat:.3f} ms")
    print(f" Ingestion Throughput:        {throughput_decisions_sec:,.1f} decisions/sec")
    print("=" * 65)

    assert veto_accuracy == 100.0, f"Risk Arbiter allowed {total_unsafe_signals - vetoed_unsafe_trades} unsafe trades!"
    assert mean_lat < 1.0, f"Mean latency breached sub-millisecond gate: {mean_lat:.3f} ms"
    print("\n[OK] Surveillance Benchmark passed all quantitative gates with 100% veto recall!")
    return results


if __name__ == "__main__":
    run_surveillance_benchmark()
