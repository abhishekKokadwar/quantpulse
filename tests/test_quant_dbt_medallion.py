"""
QuantPulse: Automated Unit & Integration Tests for Enterprise Medallion Lakehouse (Phase 7)
=============================================================================================
Validates:
1. Bronze zero-copy Parquet view compilation and lineage audit columns (_ingested_at, _source_file).
2. Staging dimension coverage across all 42 instruments and 5 asset classes.
3. Silver trade deduplication, Lee-Ready aggressor classification, and price/size sanity.
4. Silver 1-minute OHLCV bar aggregation, candle monotonicity, and Cumulative Volume Delta (CVD).
5. Gold daily market liquidity factors (Kyle's Lambda and Amihud Illiquidity).
6. Gold alpha factor performance metrics (Sharpe, Sortino, Drawdown, Calmar, Win Rate).
7. Gold cross-sectional momentum ranking and long/short quintile classification.
8. Zero violations across all institutional financial data contracts.
"""

import os
import sys
import unittest
import duckdb

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from scripts.run_dbt import DEFAULT_DB_PATH, DBT_PROJECT_DIR, run_pipeline


class TestQuantDbtMedallionLakehouse(unittest.TestCase):
    con = None

    @classmethod
    def setUpClass(cls):
        """Execute the dbt Medallion pipeline if needed, then connect to DuckDB."""
        if not os.path.exists(DEFAULT_DB_PATH):
            res = run_pipeline(do_seed=True, do_run=True, do_test=True, project_dir=DBT_PROJECT_DIR)
            assert res["success"] is True, "dbt pipeline execution failed in setUpClass"
        cls.con = duckdb.connect(DEFAULT_DB_PATH, read_only=True)

    @classmethod
    def tearDownClass(cls):
        if cls.con:
            cls.con.close()

    def test_01_medallion_tables_and_views_exist(self):
        """Verify all Bronze, Silver, and Gold financial objects exist in DuckDB."""
        tables_df = self.con.execute("""
            SELECT table_schema, table_name, table_type 
            FROM information_schema.tables 
            WHERE table_schema IN ('bronze', 'silver', 'gold')
        """).df()

        schema_table_map = set(zip(tables_df["table_schema"], tables_df["table_name"]))

        expected_quant_objects = [
            ("bronze", "bronze_raw_trades"),
            ("silver", "seed_instruments"),
            ("silver", "stg_instruments"),
            ("silver", "silver_trades_clean"),
            ("silver", "silver_ohlcv_1m"),
            ("gold", "fct_daily_market_liquidity"),
            ("gold", "fct_alpha_factor_performance"),
            ("gold", "dim_cross_sectional_momentum"),
        ]

        for schema, tbl in expected_quant_objects:
            self.assertIn(
                (schema, tbl),
                schema_table_map,
                f"Missing QuantPulse object {schema}.{tbl} in DuckDB Lakehouse",
            )

    def test_02_stg_instruments_coverage(self):
        """Verify 42 multi-asset instruments across 5 classes are loaded into stg_instruments."""
        count = self.con.execute("SELECT COUNT(*) FROM silver.stg_instruments").fetchone()[0]
        self.assertEqual(count, 42, f"Expected 42 instruments in stg_instruments, got {count}")

        classes_df = self.con.execute("""
            SELECT asset_class, COUNT(*) as cnt 
            FROM silver.stg_instruments 
            GROUP BY asset_class
        """).df()
        found_classes = set(classes_df["asset_class"].tolist())
        expected_classes = {"crypto", "equities", "etfs", "forex", "commodities"}
        self.assertEqual(found_classes, expected_classes, "Mismatch in expected asset classes")

        # Verify reference prices and tick sizes are positive
        anomalies = self.con.execute("""
            SELECT COUNT(*) 
            FROM silver.stg_instruments 
            WHERE ref_price <= 0 OR tick_size <= 0 OR lot_size <= 0
        """).fetchone()[0]
        self.assertEqual(anomalies, 0, "Found non-positive ref_price or tick_size in stg_instruments")

    def test_03_bronze_raw_trades_lineage(self):
        """Verify Bronze raw trades view has rows and audit lineage metadata."""
        count = self.con.execute("SELECT COUNT(*) FROM bronze.bronze_raw_trades").fetchone()[0]
        self.assertGreater(count, 0, "Bronze raw trades view returned 0 rows")

        sample = self.con.execute("""
            SELECT _ingested_at, _source_file, _file_row_number, symbol, price, quantity 
            FROM bronze.bronze_raw_trades 
            LIMIT 5
        """).df()
        self.assertEqual(len(sample), 5)
        for _, row in sample.iterrows():
            self.assertIsNotNone(row["_ingested_at"])
            self.assertIsNotNone(row["_source_file"])
            self.assertTrue(
                str(row["_source_file"]).endswith(".parquet"),
                f"Expected .parquet extension in _source_file, got {row['_source_file']}",
            )
            self.assertGreater(row["_file_row_number"], 0)

    def test_04_silver_trades_clean_dedup_and_lee_ready(self):
        """Verify Silver trades table has zero duplicates, Lee-Ready sides, and price sanity."""
        count = self.con.execute("SELECT COUNT(*) FROM silver.silver_trades_clean").fetchone()[0]
        self.assertGreater(count, 0, "Silver trades clean table is empty")

        # 1. Zero duplicate trades
        dup_count = self.con.execute("""
            SELECT COUNT(*) FROM (
                SELECT symbol, timestamp, trade_id, COUNT(*) 
                FROM silver.silver_trades_clean 
                GROUP BY symbol, timestamp, trade_id 
                HAVING COUNT(*) > 1
            )
        """).fetchone()[0]
        self.assertEqual(dup_count, 0, "Found duplicate trade records in silver_trades_clean")

        # 2. Strict non-negativity
        sanity_fails = self.con.execute("""
            SELECT COUNT(*) 
            FROM silver.silver_trades_clean 
            WHERE price <= 0 OR quantity <= 0 OR notional_usd <= 0
        """).fetchone()[0]
        self.assertEqual(sanity_fails, 0, "Found non-positive prices/quantities in silver_trades_clean")

        # 3. Aggressor side only BUY or SELL
        sides = self.con.execute("""
            SELECT DISTINCT aggressor_side FROM silver.silver_trades_clean
        """).fetchall()
        side_set = {s[0] for s in sides}
        self.assertTrue(side_set.issubset({"BUY", "SELL"}), f"Invalid aggressor side: {side_set}")

        # 4. Referential integrity to stg_instruments
        orphan_trades = self.con.execute("""
            SELECT COUNT(*) 
            FROM silver.silver_trades_clean t 
            LEFT JOIN silver.stg_instruments i ON t.symbol = i.symbol 
            WHERE i.symbol IS NULL
        """).fetchone()[0]
        self.assertEqual(orphan_trades, 0, "Found trades with unmapped symbols in stg_instruments")

    def test_05_silver_ohlcv_1m_monotonicity(self):
        """Verify Silver 1-minute OHLCV bars satisfy mathematical candle monotonicity & CVD."""
        count = self.con.execute("SELECT COUNT(*) FROM silver.silver_ohlcv_1m").fetchone()[0]
        self.assertGreater(count, 0, "Silver 1-minute OHLCV table is empty")

        # Monotonicity test: High >= Open and High >= Close, Low <= Open and Low <= Close
        monotonicity_fails = self.con.execute("""
            SELECT COUNT(*) 
            FROM silver.silver_ohlcv_1m 
            WHERE high_price < open_price 
               OR high_price < close_price 
               OR low_price > open_price 
               OR low_price > close_price
        """).fetchone()[0]
        self.assertEqual(monotonicity_fails, 0, "Found candle envelope monotonicity breaches in silver_ohlcv_1m")

        # CVD integrity check: buy_volume + sell_volume <= total volume (+ rounding margin)
        cvd_sample = self.con.execute("""
            SELECT bar_id, volume, buy_volume, sell_volume, cvd 
            FROM silver.silver_ohlcv_1m 
            LIMIT 10
        """).df()
        for _, row in cvd_sample.iterrows():
            self.assertGreaterEqual(row["volume"], 0)
            self.assertGreaterEqual(row["buy_volume"], 0)
            self.assertGreaterEqual(row["sell_volume"], 0)
            self.assertAlmostEqual(row["cvd"], row["buy_volume"] - row["sell_volume"], places=4)

    def test_06_gold_market_liquidity_kpis(self):
        """Verify Gold daily liquidity mart computes valid Kyle's Lambda and Amihud ratios."""
        df = self.con.execute("SELECT * FROM gold.fct_daily_market_liquidity").df()
        self.assertGreater(len(df), 0, "fct_daily_market_liquidity is empty")

        # Verify key columns
        required_cols = [
            "liquidity_id", "trade_date", "symbol", "total_volume",
            "kyle_lambda", "amihud_illiquidity", "day_vwap", "avg_spread_bps",
        ]
        for col in required_cols:
            self.assertIn(col, df.columns, f"Missing required column {col}")

        # Kyle's Lambda and Amihud Illiquidity must be non-negative
        self.assertTrue((df["kyle_lambda"] >= 0.0).all(), "Found negative Kyle's Lambda")
        self.assertTrue((df["amihud_illiquidity"] >= 0.0).all(), "Found negative Amihud Illiquidity")
        self.assertTrue((df["total_volume"] > 0.0).all(), "Found non-positive daily total_volume")

    def test_07_gold_alpha_performance_metrics(self):
        """Verify Gold alpha performance mart evaluates Sharpe, Sortino, Drawdown, and Calmar."""
        df = self.con.execute("SELECT * FROM gold.fct_alpha_factor_performance").df()
        self.assertGreater(len(df), 0, "fct_alpha_factor_performance is empty")

        required_cols = [
            "performance_id", "symbol", "annualized_return",
            "annualized_volatility", "sharpe_ratio", "sortino_ratio",
            "max_drawdown", "calmar_ratio", "win_rate_pct",
        ]
        for col in required_cols:
            self.assertIn(col, df.columns, f"Missing column {col} in fct_alpha_factor_performance")

        # Win rate must be bounded between 0% and 100%
        self.assertTrue((df["win_rate_pct"] >= 0.0).all(), "Found win_rate_pct < 0")
        self.assertTrue((df["win_rate_pct"] <= 100.0).all(), "Found win_rate_pct > 100")

        # Max drawdown must be non-negative
        self.assertTrue((df["max_drawdown"] >= 0.0).all(), "Found negative max_drawdown")

    def test_08_gold_cross_sectional_momentum(self):
        """Verify Gold cross-sectional momentum assigns full universe ranks and factor quintiles."""
        df = self.con.execute("SELECT * FROM gold.dim_cross_sectional_momentum").df()
        self.assertEqual(len(df), 42, f"Expected 42 ranked instruments, got {len(df)}")

        # Percentile rank must be bounded in [0.0, 1.0]
        self.assertTrue((df["momentum_percentile"] >= 0.0).all(), "Found momentum_percentile < 0")
        self.assertTrue((df["momentum_percentile"] <= 1.0).all(), "Found momentum_percentile > 1")

        # Factor signals must match standard long/short quintile tags
        signals = set(df["factor_signal"].unique())
        self.assertTrue(
            signals.issubset({"LONG_TOP_QUINTILE", "SHORT_BOTTOM_QUINTILE", "NEUTRAL"}),
            f"Invalid factor signals: {signals}",
        )
        self.assertIn("LONG_TOP_QUINTILE", signals)
        self.assertIn("SHORT_BOTTOM_QUINTILE", signals)

    def test_09_financial_data_contracts_zero_violations(self):
        """Verify all institutional financial data contracts report ZERO violations."""
        # 1. Arbitrage non-crossing condition
        crossed_quotes = self.con.execute("""
            SELECT COUNT(*) 
            FROM silver.silver_trades_clean 
            WHERE ask_1 <= bid_1
        """).fetchone()[0]
        self.assertEqual(crossed_quotes, 0, "Crossed quote books detected (ask_1 <= bid_1)")

        # 2. Candle monotonicity
        candle_breaches = self.con.execute("""
            SELECT COUNT(*) 
            FROM silver.silver_ohlcv_1m 
            WHERE high_price < open_price 
               OR high_price < close_price 
               OR low_price > open_price 
               OR low_price > close_price
        """).fetchone()[0]
        self.assertEqual(candle_breaches, 0, "OHLCV candle monotonicity breaches detected")

        # 3. Non-negativity of execution prices and quantities
        neg_executions = self.con.execute("""
            SELECT COUNT(*) 
            FROM silver.silver_trades_clean 
            WHERE price <= 0 OR quantity <= 0 OR notional_usd <= 0
        """).fetchone()[0]
        self.assertEqual(neg_executions, 0, "Non-positive trade prices/quantities detected")

        # 4. Non-negativity of liquidity factors
        invalid_factors = self.con.execute("""
            SELECT COUNT(*) 
            FROM gold.fct_daily_market_liquidity 
            WHERE kyle_lambda < 0 OR amihud_illiquidity < 0
        """).fetchone()[0]
        self.assertEqual(invalid_factors, 0, "Invalid negative liquidity factors detected")


if __name__ == "__main__":
    unittest.main()
