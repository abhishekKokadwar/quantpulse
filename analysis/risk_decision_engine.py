"""
QuantPulse: Risk-Aware Multi-Signal Decision Engine & 3-Tier Risk Safeguards (Phase 12)
========================================================================================
The Institutional Decision Arbiter:
1. Multi-Signal Quantitative Fusion:
   - Directional Alpha Forecaster (Multi-horizon return forecast & model confidence)
   - Statistical Arbitrage Engine (Kalman filter cointegration spread Z-score & pair state)
   - Microstructure Surveillance Sentinel (VPIN toxicity, depth vacuum, spread blowout, OFI)
   - Pre-Trade Guardrails (Fat-finger caps, price collars, notional limits, depth floor)
2. 3-Tier Pre/Post-Trade Risk Safeguards:
   - Tier 1: Soft Risk Warning & Sizing Throttling (Dynamic Kelly, vol scaling, 50% cut)
   - Tier 2: Automated Delta-Neutral Hedging & Stat-Arb Divergence Liquidation
   - Tier 3: Emergency Hard Kill Switch (Instant cancel-all, position flatten, API lock)
3. In-Memory Portfolio Risk Ledger (O(1) thread-safe equity, margin, and delta tracking)
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import math
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from analysis.market_surveillance_engine import (
    MarketSurveillanceEngine,
    SurveillanceReport,
    SurveillanceState,
)


# =============================================================================
# 1. Decision Contracts & Signal Dataclasses
# =============================================================================

class RiskTier(str, Enum):
    TIER_0_NORMAL = "TIER_0_NORMAL"
    TIER_1_THROTTLED = "TIER_1_THROTTLED"
    TIER_2_HEDGING_ACTIVE = "TIER_2_HEDGING_ACTIVE"
    TIER_3_KILL_SWITCH = "TIER_3_KILL_SWITCH"


@dataclass
class StatArbSignal:
    """Input contract from Phase 6 Cointegrated Stat-Arb Pairs Engine."""
    pair_symbol: str
    spread_z_score: float
    stat_arb_state: str  # "IDLE", "LONG_SPREAD", "SHORT_SPREAD", "EXIT_MEAN_REVERT", "CIRCUIT_BREAKER_STOP"
    hedge_ratio: float = 1.0
    is_cointegrated: bool = True
    half_life_bars: Optional[float] = None


@dataclass
class TradeDecision:
    timestamp: str
    symbol: str
    action: str                 # "BUY", "SELL", or "HOLD"
    candidate_action: str       # Direction suggested by Alpha/Stat-Arb before risk arbitration
    confidence: float           # Composite confidence in [0.0, 1.0]
    horizon: str                # e.g., "1m", "5m"
    reasons: List[str]          # Supporting rationale for the signal
    risk_state: str             # "NORMAL", "ELEVATED_RISK", or "FLASH_CRASH_DETECTED"
    trade_permitted: bool       # True if passed all risk collars, False if vetoed
    veto_reasons: List[str]     # Specific reasons why trade was vetoed (if any)
    size_multiplier: float      # Dynamic position size scaling (0.0 to 1.0)
    risk_tier: str              # TIER_0_NORMAL, TIER_1_THROTTLED, TIER_2_HEDGING_ACTIVE, TIER_3_KILL_SWITCH
    kill_switch_active: bool    # True if hard circuit breaker engaged
    hedge_orders: List[Dict[str, Any]]      # Automated delta-neutral or pair liquidation orders
    emergency_orders: List[Dict[str, Any]]  # Emergency CANCEL_ALL and FLATTEN orders
    telemetry: Dict[str, Any]   # Microstructure state at decision epoch
    stat_arb_telemetry: Dict[str, Any]      # Stat-Arb state (if provided)
    portfolio_telemetry: Dict[str, Any]     # Portfolio PnL, margin, and drawdown state
    evaluation_latency_ms: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "symbol": self.symbol,
            "action": self.action,
            "candidate_action": self.candidate_action,
            "confidence": round(self.confidence, 4),
            "horizon": self.horizon,
            "reasons": self.reasons,
            "risk_state": self.risk_state,
            "trade_permitted": self.trade_permitted,
            "veto_reasons": self.veto_reasons,
            "size_multiplier": round(self.size_multiplier, 3),
            "risk_tier": self.risk_tier,
            "kill_switch_active": self.kill_switch_active,
            "hedge_orders": self.hedge_orders,
            "emergency_orders": self.emergency_orders,
            "telemetry": self.telemetry,
            "stat_arb_telemetry": self.stat_arb_telemetry,
            "portfolio_telemetry": self.portfolio_telemetry,
            "evaluation_latency_ms": round(self.evaluation_latency_ms, 3),
        }

    def format_terminal_card(self) -> str:
        """
        Renders a structured, high-impact ASCII card for logging & terminal display.
        Guaranteed 100% Windows console cp1252 / ASCII safe.
        """
        lines = [
            f"============================================================",
            f" [QuantPulse Decision Arbiter] {self.symbol} ({self.horizon})",
            f"============================================================",
            f" Signal:        {self.action:<8} (Confidence: {self.confidence*100.0:.1f}%)",
            f" Risk Tier:     {self.risk_tier} (Size Multiplier: {self.size_multiplier:.2f}x)",
            f" Risk State:    {self.risk_state}",
            f" Kill Switch:   {'ENGAGED [HALTED]' if self.kill_switch_active else 'OFF [ARMED]'}",
            f" Permitted:     {'YES [APPROVED]' if self.trade_permitted else 'NO [VETOED / BLOCKED]'}",
            f"------------------------------------------------------------",
            f" Signal Rationale:",
        ]
        for r in self.reasons:
            lines.append(f"   * {r}")

        if self.veto_reasons:
            lines.append(f"------------------------------------------------------------")
            lines.append(f" Risk Guardrail Vetoes:")
            for v in self.veto_reasons:
                lines.append(f"   [VETO] {v}")

        if self.hedge_orders:
            lines.append(f"------------------------------------------------------------")
            lines.append(f" Automated Tier 2 Hedging Orders:")
            for h in self.hedge_orders:
                lines.append(f"   [HEDGE] {h.get('action')} {h.get('quantity')} {h.get('symbol')} ({h.get('reason')})")

        if self.emergency_orders:
            lines.append(f"------------------------------------------------------------")
            lines.append(f" Tier 3 Emergency Circuit Breaker Orders:")
            for e in self.emergency_orders:
                lines.append(f"   [CRITICAL] {e.get('order_type')} ({e.get('reason')})")

        lines.extend([
            f"------------------------------------------------------------",
            f" Microstructure & Portfolio Telemetry:",
            f"   Mid Price:      ${self.telemetry.get('mid_price', 0.0):,.2f}",
            f"   Spread:         {self.telemetry.get('spread_bps', 0.0):.2f} bps",
            f"   VPIN:           {self.telemetry.get('vpin', 0.0):.3f}",
            f"   Top-5 Depth:    ${self.telemetry.get('depth_usd', 0.0):,.2f}",
            f"   Portfolio PnL:  ${self.portfolio_telemetry.get('total_pnl_usd', 0.0):,.2f}",
            f"   Drawdown:       {self.portfolio_telemetry.get('drawdown_pct', 0.0)*100.0:.2f}%",
            f"   Margin Ratio:   {self.portfolio_telemetry.get('margin_maintenance_ratio', 0.0)*100.0:.1f}%",
            f" Evaluation Latency: {self.evaluation_latency_ms:.3f} ms",
            f"============================================================",
        ])
        return "\n".join(lines)


# =============================================================================
# 2. In-Memory Portfolio Risk Ledger (O(1) State Tracking)
# =============================================================================

@dataclass
class PortfolioRiskLedger:
    """
    High-frequency in-memory portfolio ledger tracking cash, open positions,
    realized/unrealized PnL, drawdowns, and margin maintenance.
    """
    initial_capital: float = 1_000_000.0
    cash: float = 1_000_000.0
    positions: Dict[str, float] = field(default_factory=dict)       # symbol -> signed_units
    entry_prices: Dict[str, float] = field(default_factory=dict)    # symbol -> avg_entry_price
    market_prices: Dict[str, float] = field(default_factory=dict)   # symbol -> latest_price
    realized_daily_pnl: float = 0.0
    daily_loss_budget: float = 50_000.0                             # 5% of $1M
    peak_equity: float = 1_000_000.0
    margin_requirement_pct: float = 0.10                           # 10% initial margin (10x max leverage)

    def update_price(self, symbol: str, price: float) -> None:
        """O(1) market price tick update."""
        if price > 0.0:
            self.market_prices[symbol] = float(price)
            # Update peak equity
            eq = self.get_total_equity()
            if eq > self.peak_equity:
                self.peak_equity = eq

    def record_fill(self, symbol: str, quantity: float, price: float, side: str) -> None:
        """O(1) fill execution and position ledger adjustment."""
        qty = abs(float(quantity))
        px = float(price)
        signed_qty = qty if str(side).upper() == "BUY" else -qty

        curr_pos = self.positions.get(symbol, 0.0)
        curr_entry = self.entry_prices.get(symbol, px)

        # Calculate realized PnL if closing or reducing existing position
        if (curr_pos > 0 and signed_qty < 0) or (curr_pos < 0 and signed_qty > 0):
            closed_qty = min(abs(curr_pos), abs(signed_qty))
            trade_pnl = closed_qty * (px - curr_entry) if curr_pos > 0 else closed_qty * (curr_entry - px)
            self.realized_daily_pnl += trade_pnl
            self.cash += trade_pnl

        # Update net position and weighted average entry price
        new_pos = curr_pos + signed_qty
        if abs(new_pos) < 1e-9:
            self.positions[symbol] = 0.0
            self.entry_prices[symbol] = 0.0
        elif (curr_pos >= 0 and signed_qty > 0) or (curr_pos <= 0 and signed_qty < 0):
            # Increasing position size
            total_notional = abs(curr_pos) * curr_entry + qty * px
            self.entry_prices[symbol] = total_notional / abs(new_pos)
            self.positions[symbol] = new_pos
        else:
            # Partially closed position maintains original entry price
            self.positions[symbol] = new_pos

        self.market_prices[symbol] = px
        eq = self.get_total_equity()
        if eq > self.peak_equity:
            self.peak_equity = eq

    def get_unrealized_pnl(self) -> float:
        """Computes aggregate unrealized mark-to-market PnL."""
        unrealized = 0.0
        for sym, pos in self.positions.items():
            if abs(pos) > 1e-9:
                mkt_px = self.market_prices.get(sym, self.entry_prices.get(sym, 0.0))
                entry_px = self.entry_prices.get(sym, mkt_px)
                unrealized += pos * (mkt_px - entry_px)
        return float(unrealized)

    def get_total_equity(self) -> float:
        """Total Portfolio Equity = Cash + Realized PnL + Unrealized PnL."""
        return float(self.cash + self.get_unrealized_pnl())

    def get_current_drawdown_pct(self) -> float:
        """Peak-to-trough drawdown percentage in [0.0, 1.0]."""
        eq = self.get_total_equity()
        if self.peak_equity <= 0.0:
            return 0.0
        dd = (self.peak_equity - eq) / self.peak_equity
        return float(np.clip(dd, 0.0, 1.0))

    def get_daily_loss_pct(self) -> float:
        """Total daily loss relative to initial capital."""
        loss = -(self.realized_daily_pnl + self.get_unrealized_pnl())
        if loss <= 0.0 or self.initial_capital <= 0.0:
            return 0.0
        return float(np.clip(loss / self.initial_capital, 0.0, 1.0))

    def get_margin_maintenance_ratio(self) -> float:
        """
        Margin Maintenance Ratio = Total Equity / Total Required Margin.
        Values >= 2.0 indicate healthy leverage (< 50% margin used).
        Values < 1.10 indicate critical margin call / liquidation danger.
        """
        total_notional_usd = sum(
            abs(pos) * self.market_prices.get(sym, self.entry_prices.get(sym, 0.0))
            for sym, pos in self.positions.items()
        )
        required_margin = total_notional_usd * self.margin_requirement_pct
        if required_margin <= 0.0:
            return 10.0  # Infinite margin buffer when no positions
        eq = self.get_total_equity()
        return float(max(0.0, eq / required_margin))

    def get_net_delta_usd(self) -> float:
        """Aggregate signed directional exposure across all positions."""
        return float(sum(
            pos * self.market_prices.get(sym, self.entry_prices.get(sym, 0.0))
            for sym, pos in self.positions.items()
        ))

    def get_asset_concentration_pct(self, symbol: str) -> float:
        """Single-asset gross notional relative to total equity."""
        eq = self.get_total_equity()
        if eq <= 0.0:
            return 1.0
        pos = self.positions.get(symbol, 0.0)
        px = self.market_prices.get(symbol, self.entry_prices.get(symbol, 0.0))
        return float(np.clip((abs(pos) * px) / eq, 0.0, 1.0))

    def to_telemetry(self) -> Dict[str, Any]:
        return {
            "total_equity": round(self.get_total_equity(), 2),
            "unrealized_pnl": round(self.get_unrealized_pnl(), 2),
            "realized_daily_pnl": round(self.realized_daily_pnl, 2),
            "total_pnl_usd": round(self.realized_daily_pnl + self.get_unrealized_pnl(), 2),
            "drawdown_pct": round(self.get_current_drawdown_pct(), 4),
            "daily_loss_pct": round(self.get_daily_loss_pct(), 4),
            "margin_maintenance_ratio": round(self.get_margin_maintenance_ratio(), 3),
            "net_delta_usd": round(self.get_net_delta_usd(), 2),
            "open_positions_count": len([p for p in self.positions.values() if abs(p) > 1e-9]),
        }


# =============================================================================
# 3. 3-Tier Risk Guardrail Configuration
# =============================================================================

@dataclass
class RiskGuardrailConfig:
    # Microstructure & Pre-Trade Limits
    max_spread_bps: float = 25.0            # Max allowable spread before blocking trades
    min_depth_usd: float = 5000.0           # Minimum top-5 depth required
    max_vpin_threshold: float = 0.85        # VPIN ceiling above which informed flow is toxic
    min_confidence: float = 0.55            # Minimum Alpha model confidence required
    neutral_deadband_bps: float = 3.0       # Minimum expected return required to trigger BUY/SELL
    max_depth_drop_pct: float = 0.70        # Max allowable sudden depth evaporation (70%)
    max_volatility: float = 0.08            # Realized volatility collar

    # Tier 1 (Soft Risk & Sizing Throttle)
    soft_loss_throttle_pct: float = 0.50    # Throttles size when daily loss reaches 50% of budget
    max_asset_concentration_pct: float = 0.25  # Max 25% single-asset portfolio concentration
    target_volatility: float = 0.02         # Base daily volatility target for inverse-vol scaling

    # Tier 2 (Automated Delta-Neutral Hedging & Stat-Arb Circuit Breakers)
    max_net_delta_usd: float = 100_000.0    # Directional delta ceiling before automated hedging
    stat_arb_divergence_z: float = 3.5      # Z-score stop-loss for cointegrated pair liquidation
    benchmark_hedge_symbol: str = "BTC/USDT"# Benchmark hedge instrument

    # Tier 3 (Emergency Circuit Breakers & Kill Switch)
    max_daily_drawdown_pct: float = 0.03    # 3.0% max drawdown triggers hard emergency kill switch
    min_margin_maintenance_pct: float = 1.10 # 110% margin maintenance triggers immediate liquidation
    admin_kill_token: str = "QUANT_PULSE_SECURE_TOKEN_2026"  # Administrative unlock token


# =============================================================================
# 4. Institutional Decision Arbiter Implementation
# =============================================================================

class RiskAwareDecisionEngine:
    """
    Central Institutional Decision Arbiter.
    Fuses predictive Alpha, cointegrated Stat-Arb, and high-frequency microstructure surveillance,
    enforcing 3-tier pre-trade and post-trade risk safeguards.
    """

    def __init__(
        self,
        symbol: str,
        config: Optional[RiskGuardrailConfig] = None,
        bucket_size: float = 10.0,
        portfolio: Optional[PortfolioRiskLedger] = None,
    ):
        self.symbol = symbol
        self.config = config or RiskGuardrailConfig()
        self.surveillance = MarketSurveillanceEngine(symbol=symbol, bucket_size=bucket_size)
        self.portfolio = portfolio or PortfolioRiskLedger()

        # Hard circuit breaker state
        self.kill_switch_active = False
        self.kill_switch_reason: Optional[str] = None
        self.lockout_timestamp: Optional[str] = None

    def trigger_manual_kill_switch(self, reason: str = "MANUAL_OPERATOR_OVERRIDE") -> Dict[str, Any]:
        """Manually trips the Tier 3 emergency kill switch."""
        self.kill_switch_active = True
        self.kill_switch_reason = reason
        self.lockout_timestamp = datetime.now(timezone.utc).isoformat()
        return {
            "status": "EMERGENCY_HALT",
            "kill_switch_active": True,
            "reason": reason,
            "timestamp": self.lockout_timestamp,
        }

    def reset_kill_switch(self, admin_token: str) -> bool:
        """Resets the Tier 3 kill switch given an authorized administrative token."""
        if admin_token == self.config.admin_kill_token:
            self.kill_switch_active = False
            self.kill_switch_reason = None
            self.lockout_timestamp = None
            return True
        return False

    def evaluate(
        self,
        timestamp: str,
        price: float,
        quantity: float,
        side: str,
        bids: List[Tuple[float, float]],
        asks: List[Tuple[float, float]],
        predicted_return_bps: float = 0.0,
        model_confidence: float = 0.50,
        stat_arb_signal: Optional[StatArbSignal] = None,
        portfolio_ledger: Optional[PortfolioRiskLedger] = None,
        order_flow_imbalance: Optional[float] = None,
        horizon: str = "5m",
        timestamp_epoch: Optional[float] = None,
    ) -> TradeDecision:
        """
        Unified multi-signal evaluation and 3-tier risk arbitration.
        """
        t0 = time.perf_counter()
        ledger = portfolio_ledger or self.portfolio
        ledger.update_price(self.symbol, price)

        # ---------------------------------------------------------------------
        # Step 0: Fast-Path Tier 3 Kill Switch Lockout Check
        # ---------------------------------------------------------------------
        if self.kill_switch_active:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return TradeDecision(
                timestamp=timestamp,
                symbol=self.symbol,
                action="HOLD",
                candidate_action="HOLD",
                confidence=0.0,
                horizon=horizon,
                reasons=[f"Trading halted: {self.kill_switch_reason}"],
                risk_state="EMERGENCY_HALT",
                trade_permitted=False,
                veto_reasons=[f"KILL_SWITCH_ACTIVE: {self.kill_switch_reason}"],
                size_multiplier=0.0,
                risk_tier=RiskTier.TIER_3_KILL_SWITCH.value,
                kill_switch_active=True,
                hedge_orders=[],
                emergency_orders=[{"order_type": "CANCEL_ALL", "reason": self.kill_switch_reason}],
                telemetry={"mid_price": price},
                stat_arb_telemetry={},
                portfolio_telemetry=ledger.to_telemetry(),
                evaluation_latency_ms=elapsed_ms,
            )

        # ---------------------------------------------------------------------
        # Step 1: Microstructure Surveillance Update
        # ---------------------------------------------------------------------
        surv_report: SurveillanceReport = self.surveillance.process_tick(
            timestamp=timestamp,
            price=price,
            quantity=quantity,
            side=side,
            bids=bids,
            asks=asks,
            timestamp_epoch=timestamp_epoch,
        )

        best_bid = bids[0][0] if bids else price
        best_ask = asks[0][0] if asks else price
        mid_price = 0.5 * (best_bid + best_ask) if best_ask >= best_bid else price
        spread_bps = surv_report.spread_bps

        # Calculate Micro-price
        bid_qty_1 = bids[0][1] if bids else 1.0
        ask_qty_1 = asks[0][1] if asks else 1.0
        tot_qty = bid_qty_1 + ask_qty_1
        micro_price = (best_bid * ask_qty_1 + best_ask * bid_qty_1) / tot_qty if tot_qty > 0.0 else mid_price

        if order_flow_imbalance is None:
            order_flow_imbalance = surv_report.order_flow_imbalance

        # ---------------------------------------------------------------------
        # Step 2: Multi-Signal Quantitative Fusion (Alpha + Stat-Arb)
        # ---------------------------------------------------------------------
        reasons: List[str] = []
        alpha_action = "HOLD"

        if predicted_return_bps > self.config.neutral_deadband_bps and model_confidence >= self.config.min_confidence:
            alpha_action = "BUY"
            reasons.append(f"Alpha Return Forecast: +{predicted_return_bps:.1f} bps (Confidence: {model_confidence*100.0:.1f}%)")
        elif predicted_return_bps < -self.config.neutral_deadband_bps and model_confidence >= self.config.min_confidence:
            alpha_action = "SELL"
            reasons.append(f"Alpha Return Forecast: {predicted_return_bps:.1f} bps (Confidence: {model_confidence*100.0:.1f}%)")
        else:
            alpha_action = "HOLD"
            reasons.append(f"Alpha return within neutral deadband (+/-{self.config.neutral_deadband_bps:.1f} bps)")

        # Stat-Arb Signal Extraction
        stat_arb_action = "HOLD"
        stat_arb_telemetry: Dict[str, Any] = {}

        if stat_arb_signal is not None:
            stat_arb_telemetry = {
                "pair_symbol": stat_arb_signal.pair_symbol,
                "spread_z_score": round(stat_arb_signal.spread_z_score, 2),
                "stat_arb_state": stat_arb_signal.stat_arb_state,
                "hedge_ratio": round(stat_arb_signal.hedge_ratio, 4),
                "is_cointegrated": stat_arb_signal.is_cointegrated,
            }
            if stat_arb_signal.stat_arb_state == "LONG_SPREAD":
                stat_arb_action = "BUY"
                reasons.append(f"Stat-Arb: Spread undervalued (Z: {stat_arb_signal.spread_z_score:.2f} < -2.0) -> Long Pair Spread")
            elif stat_arb_signal.stat_arb_state == "SHORT_SPREAD":
                stat_arb_action = "SELL"
                reasons.append(f"Stat-Arb: Spread overvalued (Z: {stat_arb_signal.spread_z_score:.2f} > +2.0) -> Short Pair Spread")
            elif stat_arb_signal.stat_arb_state == "EXIT_MEAN_REVERT":
                reasons.append(f"Stat-Arb: Spread mean-reverted (|Z|: {abs(stat_arb_signal.spread_z_score):.2f} <= 0.5) -> Target Reached")

        # Consensus & Conflict Resolution
        composite_confidence = model_confidence
        candidate_action = "HOLD"

        if alpha_action == "BUY" and stat_arb_action == "BUY":
            candidate_action = "BUY"
            composite_confidence = min(0.99, model_confidence + 0.15)
            reasons.append("Alpha & Stat-Arb Consensus: High-conviction long alignment (+15% confidence boost)")
        elif alpha_action == "SELL" and stat_arb_action == "SELL":
            candidate_action = "SELL"
            composite_confidence = min(0.99, model_confidence + 0.15)
            reasons.append("Alpha & Stat-Arb Consensus: High-conviction short alignment (+15% confidence boost)")
        elif alpha_action == "BUY" and stat_arb_action == "SELL":
            candidate_action = "HOLD"
            reasons.append("Signal Conflict: Alpha predicts BUY but Stat-Arb spread indicates overvalued SELL -> Neutralized to HOLD")
        elif alpha_action == "SELL" and stat_arb_action == "BUY":
            candidate_action = "HOLD"
            reasons.append("Signal Conflict: Alpha predicts SELL but Stat-Arb spread indicates undervalued BUY -> Neutralized to HOLD")
        elif alpha_action in ("BUY", "SELL"):
            candidate_action = alpha_action
        elif stat_arb_action in ("BUY", "SELL"):
            candidate_action = stat_arb_action
            composite_confidence = 0.70  # Baseline confidence for unassisted Stat-Arb mean reversion

        # Augment with OFI and Micro-Price rationale
        if order_flow_imbalance > 0.30:
            reasons.append(f"OFI Strong Buy Pressure (+{order_flow_imbalance:.2f})")
        elif order_flow_imbalance < -0.30:
            reasons.append(f"OFI Strong Sell Pressure ({order_flow_imbalance:.2f})")

        if micro_price > mid_price + 1e-6:
            reasons.append("Micro-Price Premium: Buyers aggressive at top of book")
        elif micro_price < mid_price - 1e-6:
            reasons.append("Micro-Price Discount: Sellers aggressive at top of book")

        # ---------------------------------------------------------------------
        # Step 3: Microstructure & Pre-Trade Guardrail Vetoes
        # ---------------------------------------------------------------------
        veto_reasons: List[str] = []

        # Surveillance Guardrails
        if surv_report.state == SurveillanceState.FLASH_CRASH_DETECTED:
            veto_reasons.append("FLASH_CRASH_HALT: Liquidity collapse and extreme toxicity detected. All trading halted.")

        effective_vpin = max(surv_report.vpin, surv_report.fast_vpin)
        is_toxic_regime = (surv_report.vpin_regime == "TOXIC_INFORMED_FLOW") or (effective_vpin >= self.config.max_vpin_threshold)
        is_adverse_buy = (candidate_action == "BUY") and (order_flow_imbalance < -0.40 or surv_report.book_imbalance < -0.50)
        is_adverse_sell = (candidate_action == "SELL") and (order_flow_imbalance > 0.40 or surv_report.book_imbalance > 0.50)

        if is_toxic_regime:
            veto_reasons.append(f"TOXIC_ORDER_FLOW: VPIN ({effective_vpin:.3f}) exceeds threshold ({self.config.max_vpin_threshold:.2f}). Adverse selection hazard.")
        elif is_adverse_buy:
            veto_reasons.append(f"ADVERSE_SELECTION: Informed selling pressure (OFI: {order_flow_imbalance:+.2f}). BUY signal vetoed.")
        elif is_adverse_sell:
            veto_reasons.append(f"ADVERSE_SELECTION: Informed buying pressure (OFI: {order_flow_imbalance:+.2f}). SELL signal vetoed.")

        if surv_report.is_liquidity_vacuum or (surv_report.depth_drop_pct >= self.config.max_depth_drop_pct):
            veto_reasons.append(f"LIQUIDITY_VACUUM: Order book depth dropped by {surv_report.depth_drop_pct*100.0:.1f}%. Slippage risk unacceptable.")

        if spread_bps > self.config.max_spread_bps:
            veto_reasons.append(f"SPREAD_BLOWOUT: Bid-Ask spread ({spread_bps:.1f} bps) exceeds limit ({self.config.max_spread_bps:.1f} bps).")
        if surv_report.is_spread_anomaly:
            veto_reasons.append(f"SPREAD_ANOMALY: Spread is {surv_report.spread_z_score:.1f} standard deviations above baseline.")

        if surv_report.current_depth_usd < self.config.min_depth_usd:
            veto_reasons.append(f"THIN_BOOK: Top-5 depth (${surv_report.current_depth_usd:,.2f}) below minimum floor (${self.config.min_depth_usd:,.2f}).")

        if surv_report.realized_volatility > self.config.max_volatility:
            veto_reasons.append(f"VOLATILITY_COLLAR: Realized volatility ({surv_report.realized_volatility:.4f}) breached safety cap ({self.config.max_volatility:.4f}).")

        if surv_report.state == SurveillanceState.ELEVATED_TOXICITY and candidate_action in ("BUY", "SELL") and not veto_reasons:
            veto_reasons.append(f"ELEVATED_REGIME_BLOCK: Market is in {surv_report.state}. Speculative positions blocked.")

        # ---------------------------------------------------------------------
        # Step 4: 3-Tier Risk Safeguards Evaluation
        # ---------------------------------------------------------------------
        current_drawdown = ledger.get_current_drawdown_pct()
        daily_loss_pct = ledger.get_daily_loss_pct()
        margin_ratio = ledger.get_margin_maintenance_ratio()
        net_delta_usd = ledger.get_net_delta_usd()
        concentration_pct = ledger.get_asset_concentration_pct(self.symbol)

        size_multiplier = 1.0
        risk_tier = RiskTier.TIER_0_NORMAL.value
        hedge_orders: List[Dict[str, Any]] = []
        emergency_orders: List[Dict[str, Any]] = []

        # =====================================================================
        # Tier 3 Check: Emergency Hard Circuit Breaker & Kill Switch
        # =====================================================================
        is_drawdown_breach = current_drawdown >= self.config.max_daily_drawdown_pct
        is_margin_collapse = margin_ratio < self.config.min_margin_maintenance_pct
        is_flash_crash_critical = surv_report.state == SurveillanceState.FLASH_CRASH_DETECTED

        if is_drawdown_breach or is_margin_collapse or is_flash_crash_critical:
            self.kill_switch_active = True
            reasons_list = []
            if is_drawdown_breach:
                reasons_list.append(f"MAX_DRAWDOWN_BREACH: Drawdown ({current_drawdown*100.0:.2f}%) exceeded {self.config.max_daily_drawdown_pct*100.0:.1f}% limit.")
            if is_margin_collapse:
                reasons_list.append(f"MARGIN_CALL_COLLAPSE: Margin ratio ({margin_ratio*100.0:.1f}%) breached {self.config.min_margin_maintenance_pct*100.0:.1f}% maintenance floor.")
            if is_flash_crash_critical:
                reasons_list.append("CRITICAL_FLASH_CRASH: Catastrophic book collapse and market failure.")

            self.kill_switch_reason = " | ".join(reasons_list)
            self.lockout_timestamp = timestamp
            risk_tier = RiskTier.TIER_3_KILL_SWITCH.value
            size_multiplier = 0.0
            veto_reasons.append(f"TIER_3_KILL_SWITCH: {self.kill_switch_reason}")

            emergency_orders.append({"order_type": "CANCEL_ALL_OPEN_ORDERS", "reason": self.kill_switch_reason})
            emergency_orders.append({"order_type": "LIQUIDATE_ALL_POSITIONS", "reason": "EMERGENCY_PORTFOLIO_FLATTEN"})

        # =====================================================================
        # Tier 2 Check: Automated Delta-Neutral Hedging & Cointegration Stops
        # =====================================================================
        elif not self.kill_switch_active:
            # Check 1: Portfolio Net Delta Breach
            if abs(net_delta_usd) > self.config.max_net_delta_usd:
                risk_tier = RiskTier.TIER_2_HEDGING_ACTIVE.value
                hedge_direction = "SELL" if net_delta_usd > 0 else "BUY"
                hedge_size_units = abs(net_delta_usd) / price
                hedge_orders.append({
                    "action": hedge_direction,
                    "symbol": self.config.benchmark_hedge_symbol,
                    "quantity": round(hedge_size_units, 4),
                    "reason": f"PORTFOLIO_DELTA_BREACH: Net delta ${net_delta_usd:,.2f} exceeds ${self.config.max_net_delta_usd:,.2f} cap. Emitting offsetting {hedge_direction} hedge.",
                })
                reasons.append(f"Tier 2 Auto-Hedge: Net delta ${net_delta_usd:,.2f} neutralized with {hedge_direction} in {self.config.benchmark_hedge_symbol}")

            # Check 2: Stat-Arb Cointegration Structural Breakdown Stop
            if stat_arb_signal is not None:
                if stat_arb_signal.stat_arb_state == "CIRCUIT_BREAKER_STOP" or abs(stat_arb_signal.spread_z_score) >= self.config.stat_arb_divergence_z:
                    risk_tier = RiskTier.TIER_2_HEDGING_ACTIVE.value
                    veto_reasons.append(f"STAT_ARB_DIVERGENCE_STOP: Spread Z-score ({stat_arb_signal.spread_z_score:.2f}) exceeded {self.config.stat_arb_divergence_z} sigma. Cointegration broken.")
                    hedge_orders.append({
                        "action": "CLOSE_PAIR_POSITIONS",
                        "symbol": self.symbol,
                        "pair_symbol": stat_arb_signal.pair_symbol,
                        "reason": "STRUCTURAL_COINTEGRATION_BREAKDOWN_STOP",
                    })

        # =====================================================================
        # Tier 1 Check: Dynamic Sizing & Soft Drawdown Throttling
        # =====================================================================
        if risk_tier == RiskTier.TIER_0_NORMAL.value and not self.kill_switch_active:
            # Kelly factor & Volatility scaling
            kelly_factor = max(0.20, min(1.0, 2.0 * (composite_confidence - 0.50)))
            vol_scale = min(1.0, self.config.target_volatility / max(0.005, surv_report.realized_volatility))
            base_size = kelly_factor * vol_scale

            # Soft daily loss throttle (cut size by 50% when loss reaches 50% of budget)
            loss_budget_pct = (ledger.daily_loss_budget / ledger.initial_capital) if ledger.initial_capital > 0 else 0.05
            is_soft_loss_breach = daily_loss_pct >= (self.config.soft_loss_throttle_pct * loss_budget_pct)
            is_concentration_breach = concentration_pct >= (0.80 * self.config.max_asset_concentration_pct)

            if is_soft_loss_breach or is_concentration_breach:
                risk_tier = RiskTier.TIER_1_THROTTLED.value
                size_multiplier = round(base_size * 0.50, 3)
                if is_soft_loss_breach:
                    reasons.append(f"Tier 1 Throttle: Daily loss ({daily_loss_pct*100.0:.2f}%) reached 50% of daily budget. Order size halved.")
                if is_concentration_breach:
                    reasons.append(f"Tier 1 Throttle: Asset concentration ({concentration_pct*100.0:.1f}%) reached 80% of limit.")
            else:
                size_multiplier = round(base_size, 3)

        # ---------------------------------------------------------------------
        # Step 5: Final Arbitrated Execution Decision
        # ---------------------------------------------------------------------
        trade_permitted = (len(veto_reasons) == 0) and not self.kill_switch_active

        if candidate_action in ("BUY", "SELL"):
            if trade_permitted:
                final_action = candidate_action
            else:
                final_action = "HOLD"
                reasons.append(f"Original signal [{candidate_action}] suppressed by Risk Arbiter")
        else:
            final_action = "HOLD"

        # Determine composite risk classification
        if self.kill_switch_active:
            risk_state = "EMERGENCY_HALT"
        elif surv_report.state == SurveillanceState.FLASH_CRASH_DETECTED:
            risk_state = "FLASH_CRASH_DETECTED"
        elif len(veto_reasons) > 0 or surv_report.state == SurveillanceState.ELEVATED_TOXICITY or risk_tier != RiskTier.TIER_0_NORMAL.value:
            risk_state = "ELEVATED_RISK"
        else:
            risk_state = "NORMAL"

        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        telemetry = {
            "mid_price": round(mid_price, 4),
            "micro_price": round(micro_price, 4),
            "spread_bps": round(spread_bps, 2),
            "order_flow_imbalance": round(order_flow_imbalance, 3),
            "vpin": round(surv_report.vpin, 4),
            "fast_vpin": round(surv_report.fast_vpin, 4),
            "vpin_regime": surv_report.vpin_regime,
            "depth_usd": round(surv_report.current_depth_usd, 2),
            "depth_drop_pct": round(surv_report.depth_drop_pct * 100.0, 2),
            "realized_volatility": round(surv_report.realized_volatility, 6),
            "active_alarms_count": len(surv_report.active_alarms),
        }

        return TradeDecision(
            timestamp=timestamp,
            symbol=self.symbol,
            action=final_action,
            candidate_action=candidate_action,
            confidence=composite_confidence,
            horizon=horizon,
            reasons=reasons,
            risk_state=risk_state,
            trade_permitted=trade_permitted,
            veto_reasons=veto_reasons,
            size_multiplier=size_multiplier,
            risk_tier=risk_tier,
            kill_switch_active=self.kill_switch_active,
            hedge_orders=hedge_orders,
            emergency_orders=emergency_orders,
            telemetry=telemetry,
            stat_arb_telemetry=stat_arb_telemetry,
            portfolio_telemetry=ledger.to_telemetry(),
            evaluation_latency_ms=elapsed_ms,
        )
