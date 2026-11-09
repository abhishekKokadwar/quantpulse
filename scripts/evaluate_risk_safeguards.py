"""
QuantPulse: 3-Tier Risk Safeguards & Decision Arbiter Ground-Truth Benchmark
=============================================================================
Stress-tests the institutional Risk Decision Arbiter against 4 simulated crisis regimes:
1. Tier 1 Soft Sizing Throttle (verifies 50% order cut when daily loss >= 50% of budget)
2. Tier 2 Delta-Neutral Auto-Hedging (verifies automated hedge emission on net delta breach)
3. Tier 2 Stat-Arb Divergence Stop (verifies pair liquidation when Z-score > 3.5 sigma)
4. Tier 3 Emergency Hard Kill Switch (verifies 100% trade veto recall, cancel-all, and lockout)
5. Administrative Unlock Procedure (verifies credentialed reset)
"""

from datetime import datetime, timezone
import math
import os
import sys
import time
from typing import Any, Dict, List

import numpy as np

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from analysis.risk_decision_engine import (
    PortfolioRiskLedger,
    RiskAwareDecisionEngine,
    RiskGuardrailConfig,
    RiskTier,
    StatArbSignal,
)


def run_risk_safeguards_benchmark() -> Dict[str, Any]:
    print("[QuantPulse] Initializing 3-Tier Risk Safeguards Ground-Truth Benchmark...")
    config = RiskGuardrailConfig(
        max_daily_drawdown_pct=0.03,        # 3.0% max drawdown
        min_margin_maintenance_pct=1.10,    # 110% margin maintenance floor
        max_net_delta_usd=100_000.0,        # $100k delta limit
        soft_loss_throttle_pct=0.50,        # 50% loss budget throttle
        stat_arb_divergence_z=3.5,
    )

    ledger = PortfolioRiskLedger(
        initial_capital=1_000_000.0,
        cash=1_000_000.0,
        daily_loss_budget=50_000.0,
    )

    arbiter = RiskAwareDecisionEngine(
        symbol="BTC/USDT",
        config=config,
        portfolio=ledger,
        bucket_size=5.0,
    )

    bids = [(64000.0, 5.0), (63990.0, 5.0)]
    asks = [(64010.0, 5.0), (64020.0, 5.0)]

    latencies_ms = []

    # -------------------------------------------------------------------------
    # Test Stage 1: Normal Operations & Baseline Sizing
    # -------------------------------------------------------------------------
    print(" [Stage 1] Testing Normal Operations & Baseline Sizing...")
    t0 = time.perf_counter()
    dec_normal = arbiter.evaluate(
        timestamp="2026-09-30T12:00:00Z",
        price=64005.0,
        quantity=1.0,
        side="BUY",
        bids=bids,
        asks=asks,
        predicted_return_bps=15.0,
        model_confidence=0.80,
    )
    latencies_ms.append((time.perf_counter() - t0) * 1000.0)

    assert dec_normal.action == "BUY", f"Expected BUY, got {dec_normal.action}"
    assert dec_normal.risk_tier == RiskTier.TIER_0_NORMAL.value
    assert dec_normal.size_multiplier > 0.50, f"Expected normal sizing > 0.5, got {dec_normal.size_multiplier}"
    print(f"   -> Normal execution approved: {dec_normal.action} (Size Multiplier: {dec_normal.size_multiplier:.2f}x)")

    # -------------------------------------------------------------------------
    # Test Stage 2: Tier 1 Soft Loss Sizing Throttle (50% Loss Budget Reached)
    # -------------------------------------------------------------------------
    print(" [Stage 2] Testing Tier 1 Soft Sizing Throttle (Daily Loss >= 50% of Budget)...")
    # Inject $27,500 daily loss (55% of $50,000 budget)
    ledger.realized_daily_pnl = -27_500.0
    ledger.cash -= 27_500.0

    t0 = time.perf_counter()
    dec_throttled = arbiter.evaluate(
        timestamp="2026-09-30T12:01:00Z",
        price=64005.0,
        quantity=1.0,
        side="BUY",
        bids=bids,
        asks=asks,
        predicted_return_bps=18.0,
        model_confidence=0.82,
    )
    latencies_ms.append((time.perf_counter() - t0) * 1000.0)

    assert dec_throttled.risk_tier == RiskTier.TIER_1_THROTTLED.value, f"Expected TIER_1_THROTTLED, got {dec_throttled.risk_tier}"
    assert dec_throttled.size_multiplier <= 0.50, f"Expected throttled size <= 0.50, got {dec_throttled.size_multiplier}"
    assert any("Tier 1 Throttle" in r for r in dec_throttled.reasons)
    print(f"   -> Tier 1 Throttle verified: Size automatically cut to {dec_throttled.size_multiplier:.2f}x")

    # -------------------------------------------------------------------------
    # Test Stage 3: Tier 2 Automated Delta-Neutral Hedging Trigger
    # -------------------------------------------------------------------------
    print(" [Stage 3] Testing Tier 2 Delta-Neutral Auto-Hedging Trigger...")
    # Reset PnL, inject large unhedged long position: 2.5 BTC @ $64,000 = $160,000 net delta (> $100,000 limit)
    ledger.realized_daily_pnl = 0.0
    ledger.cash = 1_000_000.0
    ledger.positions["BTC/USDT"] = 2.5
    ledger.entry_prices["BTC/USDT"] = 64000.0

    t0 = time.perf_counter()
    dec_hedge = arbiter.evaluate(
        timestamp="2026-09-30T12:02:00Z",
        price=64000.0,
        quantity=0.5,
        side="BUY",
        bids=bids,
        asks=asks,
        predicted_return_bps=10.0,
        model_confidence=0.75,
    )
    latencies_ms.append((time.perf_counter() - t0) * 1000.0)

    assert dec_hedge.risk_tier == RiskTier.TIER_2_HEDGING_ACTIVE.value, f"Expected TIER_2_HEDGING_ACTIVE, got {dec_hedge.risk_tier}"
    assert len(dec_hedge.hedge_orders) == 1, "Expected 1 automated hedge order"
    hedge_order = dec_hedge.hedge_orders[0]
    assert hedge_order["action"] == "SELL", f"Expected SELL hedge order, got {hedge_order['action']}"
    assert math.isclose(hedge_order["quantity"], 2.5, abs_tol=0.01), f"Expected hedge qty 2.5, got {hedge_order['quantity']}"
    print(f"   -> Tier 2 Auto-Hedge emitted: {hedge_order['action']} {hedge_order['quantity']} {hedge_order['symbol']} ({hedge_order['reason'][:60]}...)")

    # -------------------------------------------------------------------------
    # Test Stage 4: Tier 2 Cointegrated Stat-Arb Structural Breakdown Stop
    # -------------------------------------------------------------------------
    print(" [Stage 4] Testing Tier 2 Stat-Arb Structural Cointegration Stop (|Z| >= 3.5)...")
    stat_arb_extreme = StatArbSignal(
        pair_symbol="ETH/USDT",
        spread_z_score=3.85,  # Structural blowout
        stat_arb_state="CIRCUIT_BREAKER_STOP",
        hedge_ratio=18.5,
    )

    t0 = time.perf_counter()
    dec_stat_arb = arbiter.evaluate(
        timestamp="2026-09-30T12:03:00Z",
        price=64000.0,
        quantity=0.5,
        side="BUY",
        bids=bids,
        asks=asks,
        predicted_return_bps=20.0,
        model_confidence=0.85,
        stat_arb_signal=stat_arb_extreme,
    )
    latencies_ms.append((time.perf_counter() - t0) * 1000.0)

    assert dec_stat_arb.action == "HOLD", f"Expected HOLD during cointegration stop, got {dec_stat_arb.action}"
    assert not dec_stat_arb.trade_permitted
    assert any("STAT_ARB_DIVERGENCE_STOP" in v for v in dec_stat_arb.veto_reasons)
    assert any(h["action"] == "CLOSE_PAIR_POSITIONS" for h in dec_stat_arb.hedge_orders)
    print("   -> Tier 2 Cointegration Stop verified: Speculative trades vetoed and pair liquidation order emitted.")

    # -------------------------------------------------------------------------
    # Test Stage 5: Tier 3 Emergency Hard Kill Switch (Max Drawdown Breach)
    # -------------------------------------------------------------------------
    print(" [Stage 5] Testing Tier 3 Emergency Hard Kill Switch (Drawdown >= 3.0%)...")
    # Inject severe drawdown: $35,000 unrealized loss on $1M capital (3.5% drawdown)
    ledger.positions["BTC/USDT"] = 10.0
    ledger.entry_prices["BTC/USDT"] = 64000.0
    ledger.market_prices["BTC/USDT"] = 60500.0  # Loss = 10 * -$3,500 = -$35,000

    t0 = time.perf_counter()
    dec_kill = arbiter.evaluate(
        timestamp="2026-09-30T12:04:00Z",
        price=60500.0,
        quantity=1.0,
        side="BUY",
        bids=[(60490.0, 1.0)],
        asks=[(60510.0, 1.0)],
        predicted_return_bps=50.0,  # Aggressive alpha tries to buy the dip
        model_confidence=0.95,
    )
    latencies_ms.append((time.perf_counter() - t0) * 1000.0)

    assert arbiter.kill_switch_active, "Expected kill switch to be active"
    assert dec_kill.action == "HOLD"
    assert not dec_kill.trade_permitted
    assert dec_kill.risk_tier == RiskTier.TIER_3_KILL_SWITCH.value
    assert len(dec_kill.emergency_orders) >= 2, "Expected CANCEL_ALL and LIQUIDATE orders"
    print(f"   -> Tier 3 Kill Switch tripped: {arbiter.kill_switch_reason}")

    # Verify 100% Kill Switch Recall: 100 consecutive subsequent order requests must all be vetoed
    print("   -> Verifying 100% Kill Switch Trade Rejection Recall over 100 inbound orders...")
    vetoed_post_kill = 0
    for i in range(100):
        t0 = time.perf_counter()
        d_locked = arbiter.evaluate(
            timestamp=f"2026-09-30T12:05:{i%60:02d}Z",
            price=60500.0,
            quantity=1.0,
            side="BUY",
            bids=[(60490.0, 1.0)],
            asks=[(60510.0, 1.0)],
            predicted_return_bps=30.0,
            model_confidence=0.90,
        )
        latencies_ms.append((time.perf_counter() - t0) * 1000.0)
        if not d_locked.trade_permitted and d_locked.action == "HOLD":
            vetoed_post_kill += 1

    assert vetoed_post_kill == 100, f"Expected 100/100 orders blocked, got {vetoed_post_kill}"
    print(f"   -> 100/100 post-kill orders successfully blocked (100.00% Safeguard Recall)")

    # -------------------------------------------------------------------------
    # Test Stage 6: Credentialed Administrative Unlock
    # -------------------------------------------------------------------------
    print(" [Stage 6] Testing Credentialed Administrative Unlock...")
    # Unauthorized token fails
    assert not arbiter.reset_kill_switch("INVALID_PASSWORD")
    assert arbiter.kill_switch_active

    # Authorized admin token resets
    assert arbiter.reset_kill_switch(config.admin_kill_token)
    assert not arbiter.kill_switch_active
    print("   -> Administrative unlock verified: System safely disarmed with security credentials.")

    mean_lat = float(np.mean(latencies_ms))
    p95_lat = float(np.percentile(latencies_ms, 95))
    throughput = len(latencies_ms) / (sum(latencies_ms) / 1000.0)

    print("\n" + "=" * 65)
    print(" [BENCHMARK] 3-Tier Risk Safeguards & Decision Arbiter Report")
    print("=" * 65)
    print(" Tier 1 Sizing Throttle:      VERIFIED (50% dynamic size cut on budget breach)")
    print(" Tier 2 Auto-Hedging:         VERIFIED (Delta-neutral offset + Stat-Arb stops)")
    print(" Tier 3 Hard Kill Switch:     VERIFIED (100.00% Trade Rejection Recall)")
    print(" Admin Security Unlock:       VERIFIED (Strict credentialed re-arming)")
    print("-" * 65)
    print(f" Total Decisions Evaluated:   {len(latencies_ms)}")
    print(f" Mean Decision Latency:       {mean_lat:.3f} ms (Gate: < 1.00 ms)")
    print(f" P95 Decision Latency:        {p95_lat:.3f} ms")
    print(f" Processing Throughput:       {throughput:,.1f} decisions/sec")
    print("=" * 65)

    assert mean_lat < 1.0, f"Latency breached sub-millisecond gate: {mean_lat:.3f} ms"
    print("\n[OK] Phase 12 3-Tier Risk Safeguards passed all quantitative and institutional gates!")

    return {
        "status": "PASS",
        "mean_latency_ms": round(mean_lat, 3),
        "p95_latency_ms": round(p95_lat, 3),
        "throughput_ops_sec": round(throughput, 1),
        "kill_switch_recall_pct": 100.0,
    }


if __name__ == "__main__":
    run_risk_safeguards_benchmark()
