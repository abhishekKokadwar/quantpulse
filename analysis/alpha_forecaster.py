"""
QuantPulse: Multi-Horizon Alpha Forecaster Engine (Phase 6)
===========================================================
Predictive machine learning pipeline forecasting multi-horizon forward returns
(t+1, t+5, t+15, t+60 minutes) using high-frequency market microstructure features:
- Order Flow Imbalance (OFI) & Order Book Skewness
- Micro-Price Divergence: (P_micro - P_mid) / P_mid
- Parkinson & Garman-Klass High-Low-Open-Close Volatility Estimators
- Temporal Cyclical Harmonics (Time-of-day & Day-of-week sine/cosine)
- Momentum & Trend Indicators (RSI-14, MACD Histogram, Bollinger Band %B)

Adheres strictly to ml-best-practices:
- Chronological Train / Validation / Test data splitting
- Strict Featurization Ordering: Scalers fitted exclusively on training set
- Purged & Embargoed Cross-Validation (de Prado methodology) eliminating lookahead leakage
- Ensembled Gradient Boosted Decision Trees & Random Forest Regressors
"""

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import math
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.preprocessing import StandardScaler

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

DEFAULT_MODEL_DIR = os.path.join(PROJECT_ROOT, "analysis", "models")


# =============================================================================
# 1. Microstructure Feature Engineering
# =============================================================================

def calculate_parkinson_volatility(high: pd.Series, low: pd.Series, window: int = 14) -> pd.Series:
    """
    Computes Parkinson (1980) High-Low Volatility Estimator:
        sigma_p = sqrt( (1 / (4 * ln(2))) * sum(ln(H/L)^2) / window )
    Up to 5x more statistically efficient than close-to-close volatility.
    """
    hl_ratio = np.log(high.replace(0, np.nan) / low.replace(0, np.nan))
    factor = 1.0 / (4.0 * math.log(2.0))
    rolling_hl = (hl_ratio ** 2).rolling(window=window).mean()
    return np.sqrt(factor * rolling_hl).fillna(0.0)


def calculate_garman_klass_volatility(
    open_: pd.Series, high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14
) -> pd.Series:
    """
    Computes Garman-Klass (1980) Volatility Estimator:
        sigma_gk = sqrt( (1/N) * sum( 0.5 * ln(H/L)^2 - (2*ln(2) - 1) * ln(C/O)^2 ) )
    Accounts for both opening jumps and intraday trading range.
    """
    hl_term = 0.5 * (np.log(high.replace(0, np.nan) / low.replace(0, np.nan)) ** 2)
    co_factor = 2.0 * math.log(2.0) - 1.0
    co_term = co_factor * (np.log(close.replace(0, np.nan) / open_.replace(0, np.nan)) ** 2)
    gk_var = (hl_term - co_term).rolling(window=window).mean()
    # Clamp negative floating point approximations to zero
    return np.sqrt(np.maximum(0.0, gk_var)).fillna(0.0)


def calculate_rsi(prices: pd.Series, window: int = 14) -> pd.Series:
    """
    Computes Relative Strength Index (RSI) with 14-period exponential weighting.
    Bounded in [0.0, 100.0].
    """
    delta = prices.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    avg_gain = gain.ewm(com=window - 1, min_periods=window).mean()
    avg_loss = loss.ewm(com=window - 1, min_periods=window).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi.fillna(50.0)


def calculate_macd(prices: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.Series:
    """Computes MACD histogram: MACD Line - Signal Line."""
    ema_fast = prices.ewm(span=fast, adjust=False).mean()
    ema_slow = prices.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    macd_hist = macd_line - signal_line
    return macd_hist.fillna(0.0)


def calculate_bollinger_percent_b(prices: pd.Series, window: int = 20, num_std: float = 2.0) -> pd.Series:
    """Computes Bollinger Bands %B normalized price position."""
    sma = prices.rolling(window=window).mean()
    std = prices.rolling(window=window).std(ddof=1)
    upper = sma + (num_std * std)
    lower = sma - (num_std * std)
    pct_b = (prices - lower) / (upper - lower).replace(0, np.nan)
    return pct_b.fillna(0.5)


def engineer_alpha_features(
    df: pd.DataFrame,
    horizons: Optional[List[int]] = None,
) -> Tuple[pd.DataFrame, List[str], List[str]]:
    """
    Transforms raw OHLCV and microstructure data into a comprehensive feature matrix
    and multi-horizon forward return target labels.
    """
    if horizons is None:
        horizons = [1, 5, 15]

    data = df.copy()
    if not pd.api.types.is_datetime64_any_dtype(data["timestamp"]):
        data["timestamp"] = pd.to_datetime(data["timestamp"])
    data.sort_values("timestamp", inplace=True)
    data.reset_index(drop=True, inplace=True)

    feature_cols: List[str] = []

    # 1. Price Momentum & Returns
    data["log_ret_1"] = np.log(data["close"] / data["close"].shift(1)).fillna(0.0)
    data["log_ret_5"] = np.log(data["close"] / data["close"].shift(5)).fillna(0.0)
    data["log_ret_15"] = np.log(data["close"] / data["close"].shift(15)).fillna(0.0)
    feature_cols.extend(["log_ret_1", "log_ret_5", "log_ret_15"])

    # 2. Volatility Estimators
    data["vol_parkinson"] = calculate_parkinson_volatility(data["high"], data["low"], window=14)
    data["vol_garman_klass"] = calculate_garman_klass_volatility(
        data["open"], data["high"], data["low"], data["close"], window=14
    )
    feature_cols.extend(["vol_parkinson", "vol_garman_klass"])

    # 3. Microstructure Features
    if "vwap" in data.columns:
        data["vwap_divergence"] = (data["close"] - data["vwap"]) / data["vwap"].replace(0, np.nan)
        feature_cols.append("vwap_divergence")
    if "micro_price" in data.columns and "mid_price" in data.columns:
        data["micro_price_divergence"] = (data["micro_price"] - data["mid_price"]) / data["mid_price"].replace(0, np.nan)
        feature_cols.append("micro_price_divergence")
    if "order_flow_imbalance" in data.columns:
        data["ofi"] = data["order_flow_imbalance"].fillna(0.0)
        feature_cols.append("ofi")

    # 4. Technical Oscillators
    data["rsi_14"] = calculate_rsi(data["close"], window=14)
    data["macd_hist"] = calculate_macd(data["close"])
    data["bollinger_pct_b"] = calculate_bollinger_percent_b(data["close"], window=20)
    feature_cols.extend(["rsi_14", "macd_hist", "bollinger_pct_b"])

    # 5. Temporal Cyclical Harmonics (Minute of Day & Day of Week)
    minute_of_day = data["timestamp"].dt.hour * 60 + data["timestamp"].dt.minute
    data["sin_time_of_day"] = np.sin(2.0 * np.pi * minute_of_day / 1440.0)
    data["cos_time_of_day"] = np.cos(2.0 * np.pi * minute_of_day / 1440.0)
    day_of_week = data["timestamp"].dt.dayofweek
    data["sin_day_of_week"] = np.sin(2.0 * np.pi * day_of_week / 7.0)
    data["cos_day_of_week"] = np.cos(2.0 * np.pi * day_of_week / 7.0)
    feature_cols.extend(["sin_time_of_day", "cos_time_of_day", "sin_day_of_week", "cos_day_of_week"])

    # 6. Target Labels: Multi-Horizon Forward Log Returns
    target_cols: List[str] = []
    for h in horizons:
        col_name = f"target_fwd_ret_{h}"
        data[col_name] = np.log(data["close"].shift(-h) / data["close"])
        target_cols.append(col_name)

    # Clean intermediate NaNs from rolling indicators
    data.fillna(0.0, inplace=True)

    return data, feature_cols, target_cols


# =============================================================================
# 2. Purged & Embargoed Cross-Validation Splitter
# =============================================================================

class PurgedTimeSeriesSplitter:
    """
    Chronological time series splitter with purging and embargoing (Marcos Lopez de Prado).
    - Purging: Drops training observations whose forward return horizons overlap test labels.
    - Embargoing: Adds a buffer gap immediately following the test partition to eliminate
      serial correlation leakage.
    """

    def __init__(self, train_ratio: float = 0.70, val_ratio: float = 0.15, purge_bars: int = 5, embargo_bars: int = 5):
        self.train_ratio = train_ratio
        self.val_ratio = val_ratio
        self.purge_bars = purge_bars
        self.embargo_bars = embargo_bars

    def split(self, n_samples: int) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Returns chronological index arrays (train_indices, val_indices, test_indices)."""
        train_end = int(n_samples * self.train_ratio)
        val_end = int(n_samples * (self.train_ratio + self.val_ratio))

        # Purge boundary between train and validation
        train_idx = np.arange(0, max(0, train_end - self.purge_bars))

        # Embargo buffer at start of validation
        val_start = train_end + self.embargo_bars
        val_idx = np.arange(val_start, max(val_start, val_end - self.purge_bars))

        # Embargo buffer at start of test
        test_start = val_end + self.embargo_bars
        test_idx = np.arange(test_start, n_samples)

        return train_idx, val_idx, test_idx


# =============================================================================
# 3. Multi-Horizon Alpha Forecaster Model
# =============================================================================

class AlphaForecasterModel:
    """
    Multi-horizon directional return forecaster ensembling HistGradientBoosting
    and Random Forest regressors with strict featurization ordering.
    """

    def __init__(self, horizon_label: str = "1m", random_state: int = 42):
        self.horizon_label = horizon_label
        self.random_state = random_state
        self.scaler = StandardScaler()
        self.feature_names: List[str] = []

        self.gbt_model = HistGradientBoostingRegressor(
            max_iter=150,
            learning_rate=0.04,
            max_leaf_nodes=31,
            l2_regularization=1.5,
            random_state=random_state,
        )
        self.rf_model = RandomForestRegressor(
            n_estimators=100,
            max_depth=8,
            min_samples_leaf=10,
            n_jobs=-1,
            random_state=random_state,
        )
        self.is_fitted = False

    def fit(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_val: Optional[pd.DataFrame] = None,
        y_val: Optional[pd.Series] = None,
    ) -> "AlphaForecasterModel":
        """
        Fits preprocessing scaler and regression models strictly on training partition.
        """
        self.feature_names = list(X_train.columns)

        # Strict ordering: Scaler fit ONLY on training data
        X_train_scaled = self.scaler.fit_transform(X_train)

        # Train GBDT
        self.gbt_model.fit(X_train_scaled, y_train)

        # Train Random Forest
        self.rf_model.fit(X_train_scaled, y_train)

        self.is_fitted = True
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Generates ensemble prediction: average of GBDT and Random Forest forecasts."""
        if not self.is_fitted:
            raise RuntimeError("Model is not fitted. Call fit() first.")
        X_scaled = self.scaler.transform(X[self.feature_names])
        p_gbt = self.gbt_model.predict(X_scaled)
        p_rf = self.rf_model.predict(X_scaled)
        return 0.6 * p_gbt + 0.4 * p_rf

    def evaluate(self, X_test: pd.DataFrame, y_test: pd.Series) -> Dict[str, float]:
        """
        Evaluates quantitative predictive metrics:
        - Information Coefficient (Spearman Rank IC)
        - Directional Hit Rate (% correct return sign)
        - Root Mean Squared Error (RMSE)
        - Mean Absolute Error (MAE)
        """
        preds = self.predict(X_test)
        y_true = y_test.values

        # Spearman Rank IC
        rank_ic, p_val = stats.spearmanr(preds, y_true)
        if math.isnan(rank_ic):
            rank_ic = 0.0

        # Directional Hit Rate (sign match on non-zero movements)
        sign_pred = np.sign(preds)
        sign_true = np.sign(y_true)
        valid_mask = sign_true != 0
        if np.sum(valid_mask) > 0:
            hit_rate = float(np.mean(sign_pred[valid_mask] == sign_true[valid_mask]))
        else:
            hit_rate = 0.5

        rmse = float(np.sqrt(mean_squared_error(y_true, preds)))
        mae = float(mean_absolute_error(y_true, preds))

        return {
            "rank_ic": round(float(rank_ic), 4),
            "p_value": round(float(p_val), 6),
            "hit_rate": round(hit_rate, 4),
            "rmse": round(rmse, 6),
            "mae": round(mae, 6),
            "n_samples": len(y_test),
        }

    def save(self, path: str) -> None:
        """Serializes the fitted model pipeline to disk."""
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        joblib.dump(self, path)

    @classmethod
    def load(cls, path: str) -> "AlphaForecasterModel":
        """Loads a serialized model pipeline from disk."""
        return joblib.load(path)


# =============================================================================
# 4. End-to-End Training & CLI Runner
# =============================================================================

def train_alpha_forecaster_pipeline(
    symbol: str = "BTC/USDT",
    n_bars: int = 2000,
    horizon: int = 1,
) -> Tuple[AlphaForecasterModel, Dict[str, float]]:
    """
    Synthesizes historical microstructure bars, engineers features, trains
    the alpha model, and evaluates out-of-sample performance.
    """
    from simulator.market_simulator import MarketSimulator
    from analysis.quant_analytics import aggregate_ohlcv

    print("\n========================================================")
    print(f" [QuantPulse] Training Alpha Forecaster ({symbol} | t+{horizon}m)")
    print("========================================================")

    sim = MarketSimulator(seed=42)
    # Generate 50,000 synthetic ticks to form bars
    ticks = sim.generate_historical_dataset(days=1, ticks_per_symbol=n_bars * 15, symbols=[symbol])
    df_ticks = pd.DataFrame(ticks)
    df_bars = aggregate_ohlcv(df_ticks, freq="1min")

    if len(df_bars) < 100:
        raise ValueError(f"Insufficient bars generated: {len(df_bars)}")

    print(f"[DATASET] Aggregated {len(df_bars)} 1-minute OHLCV bars.")

    # 1. Feature Engineering
    df_feat, feature_cols, target_cols = engineer_alpha_features(df_bars, horizons=[horizon])
    target_col = f"target_fwd_ret_{horizon}"

    # Drop trailing rows where target is NaN due to forward shift
    valid_data = df_feat.dropna(subset=[target_col]).copy()
    print(f"[FEATURES] Generated {len(feature_cols)} features across {len(valid_data)} labeled samples.")

    # 2. Chronological Purged & Embargoed Split
    splitter = PurgedTimeSeriesSplitter(train_ratio=0.70, val_ratio=0.15, purge_bars=horizon, embargo_bars=horizon)
    train_idx, val_idx, test_idx = splitter.split(len(valid_data))

    X_train = valid_data.iloc[train_idx][feature_cols]
    y_train = valid_data.iloc[train_idx][target_col]
    X_val = valid_data.iloc[val_idx][feature_cols]
    y_val = valid_data.iloc[val_idx][target_col]
    X_test = valid_data.iloc[test_idx][feature_cols]
    y_test = valid_data.iloc[test_idx][target_col]

    print(f"[SPLIT] Train: {len(X_train)} | Validation: {len(X_val)} | Test (Out-of-Sample): {len(X_test)}")

    # 3. Model Training
    t0 = time.perf_counter()
    model = AlphaForecasterModel(horizon_label=f"{horizon}m")
    model.fit(X_train, y_train, X_val, y_val)
    train_time = time.perf_counter() - t0

    # 4. Out-of-Sample Evaluation
    metrics = model.evaluate(X_test, y_test)
    metrics["train_time_sec"] = round(train_time, 2)

    print("\n[OUT-OF-SAMPLE PERFORMANCE EVALUATION]")
    print(f"  * Information Coefficient (Rank IC): {metrics['rank_ic']:+.4f} (p-val: {metrics['p_value']:.4f})")
    print(f"  * Directional Hit Rate:             {metrics['hit_rate']:.2%}")
    print(f"  * Root Mean Squared Error (RMSE):    {metrics['rmse']:.6f}")
    print(f"  * Mean Absolute Error (MAE):         {metrics['mae']:.6f}")
    print(f"  * Training Duration:                 {metrics['train_time_sec']}s")
    print("========================================================\n")

    return model, metrics


def main():
    parser = argparse.ArgumentParser(description="QuantPulse Alpha Forecaster Training & Inference CLI")
    parser.add_argument("--symbol", default="BTC/USDT", help="Asset symbol (e.g. BTC/USDT)")
    parser.add_argument("--horizon", type=int, default=1, help="Forecast horizon in minutes (e.g. 1, 5, 15)")
    parser.add_argument("--train", action="store_true", help="Train and save the model")
    parser.add_argument("--bars", type=int, default=1500, help="Number of historical 1m bars to synthesize")
    args = parser.parse_args()

    if args.train:
        model, metrics = train_alpha_forecaster_pipeline(
            symbol=args.symbol,
            n_bars=args.bars,
            horizon=args.horizon,
        )
        model_path = os.path.join(DEFAULT_MODEL_DIR, f"alpha_{args.symbol.replace('/', '-')}_{args.horizon}m.joblib")
        model.save(model_path)
        print(f"[SAVED] Serialized alpha model to: {model_path}")


if __name__ == "__main__":
    main()
