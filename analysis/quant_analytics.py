"""
QuantPulse: Quantitative Analytics & Microstructure Validation Engine
====================================================================
Computes statistical moments of log-return distributions, verifies leptokurtic
fat tails from Merton Jump Diffusion, aggregates ticks into multi-timeframe OHLCV bars,
and runs sub-5ms vectorized DuckDB SQL over the partitioned market lakehouse.
"""

import math
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

import duckdb
import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def compute_log_returns(prices: np.ndarray) -> np.ndarray:
    """Computes continuous log-returns r_t = ln(S_t / S_{t-1})."""
    if len(prices) < 2:
        return np.array([])
    prices = np.asarray(prices, dtype=float)
    # Filter out zero or negative prices if any
    prices = np.where(prices <= 0, 1e-6, prices)
    return np.diff(np.log(prices))


def compute_distribution_moments(returns: np.ndarray) -> Dict[str, float]:
    """
    Computes statistical moments of the return distribution:
    1. Mean (drift)
    2. Variance & Standard Deviation (volatility)
    3. Skewness (asymmetry)
    4. Kurtosis & Excess Kurtosis (leptokurtic fat-tail indicator)
    """
    if len(returns) < 4:
        return {
            "count": len(returns),
            "mean": 0.0,
            "std": 0.0,
            "skewness": 0.0,
            "kurtosis": 3.0,
            "excess_kurtosis": 0.0,
            "is_leptokurtic": False,
        }

    n = len(returns)
    mean = float(np.mean(returns))
    std = float(np.std(returns, ddof=1))

    if std < 1e-12:
        return {
            "count": n,
            "mean": mean,
            "std": 0.0,
            "skewness": 0.0,
            "kurtosis": 3.0,
            "excess_kurtosis": 0.0,
            "is_leptokurtic": False,
        }

    z = (returns - mean) / std

    # Sample skewness (Fisher-Pearson)
    skewness = float((n / ((n - 1) * (n - 2))) * np.sum(z ** 3)) if n > 2 else 0.0

    # Sample kurtosis (Gaussian = 3.0)
    term1 = (n * (n + 1)) / ((n - 1) * (n - 2) * (n - 3)) if n > 3 else 1.0
    term2 = (3 * (n - 1) ** 2) / ((n - 2) * (n - 3)) if n > 3 else 3.0
    kurtosis = float(term1 * np.sum(z ** 4) - term2 + 3.0) if n > 3 else 3.0
    excess_kurtosis = float(kurtosis - 3.0)

    return {
        "count": n,
        "mean": mean,
        "std": std,
        "skewness": round(skewness, 4),
        "kurtosis": round(kurtosis, 4),
        "excess_kurtosis": round(excess_kurtosis, 4),
        "is_leptokurtic": excess_kurtosis > 0.0,
    }


def detect_jumps(prices: np.ndarray, threshold_sigma: float = 3.0) -> Dict[str, Any]:
    """
    Identifies discrete Poisson jump arrivals where return magnitude |r_t| > threshold_sigma * std.
    """
    returns = compute_log_returns(prices)
    if len(returns) < 4:
        return {"jump_count": 0, "jump_indices": [], "jump_magnitudes": [], "jump_pct": 0.0}

    mean = np.mean(returns)
    std = np.std(returns)
    z_scores = np.abs(returns - mean) / max(1e-12, std)

    jump_indices = np.where(z_scores > threshold_sigma)[0]
    jump_magnitudes = [float(returns[i]) for i in jump_indices]

    return {
        "jump_count": len(jump_indices),
        "jump_indices": jump_indices.tolist(),
        "jump_magnitudes": jump_magnitudes,
        "jump_pct": round(len(jump_indices) / len(returns) * 100.0, 3),
    }


def aggregate_ohlcv(df: pd.DataFrame, freq: str = "1min") -> pd.DataFrame:
    """
    Aggregates high-frequency tick records into standard OHLCV candlestick bars.
    Computes Volume-Weighted Average Price (VWAP) per bar.
    """
    if df.empty or "timestamp" not in df.columns or "price" not in df.columns:
        return pd.DataFrame()

    dff = df.copy()
    if not pd.api.types.is_datetime64_any_dtype(dff["timestamp"]):
        dff["timestamp"] = pd.to_datetime(dff["timestamp"])

    dff.set_index("timestamp", inplace=True)
    dff.sort_index(inplace=True)

    dff["notional"] = dff["price"] * dff["quantity"]

    grouped = dff.resample(freq)
    ohlcv = pd.DataFrame({
        "open": grouped["price"].first(),
        "high": grouped["price"].max(),
        "low": grouped["price"].min(),
        "close": grouped["price"].last(),
        "volume": grouped["quantity"].sum(),
        "trade_count": grouped["price"].count(),
        "vwap": grouped["notional"].sum() / grouped["quantity"].sum().replace(0, np.nan),
    })

    # Forward-fill close price for empty bars, zero out volume
    ohlcv["close"] = ohlcv["close"].ffill()
    ohlcv["open"] = ohlcv["open"].fillna(ohlcv["close"])
    ohlcv["high"] = ohlcv["high"].fillna(ohlcv["close"])
    ohlcv["low"] = ohlcv["low"].fillna(ohlcv["close"])
    ohlcv["volume"] = ohlcv["volume"].fillna(0.0)
    ohlcv["trade_count"] = ohlcv["trade_count"].fillna(0).astype(int)
    ohlcv["vwap"] = ohlcv["vwap"].fillna(ohlcv["close"])

    return ohlcv.reset_index()


def compute_microstructure_kpis(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Calculates essential market microstructure health and liquidity metrics:
    - Average Bid-Ask spread in basis points
    - Average Effective Spread: 2 * |P_trade - P_mid|
    - Realized Volatility
    - Micro-price divergence: |P_micro - P_mid|
    """
    if df.empty:
        return {}

    kpis: Dict[str, Any] = {"total_trades": len(df)}

    if "spread_bps" in df.columns:
        kpis["avg_spread_bps"] = round(float(df["spread_bps"].mean()), 2)
        kpis["max_spread_bps"] = round(float(df["spread_bps"].max()), 2)

    if "mid_price" in df.columns and "price" in df.columns:
        eff_spread = 2.0 * np.abs(df["price"] - df["mid_price"])
        eff_spread_bps = (eff_spread / df["mid_price"]) * 10000.0
        kpis["avg_effective_spread_bps"] = round(float(eff_spread_bps.mean()), 2)

    if "micro_price" in df.columns and "mid_price" in df.columns:
        micro_div_bps = (np.abs(df["micro_price"] - df["mid_price"]) / df["mid_price"]) * 10000.0
        kpis["avg_micro_price_divergence_bps"] = round(float(micro_div_bps.mean()), 3)

    if "price" in df.columns and len(df) > 5:
        rets = compute_log_returns(df["price"].values)
        moments = compute_distribution_moments(rets)
        kpis.update(moments)

    return kpis


def query_lakehouse_with_duckdb(lake_dir: str, sql: str) -> pd.DataFrame:
    """
    Executes a vectorized zero-copy DuckDB SQL query directly across the partitioned Parquet lake.
    """
    con = duckdb.connect()
    # Replace placeholder token with glob path
    parquet_glob = os.path.join(lake_dir, "**", "*.parquet").replace("\\", "/")
    executable_sql = sql.replace("{lake_ticks}", f"read_parquet('{parquet_glob}', hive_partitioning=true)")

    try:
        res = con.execute(executable_sql).df()
        return res
    finally:
        con.close()


if __name__ == "__main__":
    prices = np.array([100.0, 100.5, 100.2, 101.8, 101.5, 105.0, 104.8, 104.9])
    rets = compute_log_returns(prices)
    stats = compute_distribution_moments(rets)
    print("Return Statistics:", stats)
