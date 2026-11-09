"""
QuantPulse: Unit & Integration Tests for Phase 12 3-Tier Risk Safeguards & Decision Arbiter
============================================================================================
Comprehensive test suite validating:
1. Multi-signal consensus fusion (Alpha Forecaster + Stat-Arb pairs)
2. Conflict resolution (opposing signals neutralize to HOLD)
3. Tier 1 dynamic position sizing and volatility scaling
4. Tier 1 soft drawdown sizing throttle (50% cut when loss >= 50% budget)
5. Tier 1 asset concentration limit throttle
6. Tier 2 automated delta-neutral hedging on portfolio delta breach
7. Tier 2 Stat-Arb cointegration structural divergence stop (|Z| >= 3.5)
8. Tier 3 emergency hard kill switch on max drawdown breach
9. Tier 3 emergency hard kill switch on margin maintenance collapse
10. Tier 3 programmatic API kill switch trip and 100% trade lockout
11. Tier 3 administrative credentialed unlock procedure
12. Sub-millisecond performance gate (< 1.0 ms latency over 3,000 evaluations)
"""

import math
import os
import sys
import time
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from analysis.risk_decision_engine import (
    PortfolioRiskLedger,
    RiskAwareDecisionEngine,
    RiskGuardrailConfig,
    RiskTier,
    StatArbSignal,
    TradeDecision,
)


class TestRiskDecisionSafeguards(unittest.TestCase):
    """
    Exhaustive tests for Phase 12 Decision Arbiter & 3-Tier Pre-Trade Safeguards.
    """

    def setUp(self):
        self.config = RiskGuardrailConfig(
            max_daily_drawdown_pct=0.03,
            min_margin_maintenance_pct=1.10,
            max_net_delta_usd=100_000.0,
            soft_loss_throttle_pct=0.50,
            max_asset_concentration_pct=0.25,
            stat_arb_divergence_z=3.5,
            admin_kill_token="TEST_SECRET_ADMIN_TOKEN_999",
        )
        self.ledger = PortfolioRiskLedger(
            initial_capital=1_000_000.0,
            cash=1_000_000.0,
            daily_loss_budget=50_000.0,
        )
        self.arbiter = RiskAwareDecisionEngine(
            symbol="BTC/USDT",
            config=self.config,
            portfolio=self.ledger,
            bucket_size=5.0,
        )
        self.bids = [(64000.0, 5.0), (63990.0, 5.0)]
        self.asks = [(64010.0, 5.0), (64020.0, 5.0)]

    def test_01_alpha_and_stat_arb_consensus_fusion(self):
        """
        Validates signal consensus:
        When Alpha predicts BUY and Stat-Arb signals LONG_SPREAD,
        composite confidence is boosted by +15% and candidate is BUY.
        """
        stat_arb = StatArbSignal(
            pair_symbol="ETH/USDT",
            spread_z_score=-2.45,
            stat_arb_state="LONG_SPREAD",
            hedge_ratio=18.2,
        )

        dec = self.arbiter.evaluate(
            timestamp="2026-09-30T10:00:00Z",
            price=64005.0,
            quantity=1.0,
            side="BUY",
            bids=self.bids,
            asks=self.asks,
            predicted_return_bps=12.0,
            model_confidence=0.75,
            stat_arb_signal=stat_arb,
        )

        self.assertEqual(dec.candidate_action, "BUY")
        self.assertEqual(dec.action, "BUY")
        self.assertTrue(dec.trade_permitted)
        # 0.75 base + 0.15 boost = 0.90
        self.assertAlmostEqual(dec.confidence, 0.90, places=2)
        self.assertTrue(any("Consensus" in r for r in dec.reasons))

    def test_02_conflicting_signals_neutral_resolution(self):
        """
        Validates conflict resolution:
        When Alpha predicts BUY but Stat-Arb indicates overvalued SHORT_SPREAD,
        the conflicting signals neutralize to HOLD.
        """
        stat_arb = StatArbSignal(
            pair_symbol="ETH/USDT",
            spread_z_score=+2.80,  # Overvalued spread
            stat_arb_state="SHORT_SPREAD",
            hedge_ratio=18.2,
        )

        dec = self.arbiter.evaluate(
            timestamp="2026-09-30T10:00:01Z",
            price=64005.0,
            quantity=1.0,
            side="BUY",
            bids=self.bids,
            asks=self.asks,
            predicted_return_bps=15.0,  # Bullish alpha
            model_confidence=0.80,
            stat_arb_signal=stat_arb,
        )

        self.assertEqual(dec.candidate_action, "HOLD")
        self.assertEqual(dec.action, "HOLD")
        self.assertTrue(any("Signal Conflict" in r for r in dec.reasons))

    def test_03_tier1_dynamic_sizing_and_volatility_collar(self):
        """
        Validates Tier 1 position sizing:
        Higher model confidence yields larger Kelly multiplier.
        """
        dec_high_conf = self.arbiter.evaluate(
            timestamp="2026-09-30T10:00:02Z",
            price=64005.0,
            quantity=1.0,
            side="BUY",
            bids=self.bids,
            asks=self.asks,
            predicted_return_bps=20.0,
            model_confidence=0.90,
        )

        dec_low_conf = self.arbiter.evaluate(
            timestamp="2026-09-30T10:00:03Z",
            price=64005.0,
            quantity=1.0,
            side="BUY",
            bids=self.bids,
            asks=self.asks,
            predicted_return_bps=5.0,
            model_confidence=0.58,
        )

        self.assertGreater(dec_high_conf.size_multiplier, dec_low_conf.size_multiplier)
        self.assertEqual(dec_high_conf.risk_tier, RiskTier.TIER_0_NORMAL.value)

    def test_04_tier1_soft_drawdown_sizing_throttle(self):
        """
        Validates Tier 1 soft loss throttle:
        When daily loss reaches >= 50% of loss budget, size is cut by 50%.
        """
        # Inject $26,000 daily loss (52% of $50,000 budget)
        self.ledger.realized_daily_pnl = -26_000.0

        dec = self.arbiter.evaluate(
            timestamp="2026-09-30T10:00:04Z",
            price=64005.0,
            quantity=1.0,
            side="BUY",
            bids=self.bids,
            asks=self.asks,
            predicted_return_bps=15.0,
            model_confidence=0.80,
        )

        self.assertEqual(dec.risk_tier, RiskTier.TIER_1_THROTTLED.value)
        self.assertLessEqual(dec.size_multiplier, 0.50)
        self.assertTrue(any("Tier 1 Throttle" in r for r in dec.reasons))

    def test_05_tier1_concentration_limit_throttling(self):
        """
        Validates Tier 1 concentration throttle:
        When single-asset exposure reaches >= 80% of limit (0.80 * 25% = 20%),
        size is throttled to Tier 1.
        """
        # Hold $224,000 notional of BTC on $1M capital = 22.4% concentration (>= 20% limit threshold)
        self.config.max_net_delta_usd = 500_000.0
        self.ledger.positions["BTC/USDT"] = 3.5
        self.ledger.entry_prices["BTC/USDT"] = 64000.0
        self.ledger.market_prices["BTC/USDT"] = 64000.0

        dec = self.arbiter.evaluate(
            timestamp="2026-09-30T10:00:05Z",
            price=64000.0,
            quantity=0.5,
            side="BUY",
            bids=self.bids,
            asks=self.asks,
            predicted_return_bps=10.0,
            model_confidence=0.75,
        )

        self.assertEqual(dec.risk_tier, RiskTier.TIER_1_THROTTLED.value)
        self.assertLessEqual(dec.size_multiplier, 0.50)
        self.assertTrue(any("concentration" in r.lower() for r in dec.reasons))

    def test_06_tier2_portfolio_delta_auto_hedge(self):
        """
        Validates Tier 2 auto-hedging:
        When portfolio net delta exceeds $100,000, an offsetting hedge order is emitted.
        """
        # Long 2.0 BTC @ $64,000 = $128,000 net delta (> $100k cap)
        self.ledger.positions["BTC/USDT"] = 2.0
        self.ledger.entry_prices["BTC/USDT"] = 64000.0
        self.ledger.market_prices["BTC/USDT"] = 64000.0

        dec = self.arbiter.evaluate(
            timestamp="2026-09-30T10:00:06Z",
            price=64000.0,
            quantity=0.5,
            side="BUY",
            bids=self.bids,
            asks=self.asks,
            predicted_return_bps=10.0,
            model_confidence=0.70,
        )

        self.assertEqual(dec.risk_tier, RiskTier.TIER_2_HEDGING_ACTIVE.value)
        self.assertEqual(len(dec.hedge_orders), 1)
        hedge = dec.hedge_orders[0]
        self.assertEqual(hedge["action"], "SELL")
        self.assertEqual(hedge["symbol"], "BTC/USDT")
        self.assertAlmostEqual(hedge["quantity"], 2.0, places=2)

    def test_07_tier2_stat_arb_divergence_circuit_breaker(self):
        """
        Validates Tier 2 Stat-Arb cointegration divergence stop:
        When spread |Z| >= 3.5, trade is vetoed and pair liquidation order is emitted.
        """
        broken_pair = StatArbSignal(
            pair_symbol="ETH/USDT",
            spread_z_score=3.75,
            stat_arb_state="CIRCUIT_BREAKER_STOP",
            hedge_ratio=18.0,
        )

        dec = self.arbiter.evaluate(
            timestamp="2026-09-30T10:00:07Z",
            price=64000.0,
            quantity=0.5,
            side="BUY",
            bids=self.bids,
            asks=self.asks,
            predicted_return_bps=20.0,
            model_confidence=0.85,
            stat_arb_signal=broken_pair,
        )

        self.assertEqual(dec.action, "HOLD")
        self.assertFalse(dec.trade_permitted)
        self.assertEqual(dec.risk_tier, RiskTier.TIER_2_HEDGING_ACTIVE.value)
        self.assertTrue(any(h["action"] == "CLOSE_PAIR_POSITIONS" for h in dec.hedge_orders))
        self.assertTrue(any("STAT_ARB_DIVERGENCE_STOP" in v for v in dec.veto_reasons))

    def test_08_tier3_drawdown_emergency_kill_switch(self):
        """
        Validates Tier 3 hard emergency kill switch on max drawdown breach:
        Trips kill switch, sets action to HOLD, and generates CANCEL_ALL and LIQUIDATE.
        """
        # Inject $35,000 drawdown on $1M capital (3.5% >= 3.0% cap)
        self.ledger.positions["BTC/USDT"] = 10.0
        self.ledger.entry_prices["BTC/USDT"] = 64000.0
        self.ledger.market_prices["BTC/USDT"] = 60500.0

        dec = self.arbiter.evaluate(
            timestamp="2026-09-30T10:00:08Z",
            price=60500.0,
            quantity=1.0,
            side="BUY",
            bids=[(60490.0, 1.0)],
            asks=[(60510.0, 1.0)],
            predicted_return_bps=40.0,
            model_confidence=0.90,
        )

        self.assertTrue(self.arbiter.kill_switch_active)
        self.assertEqual(dec.action, "HOLD")
        self.assertFalse(dec.trade_permitted)
        self.assertEqual(dec.risk_tier, RiskTier.TIER_3_KILL_SWITCH.value)
        self.assertGreaterEqual(len(dec.emergency_orders), 2)
        order_types = [e["order_type"] for e in dec.emergency_orders]
        self.assertIn("CANCEL_ALL_OPEN_ORDERS", order_types)
        self.assertIn("LIQUIDATE_ALL_POSITIONS", order_types)

    def test_09_tier3_margin_maintenance_collapse_halt(self):
        """
        Validates Tier 3 hard kill switch when margin ratio drops below 110%.
        """
        # Excessive leverage: $9,500,000 position on $900k equity -> required margin = $950,000
        # Margin ratio = 900,000 / 950,000 = 0.947 (< 1.10)
        self.ledger.cash = 900_000.0
        self.ledger.positions["BTC/USDT"] = 150.0
        self.ledger.entry_prices["BTC/USDT"] = 63333.33
        self.ledger.market_prices["BTC/USDT"] = 63333.33

        dec = self.arbiter.evaluate(
            timestamp="2026-09-30T10:00:09Z",
            price=63333.33,
            quantity=1.0,
            side="BUY",
            bids=self.bids,
            asks=self.asks,
            predicted_return_bps=10.0,
            model_confidence=0.80,
        )

        self.assertTrue(self.arbiter.kill_switch_active)
        self.assertEqual(dec.action, "HOLD")
        self.assertEqual(dec.risk_tier, RiskTier.TIER_3_KILL_SWITCH.value)
        self.assertTrue(any("MARGIN_CALL_COLLAPSE" in v for v in dec.veto_reasons))

    def test_10_tier3_manual_api_kill_switch_and_lockout(self):
        """
        Validates programmatic manual trip of emergency kill switch
        and confirms subsequent order requests are 100% blocked.
        """
        res = self.arbiter.trigger_manual_kill_switch("CHIEF_RISK_OFFICER_OVERRIDE")
        self.assertEqual(res["status"], "EMERGENCY_HALT")
        self.assertTrue(self.arbiter.kill_switch_active)

        for i in range(20):
            dec = self.arbiter.evaluate(
                timestamp=f"2026-09-30T10:01:{i:02d}Z",
                price=64000.0,
                quantity=1.0,
                side="BUY",
                bids=self.bids,
                asks=self.asks,
                predicted_return_bps=30.0,
                model_confidence=0.95,
            )
            self.assertEqual(dec.action, "HOLD")
            self.assertFalse(dec.trade_permitted)
            self.assertEqual(dec.size_multiplier, 0.0)
            self.assertTrue(any("KILL_SWITCH_ACTIVE" in v for v in dec.veto_reasons))

    def test_11_kill_switch_manual_reset_authorization(self):
        """
        Validates security token authorization for resetting the kill switch.
        """
        self.arbiter.trigger_manual_kill_switch()
        self.assertTrue(self.arbiter.kill_switch_active)

        # Invalid token must fail
        self.assertFalse(self.arbiter.reset_kill_switch("WRONG_TOKEN"))
        self.assertTrue(self.arbiter.kill_switch_active)

        # Valid token must succeed
        self.assertTrue(self.arbiter.reset_kill_switch("TEST_SECRET_ADMIN_TOKEN_999"))
        self.assertFalse(self.arbiter.kill_switch_active)

    def test_12_sub_millisecond_arbitration_latency_gate(self):
        """
        Performance invariant:
        Evaluates 3,000 multi-signal decisions with full 3-tier checks.
        Asserts mean latency < 1.0 ms (typical < 0.15 ms).
        """
        latencies = []
        stat_arb = StatArbSignal(
            pair_symbol="ETH/USDT",
            spread_z_score=-1.2,
            stat_arb_state="IDLE",
            hedge_ratio=18.0,
        )

        for i in range(3000):
            t0 = time.perf_counter()
            dec = self.arbiter.evaluate(
                timestamp=f"2026-09-30T10:00:{i%60:02d}Z",
                price=64000.0 + (i % 10),
                quantity=0.5,
                side="BUY" if i % 2 == 0 else "SELL",
                bids=self.bids,
                asks=self.asks,
                predicted_return_bps=5.0,
                model_confidence=0.70,
                stat_arb_signal=stat_arb,
                timestamp_epoch=float(1000 + i),
            )
            latencies.append((time.perf_counter() - t0) * 1000.0)

        mean_lat = sum(latencies) / len(latencies)
        p99_lat = sorted(latencies)[int(0.99 * len(latencies))]
        throughput = len(latencies) / (sum(latencies) / 1000.0)

        print(f"\n[Test Gate 12] 3,000 Decisions: Mean Latency = {mean_lat:.3f} ms, P99 = {p99_lat:.3f} ms, Throughput = {throughput:,.1f} ops/sec")
        self.assertLess(mean_lat, 1.0, f"Mean latency {mean_lat:.3f}ms breached sub-millisecond gate!")


if __name__ == "__main__":
    unittest.main()
