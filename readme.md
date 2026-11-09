# ⚡ QuantPulse: Institutional Quantitative Trading Analytics & Medallion Order Book Lakehouse

[![Python 3.11](https://img.shields.io/badge/Python-3.11-blue.svg)](https://www.python.org/)
[![Next.js 16](https://img.shields.io/badge/Next.js-16.3-black.svg)](https://nextjs.org/)
[![Delta Lake](https://img.shields.io/badge/Delta_Lake-1.6-00ADD8.svg)](https://delta.io/)
[![DuckDB](https://img.shields.io/badge/DuckDB-1.5-FFF000.svg)](https://duckdb.org/)
[![dbt-duckdb](https://img.shields.io/badge/dbt-1.8-FF694B.svg)](https://getdbt.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**QuantPulse** is an institutional-grade, ultra-low-latency quantitative trading analytics platform, Medallion order book lakehouse, and automated risk execution engine.

Ingesting high-frequency Level-2 order books and tick streams across **42 multi-asset instruments** (Crypto, Tech Equities, ETFs, Forex, Commodities), QuantPulse computes microsecond microstructure signals, persists point-in-time data in an **ACID Delta Lakehouse** with **zero lookahead bias**, and enforces **3-tier automated risk circuit breakers** before orders can ever reach an exchange.

---

## 🏛️ Tri-Mode Operating Architecture

QuantPulse operates in three distinct, mutually reinforcing modes:

```
                       ┌────────────────────────────────────────────────────────┐
                       │                     DATA INGESTION                     │
                       └────────────────────────────────────────────────────────┘
                                                    │
                ┌───────────────────────────────────┼───────────────────────────────────┐
                ▼                                   ▼                                   ▼
        [1. LIVE MODE]                     [2. REPLAY MODE]                   [3. CRISIS SIM MODE]
       Binance WebSocket / REST           Historical Tick Replay            Synthetic Stress Engine
      Real Exchange Order Book            Parquet / CSV Lakehouse           Toxic Dump / Flash Crash
                │                                   │                                   │
                └───────────────────────────────────┼───────────────────────────────────┘
                                                    ▼
                                    ┌───────────────────────────────┐
                                    │      STREAMING PROCESSOR      │
                                    │   VPIN / OFI / VWAP / Depth   │
                                    └───────────────┬───────────────┘
                                                    ▼
                                    ┌───────────────────────────────┐
                                    │     RISK DECISION ARBITER     │
                                    │   Multi-Signal Consensus &    │
                                    │      3-Tier Safeguards        │
                                    └───────────────┬───────────────┘
                                                    ▼
                                    ┌───────────────────────────────┐
                                    │      NEXT.JS 16 TERMINAL      │
                                    │  [LIVE] [REPLAY] [CRISIS SIM] │
                                    └───────────────────────────────┘
```

1. **🟢 LIVE MODE**: Ingests real market data from Binance Public REST & WebSocket APIs (20-level order book depth, real-time trades, 1m candles) with sub-millisecond VWAP, Order Flow Imbalance (OFI), and basis-point spread computation.
2. **🔵 REPLAY MODE**: Deterministic historical tick tape replay engine with interactive playback controls (play/pause, step forward/backward, speed multipliers `1x` to `60x`, timeline scrubber).
3. **🟠 CRISIS SIM MODE**: Institutional stress-testing sandbox that injects adverse selection regimes (`toxic_dump`, `liquidity_vacuum`, `flash_crash`, `cointegration_breakdown`) to verify that the Decision Arbiter vetoes toxic orders and activates Tier-3 circuit breakers before capital can be lost.

---

## 🗺️ Master 14-Phase Evolutionary Roadmap

| Phase | Phase Name | Primary Technology Stack | Status | Key Deliverables & Architectural Output |
| :--- | :--- | :--- | :---: | :--- |
| **Phase 1** | **Multi-Asset Synthetic Simulator & Tick Store** | Python, NumPy, PyArrow, Snappy Parquet | **✅ Complete** | 42-asset stochastic jump-diffusion simulator, L2 order book generator, historical tick replay. |
| **Phase 2** | **Relational Market Store & Financial Schemas** | PostgreSQL (Neon), SQLAlchemy, BRIN | **✅ Complete** | 3NF financial schema (`instruments`, `trades_fact`, `orderbook_snapshots`, `risk_events`), time-bucketed OHLCV. |
| **Phase 3** | **Real-Time Market Ingestion & Live Exchange Gateways** | Kafka (KRaft), Binance/Coinbase WS, Alpaca | **✅ Complete** | Event streaming (`market.trades.raw`, `market.orderbook.l2`), live crypto connectors, symbol partition keys. |
| **Phase 4** | **Distributed Quantitative Stream Processing** | Apache Spark 3.5.0, PySpark, Streaming SQL | **✅ Complete** | Sliding-window financial stream processing: Rolling VWAP, Order Flow Imbalance (OFI), Micro-price, Realized Volatility, CVD. |
| **Phase 5** | **High-Frequency Columnar Lakehouse & DuckDB Engine** | DuckDB, Apache Parquet, Snappy, Compactor | **✅ Complete** | Partitioned tick lake (`asset_class/symbol/year/month/day`), sub-5ms vectorized DuckDB SQL, micro-batch compactor. |
| **Phase 6** | **Quantitative Predictive AI, Alpha Forecaster & Stat-Arb** | LightGBM, Scikit-Learn, Kalman Filters | **✅ Complete** | Multi-horizon directional return forecaster, GARCH volatility modeling, Kalman Filter cointegrated pairs trading stat-arb. |
| **Phase 7** | **Enterprise Medallion Lakehouse & dbt Financial Transforms** | dbt-duckdb, DuckDB, Jinja, Data Contracts | **✅ Complete** | Bronze/Silver/Gold ELT models, 103 financial data assertions (Bid < Ask, volume non-negativity), Alpha & Liquidity Marts. |
| **Phase 8** | **ACID Market Lakehouse Table Format (Delta Lake)** | Delta Lake (`deltalake`), DuckDB, PyArrow | **✅ Complete** | Atomic commits (`_delta_log`), point-in-time reproducible backtesting (zero lookahead bias), Z-Ordering on `(symbol, timestamp)`. |
| **Phase 9** | **Production Workflow Orchestration & Alpha DAGs** | Apache Airflow 2.x, Python, Docker | **Planned** | Market-close DAG: tick freshness audits, Delta OPTIMIZE, dbt factor builds, walk-forward model retrain. |
| **Phase 10** | **Petabyte Cloud Object Storage Emulation (MinIO/S3)** | MinIO, AWS S3 API, Boto3, DuckDB S3 | **Planned** | Distributed tick lakehouse (`s3://quantpulse-lakehouse`), multipart streaming commits, automated lifecycle tiering. |
| **Phase 11** | **Market Surveillance, Toxic Flow & Flash Crash Engine** | VPIN (Volume Toxicity), Kyle's Lambda | **Planned** | Institutional surveillance detecting spoofing, layering, toxic flow (VPIN), and flash crashes with 100% test recall. |
| **Phase 12** | **Algorithmic Execution & 3-Tier Pre/Post-Trade Risk Engine** | Alpaca REST/WS, Binance API, IBKR Client | **Planned** | Algorithmic execution (TWAP/VWAP/Implementation Shortfall), 3-tier risk safeguards (sizing throttle, auto-hedge, kill switch). |
| **Phase 13** | **Institutional Next.js & TradingView Operations Terminal** | Next.js 16, React 19, Tailwind CSS | **In Progress** | 60 FPS Depth-of-Market (DOM) ladder, canvas order book, interactive charts, OLED pitch black design system. |
| **Phase 14** | **Data Observability, Contract DLQ & Compliance Framework** | Great Expectations, Kafka DLQ | **Planned** | Pre-ingestion validation suites, dead-letter quarantine for corrupted ticks, SEC Rule 611 / MiFID II best-execution audit logs. |

---

## 🔬 Core System Modules

### 1. Medallion Lakehouse (`dbt-duckdb`)
* **Bronze Layer**: Zero-copy view (`bronze_raw_trades`) reading multi-partition Parquet ticks with audit lineage (`_ingested_at`, `_source_file`, `_file_row_number`).
* **Silver Layer**: Cleaned, deduplicated trade stream (`silver_trades_clean`) with Lee-Ready trade aggressor classification, spread bps, and 1-minute standardized OHLCV candles (`silver_ohlcv_1m`) with Cumulative Volume Delta (CVD).
* **Gold Layer**:
  - `fct_daily_market_liquidity`: Kyle's $\lambda$ (price impact) and Amihud Illiquidity ratio.
  - `fct_alpha_factor_performance`: Annualized Sharpe, Sortino, Continuous Max Drawdown, and Calmar ratios.
  - `dim_cross_sectional_momentum`: Dense ranks, percentiles, and Long/Short quintile factors across the 42-asset universe.
* **103 Automated Financial Data Contracts**: Enforces Arbitrage Non-Crossing ($Ask > Bid$), Candle Monotonicity, and non-negativity across all mart entities.

### 2. ACID Delta Lakehouse & Zero Lookahead Backtester
* **Transaction Log (`_delta_log/*.json`)**: Atomic serializable commits eliminate dirty reads during streaming ingestion.
* **Space-Filling Z-Ordering on `(symbol, timestamp)`**: Coalesces micro-batch files and organizes data layout along space-filling curves, pruning up to 90% of file scans for symbol time-slice queries.
* **Non-Destructive Schema Evolution (`schema_mode="merge"`)**: Seamlessly adds institutional derivatives fields (`funding_rate`, `open_interest`, `iv_surface`, `taker_buy_volume`).
* **Zero Lookahead Invariant**: Running a strategy on historical snapshot $V_0$ produces bit-for-bit identical PnL and Sharpe ($10^{-6}$ epsilon) regardless of future market movements.

---

## 🧪 Verification & Empirical Benchmarks

* **Full Quant Test Suite**: 44/44 unit and integration tests passing in 18.7s across all components.
* **Phase 8 ACID Lakehouse Suite**: 13/13 tests passing in 1.99s.
* **dbt Lakehouse Pipeline**: 14 models, 3 seeds, 103 financial data tests passing in 26.3s (100% pass rate).
* **Vectorized Analytical Latency**: Sub-10ms mean query latency over 42 symbols via DuckDB.
* **Next.js Production Build**: Compiles cleanly with zero errors across all API routes.

---

## 🚀 Quickstart & Reproduction

### 1. Python Environment Setup
```bash
python -m venv .venv
source .venv/bin/activate  # Or on Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Run the ACID Delta Lakehouse Pipeline
```bash
python scripts/run_delta_lakehouse.py --all
```

### 3. Run the dbt Medallion Lakehouse Pipeline
```bash
python scripts/run_dbt.py --all
```

### 4. Execute the Full Quant Test Suite
```bash
python -m unittest discover -s tests -p "test_quant_*.py" -v
```

### 5. Launch the Next.js Institutional Trading Terminal
```bash
cd frontend
npm install
npm run dev
```
Open [http://localhost:3000](http://localhost:3000) to view the OLED Pitch Black Trading Terminal.

---

## 📜 License

MIT License. Designed and engineered for institutional quantitative finance and market microstructure research.
