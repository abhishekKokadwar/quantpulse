"""
QuantPulse: Statistical Arbitrage & Cointegrated Pairs Engine (Phase 6)
======================================================================
High-frequency statistical arbitrage engine implementing:
1. Engle-Granger Two-Step Cointegration Test with Augmented Dickey-Fuller (ADF)
   residual stationarity verification and MacKinnon critical value bounds.
2. Dynamic Online Kalman Filter tracking state-space time-varying hedge ratios (beta_t)
   and equilibrium spreads: ln(P_A) = alpha_t + beta_t * ln(P_B) + epsilon_t.
3. Mean-Reversion Signal State Machine:
   - Entry: |Z| > 2.0 (Long undervalued, Short overvalued)
   - Exit: |Z| < 0.5 (Mean reversion profit target)
   - Circuit Breaker: |Z| > 3.5 (Structural divergence stop-loss)
"""

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import math
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


class StatArbState(Enum):
    """Trading states for the statistical arbitrage state machine."""
    IDLE = "IDLE"
    LONG_SPREAD = "LONG_SPREAD"    # Long Asset A, Short Asset B (Spread is undervalued: Z < -2.0)
    SHORT_SPREAD = "SHORT_SPREAD"  # Short Asset A, Long Asset B (Spread is overvalued: Z > +2.0)
    EXIT_MEAN_REVERT = "EXIT_MEAN_REVERT"  # Reverted to equilibrium (|Z| <= 0.5)
    CIRCUIT_BREAKER_STOP = "CIRCUIT_BREAKER_STOP"  # Emergency stop-loss (|Z| >= 3.5)


# =============================================================================
# 1. Engle-Granger Two-Step Cointegration Test
# =============================================================================

def engle_granger_cointegration_test(
    series_a: np.ndarray,
    series_b: np.ndarray,
    max_lags: int = 1,
) -> Dict[str, Any]:
    """
    Executes the Engle-Granger Two-Step Cointegration Test:
    Step 1: OLS hedge regression: ln(P_A) = alpha + beta * ln(P_B) + epsilon.
    Step 2: Augmented Dickey-Fuller (ADF) unit-root regression on residuals:
            Delta epsilon_t = gamma * epsilon_{t-1} + sum(delta_i * Delta epsilon_{t-i}) + u_t.
    Rejects null hypothesis of unit root when t-stat < critical value (-3.34 at 95% confidence).
    """
    if len(series_a) != len(series_b) or len(series_a) < 30:
        raise ValueError(f"Series length must match and contain at least 30 observations (got {len(series_a)})")

    # Log prices
    y = np.log(np.maximum(1e-8, np.asarray(series_a, dtype=np.float64)))
    x = np.log(np.maximum(1e-8, np.asarray(series_b, dtype=np.float64)))

    # Step 1: OLS Regression
    slope, intercept, r_val, p_val_ols, std_err = stats.linregress(x, y)
    residuals = y - (intercept + slope * x)

    # Step 2: ADF Test on Residuals
    d_res = np.diff(residuals)
    res_lag = residuals[:-1]

    # Build regression matrix with lagged differences if max_lags > 0
    n = len(d_res)
    if max_lags == 0 or n <= max_lags + 2:
        # Simple DF regression: Delta res_t = gamma * res_{t-1} + u_t
        reg_x = res_lag.reshape(-1, 1)
        reg_y = d_res
    else:
        # ADF with lagged difference terms
        lagged_diffs = []
        for lag in range(1, max_lags + 1):
            lagged_diffs.append(d_res[max_lags - lag : n - lag])
        lagged_diffs_matrix = np.column_stack(lagged_diffs)
        reg_x = np.column_stack([res_lag[max_lags:], lagged_diffs_matrix])
        reg_y = d_res[max_lags:]

    # OLS estimation: (X^T X)^{-1} X^T Y
    try:
        XtX_inv = np.linalg.pinv(reg_x.T @ reg_x)
        beta_coeffs = XtX_inv @ (reg_x.T @ reg_y)
        gamma = float(beta_coeffs[0])

        # Residuals of ADF regression
        adf_res = reg_y - reg_x @ beta_coeffs
        sigma_sq = float(np.sum(adf_res ** 2) / max(1, len(reg_y) - reg_x.shape[1]))
        gamma_se = float(np.sqrt(max(1e-12, sigma_sq * XtX_inv[0, 0])))
        t_stat = float(gamma / gamma_se)
    except Exception:
        gamma = 0.0
        t_stat = 0.0

    # MacKinnon (1991) critical values for cointegration with 2 variables (constant, no trend)
    crit_values = {
        "1%": -3.90,
        "5%": -3.34,
        "10%": -3.04,
    }

    # Cointegrated at 95% confidence if t_stat < -3.34
    is_cointegrated = t_stat < crit_values["5%"]

    # Approximate asymptotic p-value estimation
    if t_stat < -4.0:
        p_val_approx = 0.005
    elif t_stat < -3.34:
        p_val_approx = 0.03
    elif t_stat < -3.04:
        p_val_approx = 0.08
    elif t_stat < -2.50:
        p_val_approx = 0.20
    else:
        p_val_approx = 0.50

    return {
        "is_cointegrated": is_cointegrated,
        "t_stat": round(t_stat, 4),
        "critical_values": crit_values,
        "p_value_approx": p_val_approx,
        "hedge_ratio": round(float(slope), 4),
        "intercept": round(float(intercept), 4),
        "r_squared": round(float(r_val ** 2), 4),
        "half_life_bars": round(float(-np.log(2) / gamma), 1) if gamma < 0 else None,
    }


# =============================================================================
# 2. Dynamic Online Kalman Filter Hedge Ratio Tracker
# =============================================================================

class KalmanHedgeRatioTracker:
    """
    Online state-space Kalman Filter dynamically estimating time-varying hedge ratios:
        ln(P_A(t)) = alpha_t + beta_t * ln(P_B(t)) + epsilon_t
    State vector: theta_t = [alpha_t, beta_t]^T
    """

    def __init__(
        self,
        delta: float = 1e-4,
        observation_variance: float = 1e-3,
        initial_beta: float = 1.0,
        initial_alpha: float = 0.0,
    ):
        # State vector: [alpha, beta]
        self.theta = np.array([initial_alpha, initial_beta], dtype=np.float64)

        # State covariance P
        self.P = np.eye(2, dtype=np.float64) * 1.0

        # Process noise covariance W
        self.W = np.eye(2, dtype=np.float64) * delta

        # Measurement noise variance V
        self.V = observation_variance

    def update(self, price_a: float, price_b: float) -> Tuple[float, float, float]:
        """
        Processes a new price pair tick sequentially.
        Returns: (current_alpha, current_beta, spread).
        """
        y = math.log(max(1e-8, price_a))
        x = math.log(max(1e-8, price_b))

        # Observation matrix H = [1, x]
        H = np.array([[1.0, x]], dtype=np.float64)

        # 1. Time Update (Predict)
        theta_prior = self.theta.copy()
        P_prior = self.P + self.W

        # 2. Measurement Update (Correct)
        # Innovation (spread)
        y_hat = float((H @ theta_prior)[0])
        error = y - y_hat

        # Innovation covariance
        S = float((H @ P_prior @ H.T)[0, 0]) + self.V

        # Kalman gain: K = P_prior * H^T / S
        K = (P_prior @ H.T) / S

        # Posterior state estimate
        self.theta = theta_prior + (K * error).flatten()

        # Posterior covariance
        self.P = (np.eye(2) - K @ H) @ P_prior

        alpha = float(self.theta[0])
        beta = float(self.theta[1])
        spread = y - (alpha + beta * x)

        return alpha, beta, spread

    def batch_filter(
        self, prices_a: np.ndarray, prices_b: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Runs the Kalman filter over historical price series."""
        n = len(prices_a)
        alphas = np.zeros(n, dtype=np.float64)
        betas = np.zeros(n, dtype=np.float64)
        spreads = np.zeros(n, dtype=np.float64)

        for i in range(n):
            a, b, s = self.update(prices_a[i], prices_b[i])
            alphas[i] = a
            betas[i] = b
            spreads[i] = s

        return alphas, betas, spreads


# =============================================================================
# 3. Mean-Reversion Signal State Machine
# =============================================================================

@dataclass
class StatArbSignal:
    """Represents a trading signal dispatched by the pairs trading engine."""
    timestamp: str
    pair: str
    state: StatArbState
    spread: float
    z_score: float
    hedge_ratio: float
    action: str
    message: str


class StatArbSignalGenerator:
    """
    Generates mean-reverting trading signals from dynamic Kalman spreads
    with hysteresis thresholds and emergency circuit breaker stops.
    """

    def __init__(
        self,
        pair_label: str = "BTC/USDT-ETH/USDT",
        z_entry: float = 2.0,
        z_exit: float = 0.5,
        z_circuit_breaker: float = 3.5,
        lookback_window: int = 50,
    ):
        self.pair_label = pair_label
        self.z_entry = z_entry
        self.z_exit = z_exit
        self.z_circuit_breaker = z_circuit_breaker
        self.lookback_window = lookback_window

        self.current_state = StatArbState.IDLE
        self.spread_history: List[float] = []

    def process_tick(
        self,
        timestamp: str,
        spread: float,
        hedge_ratio: float,
    ) -> StatArbSignal:
        """Processes a single spread observation and evaluates state transitions."""
        self.spread_history.append(spread)
        if len(self.spread_history) > 1000:
            self.spread_history.pop(0)

        # Compute rolling Z-score
        window_spreads = self.spread_history[-self.lookback_window:]
        if len(window_spreads) < 10:
            z_score = 0.0
        else:
            mean = float(np.mean(window_spreads))
            std = float(np.std(window_spreads, ddof=1))
            z_score = float((spread - mean) / max(1e-8, std))

        # Evaluate State Machine Transitions
        action = "HOLD"
        message = f"Z-score {z_score:+.2f} within normal band"

        # 1. Stop-Loss Circuit Breaker (highest priority)
        if abs(z_score) >= self.z_circuit_breaker and self.current_state in [StatArbState.LONG_SPREAD, StatArbState.SHORT_SPREAD]:
            self.current_state = StatArbState.CIRCUIT_BREAKER_STOP
            action = "EMERGENCY_FLATTEN"
            message = f"CIRCUIT BREAKER: |Z|={abs(z_score):.2f} >= {self.z_circuit_breaker}. Structural break stop-loss triggered."

        # 2. Exit / Mean Reversion Target
        elif abs(z_score) <= self.z_exit and self.current_state in [StatArbState.LONG_SPREAD, StatArbState.SHORT_SPREAD]:
            self.current_state = StatArbState.EXIT_MEAN_REVERT
            action = "FLATTEN_PROFIT"
            message = f"EXIT: Spread reverted to equilibrium (|Z|={abs(z_score):.2f} <= {self.z_exit})."

        # 3. Long Spread Entry (Spread undervalued: Z < -z_entry)
        elif z_score <= -self.z_entry and self.current_state in [StatArbState.IDLE, StatArbState.EXIT_MEAN_REVERT]:
            self.current_state = StatArbState.LONG_SPREAD
            action = "ENTER_LONG_SPREAD"
            message = f"ENTRY LONG: Z={z_score:+.2f} <= -{self.z_entry}. Long Asset A / Short {hedge_ratio:.3f} Asset B."

        # 4. Short Spread Entry (Spread overvalued: Z > +z_entry)
        elif z_score >= self.z_entry and self.current_state in [StatArbState.IDLE, StatArbState.EXIT_MEAN_REVERT]:
            self.current_state = StatArbState.SHORT_SPREAD
            action = "ENTER_SHORT_SPREAD"
            message = f"ENTRY SHORT: Z={z_score:+.2f} >= +{self.z_entry}. Short Asset A / Long {hedge_ratio:.3f} Asset B."

        # Reset post-exit to IDLE
        if self.current_state in [StatArbState.EXIT_MEAN_REVERT, StatArbState.CIRCUIT_BREAKER_STOP] and abs(z_score) < self.z_entry:
            self.current_state = StatArbState.IDLE

        return StatArbSignal(
            timestamp=timestamp,
            pair=self.pair_label,
            state=self.current_state,
            spread=round(spread, 6),
            z_score=round(z_score, 4),
            hedge_ratio=round(hedge_ratio, 4),
            action=action,
            message=message,
        )


# =============================================================================
# 4. CLI Runner
# =============================================================================

def run_stat_arb_analysis(pair: str = "BTC/USDT,ETH/USDT", n_bars: int = 500) -> None:
    """Executes end-to-end cointegration testing and dynamic Kalman filtering on asset pair."""
    from simulator.market_simulator import MarketSimulator
    from analysis.quant_analytics import aggregate_ohlcv

    sym_a, sym_b = [s.strip() for s in pair.split(",")]

    print("\n========================================================")
    print(f" [QuantPulse] Statistical Arbitrage & Cointegration Engine")
    print("========================================================")
    print(f"Pair:        {sym_a} vs {sym_b}")
    print(f"Candles:     {n_bars} (1-minute OHLCV)")
    print("--------------------------------------------------------\n")

    sim = MarketSimulator(seed=42)
    # Generate ticks for both instruments
    ticks_a = sim.generate_historical_dataset(days=1, ticks_per_symbol=n_bars * 15, symbols=[sym_a])
    ticks_b = sim.generate_historical_dataset(days=1, ticks_per_symbol=n_bars * 15, symbols=[sym_b])

    df_bars_a = aggregate_ohlcv(pd.DataFrame(ticks_a), freq="1min").set_index("timestamp")
    df_bars_b = aggregate_ohlcv(pd.DataFrame(ticks_b), freq="1min").set_index("timestamp")

    common_idx = df_bars_a.index.intersection(df_bars_b.index)
    prices_a = df_bars_a.loc[common_idx, "close"].values
    prices_b = df_bars_b.loc[common_idx, "close"].values

    print(f"[DATASET] Aligned {len(common_idx)} timestamped 1-minute close prices.")

    # 1. Engle-Granger Cointegration Test
    eg_res = engle_granger_cointegration_test(prices_a, prices_b)
    print("\n[ENGLE-GRANGER COINTEGRATION TEST]")
    print(f"  * Cointegrated (95% CI):     {'YES [OK]' if eg_res['is_cointegrated'] else 'NO (Weak Cointegration)'}")
    print(f"  * ADF Test t-Statistic:      {eg_res['t_stat']:+.4f} (5% Critical Value: {eg_res['critical_values']['5%']})")
    print(f"  * Static OLS Hedge Ratio:    {eg_res['hedge_ratio']:.4f}")
    print(f"  * Regression R-squared:      {eg_res['r_squared']:.4f}")
    if eg_res["half_life_bars"]:
        print(f"  * Mean-Reversion Half-Life:  {eg_res['half_life_bars']} minutes")

    # 2. Online Kalman Filter Dynamic Tracking
    kalman = KalmanHedgeRatioTracker(delta=1e-4, initial_beta=eg_res["hedge_ratio"])
    alphas, betas, spreads = kalman.batch_filter(prices_a, prices_b)

    print("\n[DYNAMIC KALMAN FILTER STATE TRACKING]")
    print(f"  * Initial Beta:              {eg_res['hedge_ratio']:.4f}")
    print(f"  * Final Adapted Beta:        {betas[-1]:.4f}")
    print(f"  * Beta Tracking Range:       [{np.min(betas):.4f}, {np.max(betas):.4f}]")
    print(f"  * Final Spread:              {spreads[-1]:+.6f}")

    # 3. Signal Generation Backtest
    sig_gen = StatArbSignalGenerator(pair_label=f"{sym_a}-{sym_b}")
    signals: List[StatArbSignal] = []
    for i in range(len(common_idx)):
        ts_str = str(common_idx[i])
        sig = sig_gen.process_tick(ts_str, spreads[i], betas[i])
        if sig.action != "HOLD":
            signals.append(sig)

    print(f"\n[STAT-ARB SIGNALS] Generated {len(signals)} actionable trade signals:")
    for s in signals[:6]:
        print(f"  * [{s.timestamp[:19]}] {s.action:<18} | Z={s.z_score:+.2f} | Beta={s.hedge_ratio:.3f} | {s.message}")

    print("\n========================================================\n")


def main():
    parser = argparse.ArgumentParser(description="QuantPulse Stat-Arb & Cointegration Engine CLI")
    parser.add_argument("--pair", default="BTC/USDT,ETH/USDT", help="Comma-separated asset pair")
    parser.add_argument("--candles", type=int, default=500, help="Number of 1m candles to analyze")
    args = parser.parse_args()

    run_stat_arb_analysis(pair=args.pair, n_bars=args.candles)


if __name__ == "__main__":
    main()
