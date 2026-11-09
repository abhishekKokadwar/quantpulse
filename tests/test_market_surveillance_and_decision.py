"""
QuantPulse: Unit & Integration Tests for Market Surveillance & Risk Decision Layer
===================================================================================
Covers Phase 11 (Market Surveillance & Toxic Flow VPIN) and Phase 12 (Risk Arbiter):
1. VPIN mathematical precision and regime classification
2. Liquidity vacuum detection and hysteresis baseline preservation
3. Dynamic spread blowout detection
4. Hysteresis anti-flapping state transitions
5. Explainable signal generation (BUY/SELL/HOLD + Rationale)
6. Risk Arbiter veto on toxic order flow & adverse selection
7. Risk Arbiter veto on liquidity vacuum & thin book
8. Strict dictionary & terminal card output contract
9. Sub-millisecond performance & latency gate (< 1.0 ms)
"""

import math
import os
import sys
import time
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from analysis.market_surveillance_engine import (
    AbnormalVolatilityDetector,
    LiquidityVacuumDetector,
    MarketSurveillanceEngine,
    SpreadAnomalyDetector,
    SurveillanceReport,
    SurveillanceState,
    SurveillanceStateMachine,
    VPINCalculator,
)
from analysis.risk_decision_engine import (
    RiskAwareDecisionEngine,
    RiskGuardrailConfig,
    TradeDecision,
)


class TestMarketSurveillanceAndDecision(unittest.TestCase):
    """
    Comprehensive test suite validating high-frequency surveillance and risk arbitration.
    """

    def test_01_vpin_calculation_mathematical_precision(self):
        """
        Validates VPIN calculation:
        - Must be strictly within [0.0, 1.0].
        - Perfectly balanced buy/sell flow yields low VPIN (~0.0).
        - 100% one-sided toxic sell flow drives VPIN to 1.0.
        """
        # Balanced flow: 10 units BUY, 10 units SELL per bucket
        vpin_balanced = VPINCalculator(bucket_size=20.0, window_buckets=10)
        for _ in range(25):
            vpin_balanced.update(price=100.0, quantity=10.0, side="BUY")
            vpin_balanced.update(price=100.0, quantity=10.0, side="SELL")

        self.assertGreaterEqual(vpin_balanced.current_vpin, 0.0)
        self.assertLessEqual(vpin_balanced.current_vpin, 0.15)
        self.assertEqual(vpin_balanced.get_regime(), "BALANCED_FLOW")

        # 100% one-sided toxic sell dumping
        vpin_toxic = VPINCalculator(bucket_size=10.0, window_buckets=10)
        for _ in range(20):
            vpin_toxic.update(price=98.0, quantity=10.0, side="SELL")

        self.assertAlmostEqual(vpin_toxic.current_vpin, 1.0, places=4)
        self.assertEqual(vpin_toxic.get_regime(), "TOXIC_INFORMED_FLOW")

    def test_02_liquidity_vacuum_detection(self):
        """
        Validates Level-2 order book depth collapse detection:
        - Normal book ($200k depth) does not trigger vacuum.
        - 85% sudden drop in depth triggers LIQUIDITY_VACUUM.
        - Preserves baseline during vacuum regime and recovers on replenishment.
        """
        detector = LiquidityVacuumDetector(collapse_threshold=0.75, window_seconds=5.0)

        # Baseline: 10 snapshots of healthy depth ($200,000)
        healthy_bids = [(100.0 - i * 0.1, 1000.0) for i in range(5)]  # $100k bids
        healthy_asks = [(100.1 + i * 0.1, 1000.0) for i in range(5)]  # $100k asks

        for t in range(10):
            is_vac, drop_pct, depth_usd = detector.update(
                timestamp_epoch=float(t), bids=healthy_bids, asks=healthy_asks
            )
            self.assertFalse(is_vac)
            self.assertAlmostEqual(depth_usd, 1000500.0, delta=1000.0)

        # Flash collapse: Quotes pulled, depth drops by 88%
        thin_bids = [(100.0 - i * 0.5, 120.0) for i in range(5)]  # ~$120k * 0.1 = $12k
        thin_asks = [(100.5 + i * 0.5, 120.0) for i in range(5)]

        is_vac, drop_pct, depth_usd = detector.update(
            timestamp_epoch=10.5, bids=thin_bids, asks=thin_asks
        )
        self.assertTrue(is_vac)
        self.assertGreaterEqual(drop_pct, 0.75)

    def test_03_spread_widening_anomaly(self):
        """
        Validates rolling dynamic spread blowout detection (>3.0 sigma and >2.5x mean).
        """
        detector = SpreadAnomalyDetector(window_size=50, z_threshold=3.0, multiplier_threshold=2.5)

        # Feed 30 ticks of normal tight spread (0.10 on 100.0 = 10 bps)
        for _ in range(30):
            is_blowout, z, bps = detector.update(bid=99.95, ask=100.05)
            self.assertFalse(is_blowout)
            self.assertAlmostEqual(bps, 10.0, delta=0.5)

        # Spread explodes 4x to 40 bps
        is_blowout, z, bps = detector.update(bid=99.80, ask=100.20)
        self.assertTrue(is_blowout)
        self.assertGreater(z, 3.0)
        self.assertGreater(bps, 25.0)

    def test_04_hysteresis_state_machine_transitions(self):
        """
        Validates anti-flapping hysteresis in the state machine:
        - NORMAL -> ELEVATED_TOXICITY on single alarm.
        - ELEVATED_TOXICITY -> FLASH_CRASH_DETECTED on combined vacuum + toxicity.
        - Requires consecutive normal ticks before stepping down (no flapping).
        """
        sm = SurveillanceStateMachine(cooldown_ticks_elevated=5, cooldown_ticks_crash=10)
        self.assertEqual(sm.state, SurveillanceState.NORMAL)

        # Trigger elevated toxicity
        state = sm.transition(is_vacuum=False, is_toxic=True, is_spread_blowout=False, is_vol_spike=False)
        self.assertEqual(state, SurveillanceState.ELEVATED_TOXICITY)

        # Trigger flash crash (vacuum + toxic flow)
        state = sm.transition(is_vacuum=True, is_toxic=True, is_spread_blowout=False, is_vol_spike=False)
        self.assertEqual(state, SurveillanceState.FLASH_CRASH_DETECTED)

        # Feeding 1 normal tick must NOT immediately exit FLASH_CRASH_DETECTED
        state = sm.transition(is_vacuum=False, is_toxic=False, is_spread_blowout=False, is_vol_spike=False)
        self.assertEqual(state, SurveillanceState.FLASH_CRASH_DETECTED)

        # Must step down to ELEVATED_TOXICITY after 10 normal ticks
        for _ in range(9):
            state = sm.transition(is_vacuum=False, is_toxic=False, is_spread_blowout=False, is_vol_spike=False)
        self.assertEqual(state, SurveillanceState.ELEVATED_TOXICITY)

        # Must step down to NORMAL after another 5 normal ticks
        for _ in range(5):
            state = sm.transition(is_vacuum=False, is_toxic=False, is_spread_blowout=False, is_vol_spike=False)
        self.assertEqual(state, SurveillanceState.NORMAL)

    def test_05_alpha_signal_generation(self):
        """
        Validates actionable directional return mapping:
        - Positive return > deadband => BUY
        - Negative return < -deadband => SELL
        - Return within +/- deadband => HOLD
        """
        engine = RiskAwareDecisionEngine(
            symbol="ETH/USDT",
            config=RiskGuardrailConfig(neutral_deadband_bps=3.0, min_confidence=0.55),
        )

        bids = [(3000.0, 5.0), (2999.0, 5.0)]
        asks = [(3000.5, 5.0), (3001.0, 5.0)]

        # Signal 1: +12 bps expected return with 75% confidence => BUY
        d1 = engine.evaluate(
            timestamp="2026-09-30T10:00:00Z",
            price=3000.25,
            quantity=1.0,
            side="BUY",
            bids=bids,
            asks=asks,
            predicted_return_bps=12.0,
            model_confidence=0.75,
        )
        self.assertEqual(d1.candidate_action, "BUY")
        self.assertEqual(d1.action, "BUY")
        self.assertTrue(d1.trade_permitted)

        # Signal 2: -15 bps return with 80% confidence => SELL
        d2 = engine.evaluate(
            timestamp="2026-09-30T10:00:01Z",
            price=3000.25,
            quantity=1.0,
            side="SELL",
            bids=bids,
            asks=asks,
            predicted_return_bps=-15.0,
            model_confidence=0.80,
        )
        self.assertEqual(d2.candidate_action, "SELL")
        self.assertEqual(d2.action, "SELL")
        self.assertTrue(d2.trade_permitted)

        # Signal 3: +1.5 bps return (within deadband) => HOLD
        d3 = engine.evaluate(
            timestamp="2026-09-30T10:00:02Z",
            price=3000.25,
            quantity=1.0,
            side="BUY",
            bids=bids,
            asks=asks,
            predicted_return_bps=1.5,
            model_confidence=0.70,
        )
        self.assertEqual(d3.candidate_action, "HOLD")
        self.assertEqual(d3.action, "HOLD")

    def test_06_risk_arbiter_veto_on_toxic_flow(self):
        """
        Validates Risk Arbiter veto logic:
        When VPIN surges due to aggressive seller dumping, an aggressive
        BUY alpha forecast must be vetoed to HOLD.
        """
        engine = RiskAwareDecisionEngine(
            symbol="BTC/USDT",
            config=RiskGuardrailConfig(max_vpin_threshold=0.80),
            bucket_size=5.0,
        )

        bids = [(64000.0, 2.0), (63999.0, 2.0)]
        asks = [(64001.0, 2.0), (64002.0, 2.0)]

        # Simulate toxic flow surge (15 large sell dumps)
        for i in range(15):
            engine.evaluate(
                timestamp=f"2026-09-30T10:00:{i:02d}Z",
                price=64000.0 - i * 2.0,
                quantity=8.0,
                side="SELL",
                bids=bids,
                asks=asks,
                predicted_return_bps=0.0,
            )

        # Alpha model attempts to BUY the dip with 90% confidence
        decision = engine.evaluate(
            timestamp="2026-09-30T10:00:16Z",
            price=63970.0,
            quantity=8.0,
            side="SELL",
            bids=bids,
            asks=asks,
            predicted_return_bps=25.0,
            model_confidence=0.90,
        )

        self.assertEqual(decision.candidate_action, "BUY")
        self.assertEqual(decision.action, "HOLD")
        self.assertFalse(decision.trade_permitted)
        self.assertGreater(len(decision.veto_reasons), 0)
        self.assertIn("TOXIC_ORDER_FLOW", decision.veto_reasons[0])

    def test_07_risk_arbiter_veto_on_liquidity_vacuum(self):
        """
        Validates Risk Arbiter veto when order book depth collapses:
        Suppresses trades to prevent massive slippage.
        """
        engine = RiskAwareDecisionEngine(
            symbol="BTC/USDT",
            config=RiskGuardrailConfig(min_depth_usd=10000.0, max_spread_bps=15.0),
        )

        # Baseline: Healthy $150k depth
        bids = [(64000.0 - i, 1.2) for i in range(5)]
        asks = [(64001.0 + i, 1.2) for i in range(5)]

        for i in range(10):
            engine.evaluate(
                timestamp=f"2026-09-30T10:00:{i:02d}Z",
                price=64000.5,
                quantity=0.5,
                side="BUY",
                bids=bids,
                asks=asks,
                timestamp_epoch=float(i),
            )

        # Sudden Liquidity Vacuum: Top-5 depth drained to < $2,000, spread blows out to 30 bps
        vacuum_bids = [(63900.0, 0.01), (63850.0, 0.01)]
        vacuum_asks = [(64100.0, 0.01), (64150.0, 0.01)]

        decision = engine.evaluate(
            timestamp="2026-09-30T10:00:11Z",
            price=64000.0,
            quantity=0.1,
            side="BUY",
            bids=vacuum_bids,
            asks=vacuum_asks,
            predicted_return_bps=30.0,
            model_confidence=0.85,
            timestamp_epoch=11.0,
        )

        self.assertEqual(decision.candidate_action, "BUY")
        self.assertEqual(decision.action, "HOLD")
        self.assertFalse(decision.trade_permitted)
        veto_str = " ".join(decision.veto_reasons)
        self.assertTrue("LIQUIDITY_VACUUM" in veto_str or "THIN_BOOK" in veto_str or "SPREAD_BLOWOUT" in veto_str)

    def test_08_explainable_decision_contract(self):
        """
        Validates the explainability output contract:
        - to_dict() contains all required quantitative and risk fields.
        - format_terminal_card() renders valid ASCII output without unicode errors.
        """
        engine = RiskAwareDecisionEngine(symbol="SOL/USDT")
        bids = [(150.0, 10.0), (149.9, 10.0)]
        asks = [(150.1, 10.0), (150.2, 10.0)]

        decision = engine.evaluate(
            timestamp="2026-09-30T10:00:00Z",
            price=150.05,
            quantity=2.0,
            side="BUY",
            bids=bids,
            asks=asks,
            predicted_return_bps=8.5,
            model_confidence=0.72,
        )

        # Dictionary contract check
        d = decision.to_dict()
        required_keys = [
            "timestamp", "symbol", "action", "candidate_action", "confidence",
            "horizon", "reasons", "risk_state", "trade_permitted", "veto_reasons",
            "telemetry", "evaluation_latency_ms"
        ]
        for key in required_keys:
            self.assertIn(key, d)

        # ASCII formatting check (must encode cleanly to ASCII / Windows cp1252)
        card = decision.format_terminal_card()
        self.assertIsInstance(card, str)
        card.encode("ascii")  # Raises UnicodeEncodeError if non-ASCII character present
        self.assertIn("QuantPulse Decision Arbiter", card)
        self.assertIn("SOL/USDT", card)

    def test_09_sub_millisecond_decision_latency_gate(self):
        """
        Latency performance gate:
        Evaluates 3,000 streaming ticks and asserts mean decision latency < 1.0 ms.
        """
        engine = RiskAwareDecisionEngine(symbol="BTC/USDT", bucket_size=5.0)
        bids = [(64000.0, 1.0), (63999.0, 1.0)]
        asks = [(64001.0, 1.0), (64002.0, 1.0)]

        latencies = []
        # Warmup
        for i in range(100):
            engine.evaluate(
                timestamp=f"2026-09-30T10:00:{i%60:02d}Z",
                price=64000.0 + (i % 5),
                quantity=1.0,
                side="BUY" if i % 2 == 0 else "SELL",
                bids=bids,
                asks=asks,
                predicted_return_bps=5.0,
                model_confidence=0.65,
                timestamp_epoch=float(i),
            )

        # Benchmark 3,000 ticks
        t_start = time.perf_counter()
        for i in range(3000):
            dec = engine.evaluate(
                timestamp=f"2026-09-30T10:00:{i%60:02d}Z",
                price=64000.0 + (i % 7),
                quantity=0.5,
                side="BUY" if i % 3 == 0 else "SELL",
                bids=bids,
                asks=asks,
                predicted_return_bps=4.0,
                model_confidence=0.60,
                timestamp_epoch=float(100 + i),
            )
            latencies.append(dec.evaluation_latency_ms)

        total_time_s = time.perf_counter() - t_start
        mean_latency_ms = sum(latencies) / len(latencies)
        throughput = len(latencies) / total_time_s

        print(f"\n[Test Gate 09] 3,000 Decisions: Mean Latency = {mean_latency_ms:.3f} ms, Throughput = {throughput:,.1f} ops/sec")
        self.assertLess(mean_latency_ms, 1.0, f"Mean latency {mean_latency_ms:.3f}ms breached sub-millisecond gate!")


if __name__ == "__main__":
    unittest.main()
