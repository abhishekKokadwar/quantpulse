"""
QuantPulse: Phase 6 Quantitative Machine Learning & Stat-Arb Test Suite
========================================================================
Comprehensive validation adhering to ml-best-practices:
1. Microstructure feature engineering math (Parkinson, Garman-Klass, RSI, Cyclical)
2. Strict featurization ordering & lookahead leakage prevention
3. Purged & Embargoed chronological cross-validation boundaries
4. Multi-horizon Alpha Forecaster training, Rank IC & directional hit rate
5. Engle-Granger Two-Step Cointegration Test on synthetic stationary & random walk pairs
6. Dynamic Kalman Filter state-space hedge ratio convergence
7. Statistical Arbitrage signal state machine transitions & circuit breaker stops
"""

from datetime import datetime, timedelta, timezone
import math
import os
import shutil
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd
from scipy import stats

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from analysis.alpha_forecaster import (
    AlphaForecasterModel,
    PurgedTimeSeriesSplitter,
    calculate_bollinger_percent_b,
    calculate_garman_klass_volatility,
    calculate_macd,
    calculate_parkinson_volatility,
    calculate_rsi,
    engineer_alpha_features,
)
from analysis.stat_arb_engine import (
    KalmanHedgeRatioTracker,
    StatArbSignalGenerator,
    StatArbState,
    engle_granger_cointegration_test,
)


class TestFeatureEngineering(unittest.TestCase):
    """Verifies mathematical correctness of technical and microstructure features."""

    def setUp(self):
        np.random.seed(42)
        n = 100
        base_price = 100.0
        returns = np.random.normal(0, 0.01, n)
        closes = base_price * np.exp(np.cumsum(returns))
        highs = closes * (1.0 + np.abs(np.random.normal(0, 0.005, n)))
        lows = closes * (1.0 - np.abs(np.random.normal(0, 0.005, n)))
        opens = (closes + np.roll(closes, 1)) / 2.0
        opens[0] = base_price

        self.df = pd.DataFrame({
            "timestamp": pd.date_range("2026-09-12 09:30:00", periods=n, freq="1min"),
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": np.random.uniform(10, 100, n),
        })

    def test_parkinson_volatility(self):
        park = calculate_parkinson_volatility(self.df["high"], self.df["low"], window=14)
        self.assertEqual(len(park), len(self.df))
        self.assertTrue((park >= 0.0).all())
        # Non-zero after warmup
        self.assertGreater(park.iloc[20], 0.0)

    def test_garman_klass_volatility(self):
        gk = calculate_garman_klass_volatility(
            self.df["open"], self.df["high"], self.df["low"], self.df["close"], window=14
        )
        self.assertEqual(len(gk), len(self.df))
        self.assertTrue((gk >= 0.0).all())
        self.assertGreater(gk.iloc[20], 0.0)

    def test_rsi_bounds(self):
        rsi = calculate_rsi(self.df["close"], window=14)
        self.assertEqual(len(rsi), len(self.df))
        # Strictly bounded [0.0, 100.0]
        self.assertTrue((rsi >= 0.0).all())
        self.assertTrue((rsi <= 100.0).all())

    def test_cyclical_session_harmonics(self):
        df_feat, feats, targets = engineer_alpha_features(self.df, horizons=[1, 5])
        self.assertIn("sin_time_of_day", feats)
        self.assertIn("cos_time_of_day", feats)
        # Verify trigonometric Pythagorean identity: sin^2 + cos^2 = 1.0
        identity = (df_feat["sin_time_of_day"] ** 2 + df_feat["cos_time_of_day"] ** 2)
        np.testing.assert_allclose(identity, 1.0, atol=1e-5)


class TestPurgedAndEmbargoedSplits(unittest.TestCase):
    """Verifies absence of lookahead leakage and correctness of chronological splits."""

    def test_purged_embargoed_splitter_boundaries(self):
        n = 1000
        splitter = PurgedTimeSeriesSplitter(train_ratio=0.70, val_ratio=0.15, purge_bars=10, embargo_bars=10)
        train_idx, val_idx, test_idx = splitter.split(n)

        # 1. Chronological order: train < val < test
        self.assertLess(np.max(train_idx), np.min(val_idx))
        self.assertLess(np.max(val_idx), np.min(test_idx))

        # 2. Purge & Embargo buffer gaps
        gap_train_val = np.min(val_idx) - np.max(train_idx)
        self.assertGreaterEqual(gap_train_val, 10 + 10)  # purge + embargo

        gap_val_test = np.min(test_idx) - np.max(val_idx)
        self.assertGreaterEqual(gap_val_test, 10 + 10)

        # 3. No index overlap
        all_indices = np.concatenate([train_idx, val_idx, test_idx])
        self.assertEqual(len(all_indices), len(np.unique(all_indices)))

    def test_strict_featurization_ordering(self):
        """Verifies StandardScaler is fit strictly on X_train only."""
        np.random.seed(42)
        X_train = pd.DataFrame({"f1": [10.0, 20.0, 30.0], "f2": [100.0, 200.0, 300.0]})
        y_train = pd.Series([0.01, -0.02, 0.03])
        X_test = pd.DataFrame({"f1": [500.0, 600.0], "f2": [5000.0, 6000.0]})

        model = AlphaForecasterModel()
        model.fit(X_train, y_train)

        # Scaler mean must reflect X_train ONLY
        expected_mean = np.array([20.0, 200.0])
        np.testing.assert_allclose(model.scaler.mean_, expected_mean, atol=1e-5)


class TestAlphaForecaster(unittest.TestCase):
    """Verifies model training, inference, metrics calculation, and serialization."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        np.random.seed(42)
        n = 500
        # Synthetic autoregressive features
        self.X = pd.DataFrame({
            "f1": np.random.normal(0, 1, n),
            "f2": np.random.normal(0, 1, n),
            "f3": np.random.normal(0, 1, n),
        })
        # Target with genuine predictive signal
        self.y = 0.05 * self.X["f1"] - 0.03 * self.X["f2"] + np.random.normal(0, 0.01, n)

        self.X_train, self.y_train = self.X.iloc[:350], self.y.iloc[:350]
        self.X_val, self.y_val = self.X.iloc[350:425], self.y.iloc[350:425]
        self.X_test, self.y_test = self.X.iloc[425:], self.y.iloc[425:]

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_fit_predict_and_metrics(self):
        model = AlphaForecasterModel(horizon_label="1m")
        model.fit(self.X_train, self.y_train, self.X_val, self.y_val)

        preds = model.predict(self.X_test)
        self.assertEqual(len(preds), len(self.X_test))

        metrics = model.evaluate(self.X_test, self.y_test)
        self.assertIn("rank_ic", metrics)
        self.assertIn("hit_rate", metrics)
        self.assertIn("rmse", metrics)
        self.assertIn("mae", metrics)

        # Positive Rank IC on data with actual linear signal
        self.assertGreater(metrics["rank_ic"], 0.20)
        self.assertGreater(metrics["hit_rate"], 0.55)

    def test_model_serialization(self):
        model = AlphaForecasterModel(horizon_label="5m")
        model.fit(self.X_train, self.y_train)

        save_path = os.path.join(self.temp_dir, "test_alpha_model.joblib")
        model.save(save_path)
        self.assertTrue(os.path.exists(save_path))

        loaded_model = AlphaForecasterModel.load(save_path)
        preds_original = model.predict(self.X_test)
        preds_loaded = loaded_model.predict(self.X_test)
        np.testing.assert_allclose(preds_original, preds_loaded, atol=1e-6)


class TestStatisticalArbitrageEngine(unittest.TestCase):
    """Verifies cointegration testing, Kalman hedge ratio adaptation, and trading signals."""

    def test_engle_granger_cointegration_detection(self):
        np.random.seed(42)
        n = 400
        # Cointegrated pair: P_B is random walk, P_A is 1.8 * P_B + stationary noise
        rw_b = np.cumsum(np.random.normal(0, 0.01, n)) + 5.0
        price_b = np.exp(rw_b)
        noise = np.random.normal(0, 0.005, n)
        price_a = np.exp(1.8 * rw_b + noise)

        res_cointeg = engle_granger_cointegration_test(price_a, price_b)
        self.assertTrue(res_cointeg["is_cointegrated"])
        self.assertLess(res_cointeg["t_stat"], res_cointeg["critical_values"]["5%"])
        self.assertAlmostEqual(res_cointeg["hedge_ratio"], 1.8, places=2)

        # Independent random walks: must FAIL cointegration test
        rw_independent = np.cumsum(np.random.normal(0, 0.01, n)) + 3.0
        price_c = np.exp(rw_independent)
        res_independent = engle_granger_cointegration_test(price_b, price_c)
        self.assertFalse(res_independent["is_cointegrated"])

    def test_kalman_filter_hedge_ratio_convergence(self):
        np.random.seed(42)
        n = 500
        # True hedge ratio = 1.75
        x = np.cumsum(np.random.normal(0, 0.02, n)) + 4.0
        y = 1.75 * x + np.random.normal(0, 0.01, n)
        prices_b = np.exp(x)
        prices_a = np.exp(y)

        # Start with bad initial beta guess of 0.50
        kalman = KalmanHedgeRatioTracker(delta=1e-4, initial_beta=0.50)
        alphas, betas, spreads = kalman.batch_filter(prices_a, prices_b)

        # Final adapted beta must converge close to 1.75
        final_beta = betas[-1]
        self.assertAlmostEqual(final_beta, 1.75, delta=0.08)

    def test_stat_arb_signal_state_transitions(self):
        sig_gen = StatArbSignalGenerator(pair_label="BTC-ETH", z_entry=2.0, z_exit=0.5, z_circuit_breaker=3.5)

        # Seed with 30 zero spreads to establish baseline mean=0, std=1
        for i in range(30):
            val = float(np.random.normal(0, 1.0))
            sig_gen.process_tick(f"2026-09-12 10:{i:02d}:00", val, 1.5)

        # Force large negative spread (Z < -2.0) -> ENTER_LONG_SPREAD
        sig_entry = sig_gen.process_tick("2026-09-12 10:31:00", -3.5, 1.5)
        self.assertEqual(sig_entry.action, "ENTER_LONG_SPREAD")
        self.assertEqual(sig_entry.state, StatArbState.LONG_SPREAD)

        # Mean reversion (|Z| < 0.5) -> FLATTEN_PROFIT
        sig_exit = sig_gen.process_tick("2026-09-12 10:32:00", 0.0, 1.5)
        self.assertEqual(sig_exit.action, "FLATTEN_PROFIT")

        # Force extreme runaway spread (Z > 4.5) -> CIRCUIT_BREAKER_STOP
        sig_entry2 = sig_gen.process_tick("2026-09-12 10:33:00", 2.8, 1.5)
        self.assertEqual(sig_entry2.action, "ENTER_SHORT_SPREAD")
        sig_cb = sig_gen.process_tick("2026-09-12 10:34:00", 6.0, 1.5)
        self.assertEqual(sig_cb.action, "EMERGENCY_FLATTEN")
        self.assertEqual(sig_cb.state, StatArbState.CIRCUIT_BREAKER_STOP)


if __name__ == "__main__":
    unittest.main()
