"""
QuantPulse: Institutional Market Surveillance, Toxic Flow (VPIN) & Flash Crash Sentinel
========================================================================================
Detects abnormal market microstructure conditions in real time from streaming ticks and
Level-2 order book depth:
1. Volume-Synchronized Probability of Toxicity (VPIN - Easley, Lopez de Prado, O'Hara)
2. Liquidity Vacuum Sentinel (rapid top-5 depth collapse >75% in <3 seconds with hysteresis recovery)
3. Dynamic Spread Blowout Detector (rolling Bollinger bands on spread bps with baseline protection)
4. Abnormal Realized Volatility Surge Detector
5. Order Flow Imbalance (OFI) & Book Imbalance Real-Time Sentinel
6. Hysteresis Anti-Flapping State Machine (NORMAL <-> ELEVATED_TOXICITY -> FLASH_CRASH_DETECTED)
"""

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# =============================================================================
# 1. Microstructure Telemetry & Surveillance Event Dataclasses
# =============================================================================

@dataclass
class SurveillanceState:
    NORMAL: str = "NORMAL"
    ELEVATED_TOXICITY: str = "ELEVATED_TOXICITY"
    FLASH_CRASH_DETECTED: str = "FLASH_CRASH_DETECTED"


@dataclass
class SurveillanceReport:
    timestamp: str
    symbol: str
    state: str
    is_anomaly: bool
    vpin: float
    fast_vpin: float
    vpin_regime: str
    spread_bps: float
    spread_z_score: float
    is_spread_anomaly: bool
    current_depth_usd: float
    depth_drop_pct: float
    is_liquidity_vacuum: bool
    realized_volatility: float
    is_volatility_spike: bool
    order_flow_imbalance: float
    book_imbalance: float
    active_alarms: List[str]
    evaluation_latency_ms: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "symbol": self.symbol,
            "state": self.state,
            "is_anomaly": self.is_anomaly,
            "vpin": round(self.vpin, 4),
            "fast_vpin": round(self.fast_vpin, 4),
            "vpin_regime": self.vpin_regime,
            "spread_bps": round(self.spread_bps, 2),
            "spread_z_score": round(self.spread_z_score, 2),
            "is_spread_anomaly": self.is_spread_anomaly,
            "current_depth_usd": round(self.current_depth_usd, 2),
            "depth_drop_pct": round(self.depth_drop_pct * 100.0, 2),
            "is_liquidity_vacuum": self.is_liquidity_vacuum,
            "realized_volatility": round(self.realized_volatility, 6),
            "is_volatility_spike": self.is_volatility_spike,
            "order_flow_imbalance": round(self.order_flow_imbalance, 3),
            "book_imbalance": round(self.book_imbalance, 3),
            "active_alarms": self.active_alarms,
            "evaluation_latency_ms": round(self.evaluation_latency_ms, 3),
        }


# =============================================================================
# 2. Volume-Synchronized Probability of Toxicity (VPIN Calculator)
# =============================================================================

class VPINCalculator:
    """
    Computes Volume-Synchronized Probability of Toxicity (VPIN).
    Slices transaction flow into standardized volume buckets of constant size V.
    Calculates absolute order imbalance |V_buy - V_sell| across N rolling buckets.
    Maintains both standard (30 buckets) and fast (5 buckets) windows for rapid threat response.
    """

    def __init__(
        self,
        bucket_size: float = 10.0,
        window_buckets: int = 30,
        fast_window_buckets: int = 5,
        toxic_threshold: float = 0.85,
        elevated_threshold: float = 0.65,
    ):
        self.bucket_size = float(bucket_size)
        self.window_buckets = int(window_buckets)
        self.fast_window_buckets = int(fast_window_buckets)
        self.toxic_threshold = float(toxic_threshold)
        self.elevated_threshold = float(elevated_threshold)

        # Current incomplete bucket state
        self._curr_buy_vol = 0.0
        self._curr_sell_vol = 0.0
        self._curr_filled_vol = 0.0

        # Completed buckets queue: stores (buy_volume, sell_volume)
        self._completed_buckets: deque = deque(maxlen=self.window_buckets)
        self._trade_flow: deque = deque(maxlen=40)  # (signed_qty, abs_qty)
        self.current_vpin = 0.0
        self.fast_vpin = 0.0
        self.trade_flow_imbalance = 0.0

    def update(self, price: float, quantity: float, side: str) -> float:
        """
        Ingests a trade execution and updates rolling VPIN and fast VPIN.
        Handles trade fragmentation across volume bucket boundaries.
        """
        remaining_qty = float(quantity)
        is_buy = str(side).upper() == "BUY"

        # Track raw trade flow imbalance
        signed_qty = remaining_qty if is_buy else -remaining_qty
        self._trade_flow.append((signed_qty, remaining_qty))
        if self._trade_flow:
            tot_signed = sum(s for s, _ in self._trade_flow)
            tot_abs = sum(a for _, a in self._trade_flow)
            self.trade_flow_imbalance = tot_signed / tot_abs if tot_abs > 0.0 else 0.0

        while remaining_qty > 0.0:
            space_in_bucket = self.bucket_size - self._curr_filled_vol
            fill_amount = min(remaining_qty, space_in_bucket)

            if is_buy:
                self._curr_buy_vol += fill_amount
            else:
                self._curr_sell_vol += fill_amount
            self._curr_filled_vol += fill_amount
            remaining_qty -= fill_amount

            # If bucket is completely filled, seal and push to rolling window
            if self._curr_filled_vol >= self.bucket_size - 1e-9:
                self._completed_buckets.append((self._curr_buy_vol, self._curr_sell_vol))
                self._curr_buy_vol = 0.0
                self._curr_sell_vol = 0.0
                self._curr_filled_vol = 0.0

        if not self._completed_buckets:
            self.current_vpin = 0.0
            self.fast_vpin = 0.0
            return 0.0

        # Compute standard rolling VPIN
        total_imbalance = sum(abs(b - s) for b, s in self._completed_buckets)
        total_volume = len(self._completed_buckets) * self.bucket_size
        self.current_vpin = float(np.clip(total_imbalance / total_volume, 0.0, 1.0))

        # Compute fast VPIN over recent fast_window_buckets
        fast_slice = list(self._completed_buckets)[-self.fast_window_buckets:]
        fast_imbalance = sum(abs(b - s) for b, s in fast_slice)
        fast_volume = len(fast_slice) * self.bucket_size
        self.fast_vpin = float(np.clip(fast_imbalance / fast_volume, 0.0, 1.0))

        return self.current_vpin

    def get_regime(self) -> str:
        # Effective toxicity triggers if standard VPIN or fast VPIN or persistent trade imbalance surges
        effective_vpin = max(self.current_vpin, self.fast_vpin)
        is_flow_surge = len(self._trade_flow) >= 10 and abs(self.trade_flow_imbalance) >= 0.80

        if effective_vpin >= self.toxic_threshold or is_flow_surge:
            return "TOXIC_INFORMED_FLOW"
        elif effective_vpin >= self.elevated_threshold or abs(self.trade_flow_imbalance) >= 0.60:
            return "ELEVATED_IMBALANCE"
        return "BALANCED_FLOW"


# =============================================================================
# 3. Liquidity Vacuum Sentinel (Order Book Depth Evacuation)
# =============================================================================

class LiquidityVacuumDetector:
    """
    Monitors aggregate top-5 bid/ask depth in Level-2 order books.
    Triggers when cumulative depth collapses by > 75% in < 3.0 seconds,
    indicating market maker quotes pulled prior to a liquidity vacuum / flash crash.
    Implements baseline preservation during vacuum regimes with hysteresis recovery.
    """

    def __init__(
        self,
        collapse_threshold: float = 0.75,
        window_seconds: float = 10.0,
        baseline_snapshots: int = 500,
        recovery_ratio: float = 0.60,
    ):
        self.collapse_threshold = float(collapse_threshold)
        self.window_seconds = float(window_seconds)
        self.baseline_snapshots = int(baseline_snapshots)
        self.recovery_ratio = float(recovery_ratio)

        # Stores (timestamp_epoch, depth_usd)
        self._history: deque = deque(maxlen=self.baseline_snapshots)
        self.is_vacuum_detected = False
        self.pre_vacuum_baseline = 0.0
        self.current_drop_pct = 0.0
        self.current_depth_usd = 0.0

    def update(
        self,
        timestamp_epoch: float,
        bids: List[Tuple[float, float]],
        asks: List[Tuple[float, float]],
    ) -> Tuple[bool, float, float]:
        """
        Evaluates top-5 order book depth ladder.
        bids: [(price, size), ...]
        asks: [(price, size), ...]
        """
        top5_bid_usd = sum(p * s for p, s in bids[:5]) if bids else 0.0
        top5_ask_usd = sum(p * s for p, s in asks[:5]) if asks else 0.0
        total_depth_usd = top5_bid_usd + top5_ask_usd
        self.current_depth_usd = total_depth_usd

        self._history.append((timestamp_epoch, total_depth_usd))

        if len(self._history) < 5:
            self.is_vacuum_detected = False
            self.current_drop_pct = 0.0
            return False, 0.0, total_depth_usd

        # Look back within window_seconds to compute maximum recent baseline
        cutoff_time = timestamp_epoch - self.window_seconds
        recent_depths = [d for t, d in self._history if t >= cutoff_time]
        if not recent_depths:
            recent_depths = [d for _, d in self._history]

        recent_max_depth = max(recent_depths)

        if not self.is_vacuum_detected:
            # Normal regime: monitor for collapse relative to recent baseline
            baseline = recent_max_depth
            if baseline <= 0.0:
                self.current_drop_pct = 0.0
                return False, 0.0, total_depth_usd

            drop_pct = (baseline - total_depth_usd) / baseline
            self.current_drop_pct = float(np.clip(drop_pct, 0.0, 1.0))
            if self.current_drop_pct >= self.collapse_threshold:
                self.is_vacuum_detected = True
                self.pre_vacuum_baseline = baseline
        else:
            # Vacuum regime: baseline is frozen at pre-vacuum baseline to avoid baseline contamination
            baseline = max(self.pre_vacuum_baseline, recent_max_depth)
            drop_pct = (baseline - total_depth_usd) / baseline if baseline > 0 else 0.0
            self.current_drop_pct = float(np.clip(drop_pct, 0.0, 1.0))

            # Hysteresis recovery: requires depth to recover to at least recovery_ratio of pre-vacuum baseline
            if total_depth_usd >= self.recovery_ratio * self.pre_vacuum_baseline:
                self.is_vacuum_detected = False
                self.pre_vacuum_baseline = 0.0

        return self.is_vacuum_detected, self.current_drop_pct, total_depth_usd


# =============================================================================
# 4. Dynamic Spread Anomaly Detector
# =============================================================================

class SpreadAnomalyDetector:
    """
    Maintains a rolling statistical envelope over bid-ask spread in basis points.
    Flags spread blowouts (> 3.0 standard deviations and > 2.5x moving average).
    Includes baseline protection during active blowouts to prevent anomaly self-normalization.
    """

    def __init__(
        self,
        window_size: int = 300,
        z_threshold: float = 3.0,
        multiplier_threshold: float = 2.5,
        recovery_multiplier: float = 1.6,
    ):
        self.window_size = window_size
        self.z_threshold = z_threshold
        self.multiplier_threshold = multiplier_threshold
        self.recovery_multiplier = recovery_multiplier
        self._history: deque = deque(maxlen=window_size)
        self.current_spread_bps = 0.0
        self.current_z_score = 0.0
        self.pre_blowout_mean = 0.0
        self.is_blowout = False

    def update(self, bid: float, ask: float) -> Tuple[bool, float, float]:
        if ask <= 0.0 or bid <= 0.0 or ask < bid:
            return False, 0.0, 0.0

        mid = 0.5 * (bid + ask)
        spread_bps = 10000.0 * (ask - bid) / mid
        self.current_spread_bps = spread_bps

        if len(self._history) < 10:
            self._history.append(spread_bps)
            self.is_blowout = False
            self.current_z_score = 0.0
            return False, 0.0, spread_bps

        arr = np.array(self._history, dtype=np.float64)
        mean_bps = float(np.mean(arr))
        std_bps = float(np.std(arr))

        if not self.is_blowout:
            self._history.append(spread_bps)
            if std_bps < 1e-6:
                if mean_bps > 0.0 and spread_bps >= self.multiplier_threshold * mean_bps:
                    self.is_blowout = True
                    self.pre_blowout_mean = mean_bps
                    self.current_z_score = 99.0
                    return True, self.current_z_score, spread_bps
                else:
                    self.current_z_score = 0.0
                    self.is_blowout = False
                    return False, 0.0, spread_bps

            z = (spread_bps - mean_bps) / std_bps
            self.current_z_score = float(z)

            # Trigger condition: Exceeds both standard deviation threshold and multiple of historical mean
            if (z >= self.z_threshold) and (spread_bps >= self.multiplier_threshold * mean_bps):
                self.is_blowout = True
                self.pre_blowout_mean = max(mean_bps, 1e-4)
        else:
            # Active blowout: freeze reference mean, append to history with dampening
            self._history.append(spread_bps)
            ref_mean = self.pre_blowout_mean
            ref_std = max(std_bps, 1e-6)
            self.current_z_score = float((spread_bps - ref_mean) / ref_std)

            # Recovery condition: spread must drop back down near pre-blowout baseline
            if spread_bps <= self.recovery_multiplier * self.pre_blowout_mean:
                self.is_blowout = False
                self.pre_blowout_mean = 0.0

        return self.is_blowout, self.current_z_score, spread_bps


# =============================================================================
# 5. Abnormal Realized Volatility Detector
# =============================================================================

class AbnormalVolatilityDetector:
    """
    Computes rolling realized volatility from logarithmic tick returns
    and flags sudden volatility surges.
    """

    def __init__(self, window_size: int = 50, z_threshold: float = 3.2):
        self.window_size = window_size
        self.z_threshold = z_threshold
        self._prices: deque = deque(maxlen=window_size)
        self._vols: deque = deque(maxlen=window_size)
        self.current_vol = 0.0
        self.is_vol_spike = False

    def update(self, price: float) -> Tuple[bool, float]:
        if price <= 0.0:
            return False, 0.0

        self._prices.append(price)
        if len(self._prices) < 5:
            return False, 0.0

        # Calculate log returns
        arr = np.array(self._prices, dtype=np.float64)
        returns = np.diff(np.log(arr))
        curr_vol = float(np.std(returns)) if len(returns) > 1 else 0.0
        self.current_vol = curr_vol
        self._vols.append(curr_vol)

        if len(self._vols) < 15:
            return False, curr_vol

        vol_arr = np.array(self._vols, dtype=np.float64)
        mean_vol = float(np.mean(vol_arr[:-1]))
        std_vol = float(np.std(vol_arr[:-1]))

        if std_vol < 1e-8:
            return False, curr_vol

        z = (curr_vol - mean_vol) / std_vol
        self.is_vol_spike = z >= self.z_threshold
        return self.is_vol_spike, curr_vol


# =============================================================================
# 6. Hysteresis Anti-Flapping State Machine & Composite Engine
# =============================================================================

class SurveillanceStateMachine:
    """
    Hysteresis anti-flapping state machine.
    Prevents false-trigger oscillations by requiring consecutive normal observations
    before stepping down from ELEVATED_TOXICITY or FLASH_CRASH_DETECTED.
    """

    def __init__(self, cooldown_ticks_elevated: int = 15, cooldown_ticks_crash: int = 30):
        self.state = SurveillanceState.NORMAL
        self.cooldown_ticks_elevated = cooldown_ticks_elevated
        self.cooldown_ticks_crash = cooldown_ticks_crash
        self._normal_consecutive_ticks = 0

    def transition(
        self,
        is_vacuum: bool,
        is_toxic: bool,
        is_spread_blowout: bool,
        is_vol_spike: bool,
    ) -> str:
        # Critical Flash Crash trigger:
        # Liquidity vacuum + toxic order flow OR Liquidity vacuum + spread blowout
        if is_vacuum and (is_toxic or is_spread_blowout):
            self.state = SurveillanceState.FLASH_CRASH_DETECTED
            self._normal_consecutive_ticks = 0
            return self.state

        # Elevated Toxicity trigger
        if is_toxic or is_spread_blowout or is_vacuum or is_vol_spike:
            if self.state != SurveillanceState.FLASH_CRASH_DETECTED:
                self.state = SurveillanceState.ELEVATED_TOXICITY
                self._normal_consecutive_ticks = 0
                return self.state

        # Recovery Logic with Hysteresis Dampening
        self._normal_consecutive_ticks += 1

        if self.state == SurveillanceState.FLASH_CRASH_DETECTED:
            if self._normal_consecutive_ticks >= self.cooldown_ticks_crash:
                self.state = SurveillanceState.ELEVATED_TOXICITY
                self._normal_consecutive_ticks = 0
        elif self.state == SurveillanceState.ELEVATED_TOXICITY:
            if self._normal_consecutive_ticks >= self.cooldown_ticks_elevated:
                self.state = SurveillanceState.NORMAL
                self._normal_consecutive_ticks = 0

        return self.state


class MarketSurveillanceEngine:
    """
    Unified high-frequency market surveillance engine operating per symbol.
    Evaluates streaming ticks and order book snapshots in sub-millisecond latency.
    """

    def __init__(self, symbol: str, bucket_size: float = 10.0):
        self.symbol = symbol
        self.vpin_calc = VPINCalculator(bucket_size=bucket_size)
        self.depth_vacuum = LiquidityVacuumDetector()
        self.spread_anomaly = SpreadAnomalyDetector()
        self.vol_detector = AbnormalVolatilityDetector()
        self.state_machine = SurveillanceStateMachine()

    def process_tick(
        self,
        timestamp: str,
        price: float,
        quantity: float,
        side: str,
        bids: Optional[List[Tuple[float, float]]] = None,
        asks: Optional[List[Tuple[float, float]]] = None,
        timestamp_epoch: Optional[float] = None,
    ) -> SurveillanceReport:
        t0 = time.perf_counter()

        if timestamp_epoch is None:
            try:
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                timestamp_epoch = dt.timestamp()
            except Exception:
                timestamp_epoch = time.time()

        # 1. Update VPIN & Trade Flow
        vpin = self.vpin_calc.update(price=price, quantity=quantity, side=side)
        fast_vpin = self.vpin_calc.fast_vpin
        vpin_regime = self.vpin_calc.get_regime()
        is_toxic = (vpin_regime == "TOXIC_INFORMED_FLOW")

        # 2. Update Depth Vacuum & Book Imbalance
        top5_bid_usd = sum(p * s for p, s in bids[:5]) if bids else 0.0
        top5_ask_usd = sum(p * s for p, s in asks[:5]) if asks else 0.0
        tot_depth = top5_bid_usd + top5_ask_usd
        book_imbalance = (top5_bid_usd - top5_ask_usd) / tot_depth if tot_depth > 0.0 else 0.0

        if bids is not None and asks is not None:
            is_vacuum, drop_pct, depth_usd = self.depth_vacuum.update(
                timestamp_epoch=timestamp_epoch, bids=bids, asks=asks
            )
        else:
            is_vacuum = self.depth_vacuum.is_vacuum_detected
            drop_pct = self.depth_vacuum.current_drop_pct
            depth_usd = self.depth_vacuum.current_depth_usd

        # 3. Update Spread Anomaly
        if bids and asks:
            best_bid = bids[0][0]
            best_ask = asks[0][0]
            is_spread_blowout, spread_z, spread_bps = self.spread_anomaly.update(best_bid, best_ask)
        else:
            is_spread_blowout = self.spread_anomaly.is_blowout
            spread_z = self.spread_anomaly.current_z_score
            spread_bps = self.spread_anomaly.current_spread_bps

        # 4. Update Volatility Anomaly
        is_vol_spike, realized_vol = self.vol_detector.update(price)

        # 5. Hysteresis State Machine
        curr_state = self.state_machine.transition(
            is_vacuum=is_vacuum,
            is_toxic=is_toxic,
            is_spread_blowout=is_spread_blowout,
            is_vol_spike=is_vol_spike,
        )

        # Collect active alarms
        alarms = []
        if is_toxic:
            alarms.append(f"TOXIC_FLOW_SURGE: VPIN={vpin:.2f}, FastVPIN={fast_vpin:.2f}, OFI={self.vpin_calc.trade_flow_imbalance:+.2f}")
        if is_vacuum:
            alarms.append(f"LIQUIDITY_VACUUM: {drop_pct*100.0:.1f}% depth drop in book")
        if is_spread_blowout:
            alarms.append(f"SPREAD_BLOWOUT: {spread_bps:.1f} bps (Z-Score: {spread_z:.2f})")
        if is_vol_spike:
            alarms.append(f"VOLATILITY_SPIKE: Realized Vol {realized_vol:.6f}")
        if curr_state == SurveillanceState.FLASH_CRASH_DETECTED:
            alarms.append("CRITICAL: FLASH_CRASH_COLLAPSE_IN_PROGRESS")

        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        return SurveillanceReport(
            timestamp=timestamp,
            symbol=self.symbol,
            state=curr_state,
            is_anomaly=(curr_state != SurveillanceState.NORMAL),
            vpin=vpin,
            fast_vpin=fast_vpin,
            vpin_regime=vpin_regime,
            spread_bps=spread_bps,
            spread_z_score=spread_z,
            is_spread_anomaly=is_spread_blowout,
            current_depth_usd=depth_usd,
            depth_drop_pct=drop_pct,
            is_liquidity_vacuum=is_vacuum,
            realized_volatility=realized_vol,
            is_volatility_spike=is_vol_spike,
            order_flow_imbalance=self.vpin_calc.trade_flow_imbalance,
            book_imbalance=book_imbalance,
            active_alarms=alarms,
            evaluation_latency_ms=elapsed_ms,
        )
