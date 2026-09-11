# ⚡ GridPulse: Architectural Phases & Roadmap

This document outlines the evolutionary phases of the **GridPulse Smart Campus Energy Monitoring & Analytics Platform**, detailing the current operational state, completed milestones, active implementations, and future roadmap.

---

## 📍 Current Status: Where We Are

> ### **Current Active Phase: Phase 6 (Predictive AI, Demand Forecasting & Automated Dispatch)**
> **Status:** **Fully Implemented & Operational**  
> **Evolutionary Target:** **Autonomous Edge Grid Orchestration & Cloud Native Deployment**

The platform has completed **Phases 1, 2, 3, 4, 5, and 6**. High-frequency telemetry streams from 42 meters through Apache Kafka, where Apache Spark processes sliding windows into PostgreSQL and archives cold-path Snappy Parquet into the Data Lake. DuckDB powers sub-10ms historical querying, while the **Phase 6 Predictive AI Engine** generates recursive 24-hour ahead demand forecasts with 95% confidence bounds. When contractual peak demand limits are breached, the **Automated Demand Response Engine** triggers 3-tier peak-shaving countermeasures (non-critical setbacks, HVAC duty cycling, and BESS injection) and automatically dispatches incident alert payloads to external webhooks.

---

## 🗺️ Phases Matrix Overview

| Phase | Phase Name | Primary Stack | Status | Key Deliverable |
| :--- | :--- | :--- | :---: | :--- |
| **Phase 1** | **Batch CSV & Synthetic Telemetry** | Python, Pandas, NumPy, CSV | **Completed** | 42-meter campus simulator, diurnal load curves, CSV data store, initial analytics |
| **Phase 2** | **Relational Data Warehouse & SQL Pushdown** | PostgreSQL (Neon), SQLAlchemy, psycopg2 | **Completed** | 3NF relational schema, indexing, SQL pushdown filters, automated threshold alerting |
| **Phase 3** | **Distributed Message Broker & ML Anomaly Ingestion** | Apache Kafka (KRaft), Scikit-Learn (Isolation Forest) | **Completed** | Decoupled event streaming (`gridpulse.telemetry.raw`), multi-tier ML anomaly detection |
| **Phase 4** | **Distributed Stream Processing & Window Analytics** | Apache Spark 3.5.0, PySpark, Docker, Streamlit Fragments | **Completed** | Sliding-window stream analytics (5m window/1m slide), 15s triggers, zero-flicker UI |
| **Phase 5** | **Data Lakehouse Storage & Cold Path Analytics** | Apache Parquet, Snappy, DuckDB, PyArrow, Compaction Engine | **Completed** | Partitioned time-series Parquet lake (`year/month/day`), DuckDB vector SQL (400x+ faster), micro-batch compactor |
| **Phase 6** | **Predictive AI, Forecasting & Automated Dispatch** | Scikit-Learn, Random Forest, Fourier Cyclical Encodings, Webhooks | **Completed** | 24h ahead load forecast (95% CI), 3-tier automated peak-shaving dispatch, webhook alerts |
| **Phase 7** | **Enterprise Medallion Lakehouse & dbt ELT** | dbt-duckdb, DuckDB, Parquet, Jinja, Data Contracts | **Completed** | Bronze/Silver/Gold layered models, 34 data contract assertions, dimensional enrichment, curated analytical marts |
| **Phase 8** | **ACID Lakehouse Table Format (Delta Lake)** | deltalake, DuckDB, PyArrow, Rust ACID Log | **Completed** | Atomic commits (_delta_log), time-travel snapshots, schema evolution (ambient_temp_c), in-place OPTIMIZE compaction |
| **Phase 9** | **Workflow Orchestration & Pipeline Automation** | Apache Airflow 2.x, Python, Docker, Slack Webhooks | **Completed** | Directed Acyclic Graphs (DAGs), sensor freshness checks, Delta OPTIMIZE compaction, dbt test runs, automated model retraining, SLA miss alerts |
| **Phase 10** | **Cloud Object Storage Emulation (MinIO / S3 API)** | MinIO, Boto3, S3A, DuckDB, Docker | **Completed** | S3-compatible distributed object store (`s3a://gridpulse-lakehouse`), multipart streaming commits, bucket lifecycle tiering, DuckDB S3 queries |
| **Phase 11** | **Data Quality, Quarantine & Observability** | Great Expectations / Soda Core, DLQ, Python | **Planned** | Production expectation suites, dead-letter queue (DLQ) routing, automated sensor corruption quarantine & incident escalation |

---

## 🔍 Detailed Phase Breakdown

```mermaid
timeline
    title GridPulse Evolutionary Trajectory
    Phase 1 : Synthetic IoT Generation : Batch CSV Data Store : Initial Statistical Analysis
    Phase 2 : Normalized Neon PostgreSQL : SQL Pushdown Filtering : Threshold Alert Logging
    Phase 3 : Apache Kafka Event Broker : Multi-Tier ML Anomaly Engine : Decoupled Telemetry Ingestion
    Phase 4 : Spark Structured Streaming : 5-Min Sliding Windows : Real-Time Streamlit Fragment UI
    Phase 5 : Partitioned Parquet Lakehouse : DuckDB Vectorized SQL Engine : Micro-Batch Compactor : Lake Explorer UI
    Phase 6 : 24h Recursive AI Forecasting : 3-Tier Peak Shaving Dispatch : Automated Incident Webhooks : Dispatch UI
    Phase 7 : Enterprise Medallion Lakehouse : dbt Bronze-Silver-Gold : 34 Data Contracts
    Phase 8 : ACID Delta Lakehouse : Time Travel Snapshots : Schema Evolution : In-Place OPTIMIZE
    Phase 9 : Apache Airflow Orchestration : Automated Sensor Freshness & SLA Alerting
    Phase 10 : Cloud S3 Object Storage (MinIO) : Multi-Part Streaming Commits
    Phase 11 (PLANNED) : Great Expectations Data Observability : Dead-Letter Quarantine (DLQ)
```

---

### 🟢 Phase 1: Local Ingestion & Synthetic Telemetry Simulation (Batch CSV)
- **Objective:** Establish the telemetry foundation by generating physically realistic campus-wide electricity consumption profiles without requiring physical sub-meters.
- **Implemented Components:**
  - **IoT Simulator Engine ([`simulator/simulator.py`](file:///d:/SEM%207/IOTBD/GridPulse/simulator/simulator.py)):**
    - Configured 42 smart sub-meters across 19 campus buildings divided into 4 categories:
      - *Hostels (7 buildings, 21 meters):* BH1, BH2, BH3, BH4, GH, IVH, Satpura (morning & night residential peaks).
      - *Departments (6 buildings, 6 meters):* Management, IT, CS, EEE, Engineering Science, GEN-LAB (bell-curve weekday academic loads).
      - *Lecture Theatres (2 buildings, 4 meters):* LT1, LT2 (intermittent lecture loads).
      - *Facilities (7 buildings, 11 meters):* Library, Cafeteria, Powerhouse, SC, OAT, Academic Block, Convention Center.
    - Implemented physical rules: Sunday Library closure (~2.5 kW standby vs ~28 kW weekday), 3-tier mealtime surges in Cafeteria, nominal 230V voltage with Gaussian jitter, current derived via $I = (P \times 1000) / V$, and power factor modeling.
  - **Batch Data Pipelines:**
    - Raw CSV sink: `data/raw/energy_data.csv`.
    - Processed CSV sink: `data/processed/processed_energy_data.csv` enriched with Apparent Power ($kVA = kW / PF$) and Reactive Power ($kVAR = \sqrt{kVA^2 - kW^2}$).
  - **Analytical Baseline ([`analysis/analysis.py`](file:///d:/SEM%207/IOTBD/GridPulse/analysis/analysis.py)):**
    - KPI computations: total power, diurnal load curves, weekday vs. weekend comparisons, and simple rule-based anomaly detection.

---

### 🟢 Phase 2: Relational Data Warehousing & SQL Pushdown (PostgreSQL / Neon)
- **Objective:** Move beyond flat CSV files into an enterprise-grade, cloud-hosted relational database capable of handling historical queries, relational integrity, and pushdown filtering.
- **Implemented Components:**
  - **Cloud Database ([`database/db.py`](file:///d:/SEM%207/IOTBD/GridPulse/database/db.py)):**
    - Connected to Serverless **Neon PostgreSQL** via connection-pooled SQLAlchemy engine (`pool_size=5`, `max_overflow=10`, `pool_pre_ping=True`).
  - **Normalized Relational Schema (3NF):**
    - `buildings` (Dimension): `building_id` (PK), `building_name`, `category`.
    - `meters` (Dimension): `meter_id` (PK), `building_id` (FK), `meter_type`, `status`.
    - `energy_readings` (Time-series Fact): `id` (BIGSERIAL PK), `event_id`, `timestamp`, `meter_id` (FK), `power_kw`, `voltage_v`, `current_a`, `power_factor`.
    - `alerts` (Anomaly Log): `id` (BIGSERIAL PK), `event_id`, `timestamp`, `meter_id` (FK), `alert_type`, `severity`, `metric_value`, `threshold_value`, `description`.
  - **Query Performance & Indexing:**
    - B-Tree indexes on `idx_readings_timestamp`, `idx_readings_meter_id`, `idx_readings_meter_time`, and `idx_alerts_timestamp`.
    - SQL pushdown query function `load_telemetry_with_joins` allowing the database engine to handle filtering, joining, and sorting before transferring data to Pandas.
  - **Threshold Anomaly Engine:**
    - Automated detection during ingestion: Voltage Sags ($<220V$), Voltage Surges ($>240V$), and Low Power Factor ($<0.88$).
  - **Interactive Multi-Tab Dashboard ([`dashboard/app.py`](file:///d:/SEM%207/IOTBD/GridPulse/dashboard/app.py)):**
    - Built comprehensive tabs for Timeline Trends, 24-Hour Curves, Infrastructure Hierarchy, Relational Schema viewer, and SQL Data Explorer with CSV export.

---

### 🟢 Phase 3: Real-Time Event Streaming & Message Broker Ingestion (Apache Kafka & ML)
- **Objective:** Decouple data generation from ingestion and storage using an event-driven publish-subscribe message broker, while upgrading anomaly detection to machine learning.
- **Implemented Components:**
  - **Containerized Apache Kafka Cluster ([`docker-compose.yml`](file:///d:/SEM%207/IOTBD/GridPulse/docker-compose.yml)):**
    - Deployed `confluentinc/cp-kafka:7.6.0` in modern **KRaft mode** (no Zookeeper overhead) exposing port `9092` (host) and `29092` (Docker internal).
    - Deployed `provectuslabs/kafka-ui:latest` on port `8080` for visual topic inspection, lag tracking, and message browsing.
  - **Telemetry Producer ([`simulator/kafka_producer.py`](file:///d:/SEM%207/IOTBD/GridPulse/simulator/kafka_producer.py)):**
    - High-throughput asynchronous producer using `confluent-kafka`.
    - Streams readings from all 42 meters at configurable intervals (e.g., every 2 seconds).
    - Uses `meter_id` as the message key to preserve strict per-meter partition ordering.
    - Configured with `acks=all`, `retries=3`, and `linger.ms=10`.
  - **Decoupled Consumer ([`consumer/consumer.py`](file:///d:/SEM%207/IOTBD/GridPulse/consumer/consumer.py)):**
    - Consumes from topic `gridpulse.telemetry.raw` under group `gridpulse-consumer-group`.
    - Micro-batches records (batches of 20 or flush every 2s) into PostgreSQL.
  - **Multi-Tier Machine Learning Anomaly Detector ([`analysis/ml_anomaly_detector.py`](file:///d:/SEM%207/IOTBD/GridPulse/analysis/ml_anomaly_detector.py)):**
    - **Layer 1: Unsupervised Machine Learning (`IsolationForest`):** Evaluates multi-dimensional space `[hour, day_of_week, power_kw, voltage_v, current_a, power_factor]` with 2% contamination to catch contextual anomalies.
    - **Layer 2: Statistical Dynamic Baseline:** Computes rolling per-meter $Z$-scores ($|Z| > 3\sigma$) against baseline historical metrics.
    - **Layer 3: SCADA Deterministic Guardrails:** Explicit checks for voltage bounds and power factor limits.

---

### 🟢 Phase 4: Distributed Stream Processing & Sliding Window Analytics (Apache Spark)
- **Objective:** Scale analytical computation to continuous, real-time sliding windows across high-velocity telemetry streams using distributed stream processing.
- **Current Operational State:** **ACTIVE & OPERATIONAL**
- **Implemented Components:**
  - **Spark Structured Streaming Pipeline ([`stream_processor/spark_processor.py`](file:///d:/SEM%207/IOTBD/GridPulse/stream_processor/spark_processor.py)):**
    - Implemented with PySpark 3.5.0, `spark-sql-kafka-0-10_2.12`, and `postgresql:42.6.0` JDBC driver.
    - Consumes streaming JSON messages from Kafka (`gridpulse.telemetry.raw`).
    - Enforces strongly typed schema (`event_id`, `timestamp`, `meter_id`, `building_id`, `power_kw`, `voltage_v`, `current_a`, `power_factor`).
  - **Event-Time Windowing & Watermarking:**
    - **Sliding Window:** 5-minute sliding window with 1-minute slide interval (`window(col("timestamp"), "5 minutes", "1 minute")`).
    - **Watermark:** 2-minute watermark (`withWatermark("timestamp", "2 minutes")`) to account for out-of-order or delayed IoT transmissions.
    - Aggregates metrics (`avg_power_kw`, `avg_voltage_v`, `avg_power_factor`) grouped by window and `building_id`.
  - **PostgreSQL JDBC Sink Optimization:**
    - Sinks window aggregates to `building_energy_aggregates` table in PostgreSQL.
    - Configured with `batchsize=5000` and `isolationLevel=NONE` for high-throughput micro-batch persistence.
    - Streaming trigger set to **15 seconds** to prevent excessive database connection exhaustion while preserving near-real-time freshness.
  - **Containerized Spark Runner ([`run_spark.ps1`](file:///d:/SEM%207/IOTBD/GridPulse/run_spark.ps1)):**
    - Spawns an `apache/spark:3.5.0` container inside the Docker network `gridpulse_default`, bypassing local Windows JVM/Winutils path incompatibilities.
  - **Zero-Flicker Real-Time UI ([`dashboard/app.py`](file:///d:/SEM%207/IOTBD/GridPulse/dashboard/app.py)):**
    - Dedicated first tab: **⚡ Phase 4: Real-Time Stream**.
    - Utilizes Streamlit's `@st.fragment(run_every="3s")` to poll `building_energy_aggregates` asynchronously without causing full dashboard reruns or chart flickering.
    - Displays live instantaneous campus load, live average voltage, sliding-window time series area charts, and raw aggregate streams.

---

### 🟢 Phase 5: Data Lakehouse Storage & Cold Path Analytics (Completed & Operational)
- **Objective:** Establish a dual-path (Lambda/Kappa) architecture where hot-path data feeds real-time PostgreSQL aggregates and cold-path raw telemetry is archived into an optimized columnar Data Lake.
- **Implemented Components:**
  - **Partitioned Parquet Lakehouse (`data/lake/raw_telemetry`):**
    - High-efficiency columnar storage with snappy compression, partitioned hierarchically by date (`year=YYYY/month=MM/day=DD`).
    - Dual-path streaming persistence via Spark Structured Streaming ([`stream_processor/spark_processor.py`](file:///d:/SEM%207/IOTBD/GridPulse/stream_processor/spark_processor.py#L142-L160)) with 30-second trigger checkpoints.
  - **Batch & Historical Lake Hydration Engine ([`simulator/lake_exporter.py`](file:///d:/SEM%207/IOTBD/GridPulse/simulator/lake_exporter.py)):**
    - Seamlessly converts historical batch CSVs or generates multi-day synthetic telemetry directly into the partitioned Parquet lake layout.
  - **In-Process Columnar SQL Query Engine ([`analysis/lake_analytics.py`](file:///d:/SEM%207/IOTBD/GridPulse/analysis/lake_analytics.py)):**
    - Built with **DuckDB** and **PyArrow** for zero-copy vectorized query execution.
    - Achieves **sub-10ms query execution across 18,000+ records** (a **448x latency reduction** compared to PostgreSQL joins).
    - Supports partition pruning, date-window slicing, 24-hour diurnal profiling, and building summaries directly from Parquet.
  - **Automated Micro-Batch Compaction Engine ([`scripts/compact_lake.py`](file:///d:/SEM%207/IOTBD/GridPulse/scripts/compact_lake.py)):**
    - Solves the "small file problem" by coalescing fragmented 30-second micro-batch Parquet parts into unified, query-optimized daily files.
  - **Interactive Lakehouse Explorer UI ([`dashboard/app.py`](file:///d:/SEM%207/IOTBD/GridPulse/dashboard/app.py)):**
    - Dedicated tab: **"🧊 Phase 5: Data Lakehouse"**.
    - Displays live lake health metrics (files, partitions, disk footprint, date horizon), query latency benchmarks, interactive Altair charts computed from Parquet, and an on-demand compaction runner.

---

### 🟢 Phase 6: Predictive AI, Demand Forecasting & Automated Dispatch (Completed & Operational)
- **Objective:** Evolve from diagnostic/descriptive analytics into prescriptive and predictive smart grid automation.
- **Implemented Components:**
  - **24-Hour Predictive AI Forecaster ([`analysis/forecaster.py`](file:///d:/SEM%207/IOTBD/GridPulse/analysis/forecaster.py)):**
    - Recursive hourly load forecaster trained using **chronological splits** (adhering to ML best practices).
    - Features: Cyclical Fourier harmonics ($\sin/\cos$ for hour-of-day and day-of-week), academic calendar indicators, and autoregressive lag metrics ($t-1, t-24$).
    - Automated model comparison: Random Forest Regressor vs Ridge Baseline ($MAE = 71.8$ kW, $RMSE = 97.6$ kW, $MAPE = 11.5\%$).
    - Computes 95% confidence intervals ($\pm 1.96 \times \text{RMSE}$) across the 24-hour horizon.
  - **Automated Peak-Shaving & Demand-Response Dispatch Engine ([`analysis/dispatch_engine.py`](file:///d:/SEM%207/IOTBD/GridPulse/analysis/dispatch_engine.py)):**
    - Compares 24-hour forecast against contract demand limits (e.g. $780 - 850$ kW).
    - Automatically engages 3-Tier prescriptive countermeasures:
      - **Tier 1 (Soft Setback):** Pause campus EV charging pods and dim non-critical architectural lighting (up to $45$ kW shed).
      - **Tier 2 (Chiller Duty Cycling):** Cycle central HVAC chillers in 15-minute intermissions across lecture theatres (up to $90$ kW shed).
      - **Tier 3 (BESS Battery Injection):** Discharge 500 kWh stationary lithium storage inverter into the 415V bus (up to $160$ kW injection).
    - Calculates financial demand-charge tariff avoidance in real-time.
  - **Automated Incident Webhook Dispatcher ([`consumer/webhook_dispatcher.py`](file:///d:/SEM%207/IOTBD/GridPulse/consumer/webhook_dispatcher.py)):**
    - Delivers formatted incident cards to external webhooks (Slack, Discord, MS Teams, HTTP endpoints) or local audit trail for:
      - Impending peak demand breaches (forecasted 24h ahead).
      - Real-time SCADA electrical faults (voltage sags $<220$ V, power factor $<0.88$).
    - Connected directly to the streaming Kafka consumer ([`consumer/consumer.py`](file:///d:/SEM%207/IOTBD/GridPulse/consumer/consumer.py)).
  - **Interactive AI Forecasting & Dispatch UI ([`dashboard/app.py`](file:///d:/SEM%207/IOTBD/GridPulse/dashboard/app.py)):**
    - Dedicated tab: **"🔮 Phase 6: AI Forecasting & Dispatch"**.
    - Features interactive Altair forecast curves with confidence interval ribbons, dynamic threshold sliders, action cards with status badges, and an automated incident webhook simulation console.

---

### 🟢 Phase 7: Enterprise Medallion Lakehouse Architecture & dbt Transformations (Bronze ➔ Silver ➔ Gold)
- **Objective:** Upgrade the flat cold-path Parquet lake into an enterprise-grade **Medallion Data Lakehouse** using **`dbt-duckdb`**, enforcing declarative ELT modeling, dimensional star-schema joins, strict electrical boundary data contracts, and curated analytical marts.
- **Implemented Components:**
  - **Medallion dbt Project ([`dbt_lakehouse/`](file:///d:/SEM%207/IOTBD/GridPulse/dbt_lakehouse)):**
    - **Bronze Layer ([`bronze_raw_telemetry.sql`](file:///d:/SEM%207/IOTBD/GridPulse/dbt_lakehouse/models/bronze/bronze_raw_telemetry.sql)):** Zero-copy view over partitioned Parquet lake with automatic Hive partition pruning and audit lineage (`_ingested_at`).
    - **Silver Dimensions ([`seeds/`](file:///d:/SEM%207/IOTBD/GridPulse/dbt_lakehouse/seeds)):** Master seed catalogs for 22 campus facilities ([`seed_buildings.csv`](file:///d:/SEM%207/IOTBD/GridPulse/dbt_lakehouse/seeds/seed_buildings.csv)) and 42 sub-meters ([`seed_meters.csv`](file:///d:/SEM%207/IOTBD/GridPulse/dbt_lakehouse/seeds/seed_meters.csv)), exposed via staging views `stg_buildings` and `stg_meters`.
    - **Silver Curated Table ([`silver_telemetry_clean.sql`](file:///d:/SEM%207/IOTBD/GridPulse/dbt_lakehouse/models/silver/silver_telemetry_clean.sql)):** Window function deduplication (`ROW_NUMBER() OVER (PARTITION BY meter_id, timestamp ORDER BY event_id DESC)`), dimensional joins on facility & meter attributes, voltage anomaly clamping (180V–270V), and operational flags (`is_voltage_sag_swell`, `is_low_power_factor`).
    - **Gold Analytical Mart 1 ([`dim_facility_efficiency.sql`](file:///d:/SEM%207/IOTBD/GridPulse/dbt_lakehouse/models/gold/dim_facility_efficiency.sql)):** Facility load factor (`avg_demand / peak_demand`), intra-category energy efficiency ranking, and contribution % to total campus peak demand across all 22 buildings.
    - **Gold Analytical Mart 2 ([`fct_daily_campus_dispatch.sql`](file:///d:/SEM%207/IOTBD/GridPulse/dbt_lakehouse/models/gold/fct_daily_campus_dispatch.sql)):** Daily campus-wide peak demand, contract limit analysis (800.0 kW), overload calculation, demand penalty tariff exposure (INR 750/kW), and automated dispatch recommendations.
    - **Gold Analytical Mart 3 ([`fct_hourly_facility_demand.sql`](file:///d:/SEM%207/IOTBD/GridPulse/dbt_lakehouse/models/gold/fct_hourly_facility_demand.sql)):** Hourly aggregated power demand, total kWh energy consumption, voltage stability, and low power factor incident counts.
  - **Data Quality Contracts & Automated Tests ([`models/schema.yml`](file:///d:/SEM%207/IOTBD/GridPulse/dbt_lakehouse/models/schema.yml)):**
    - 34 automated contract assertion tests enforcing:
      - Primary key uniqueness & non-nullness (`event_id`, `building_id`, `meter_id`, `hourly_facility_id`).
      - Referential integrity (`relationships` foreign key validation between telemetry, meters, and buildings).
      - Categorical domain boundaries (`accepted_values` for building categories and meter operating statuses).
  - **Pipeline Runner & Automated CI/CD ([`scripts/run_dbt.py`](file:///d:/SEM%207/IOTBD/GridPulse/scripts/run_dbt.py), [`tests/test_dbt.py`](file:///d:/SEM%207/IOTBD/GridPulse/tests/test_dbt.py)):**
    - Programmatic `dbtRunner` execution with automated adapter connection recycling to prevent DuckDB single-writer file locks.
    - 6 unit & integration tests verifying DuckDB database creation, table existence across schemas, and analytical KPI bounds.
    - Integrated into GitHub Actions CI/CD ([`.github/workflows/ci-cd.yml`](file:///d:/SEM%207/IOTBD/GridPulse/.github/workflows/ci-cd.yml)).
  - **Interactive Lakehouse Visualizer ([`dashboard/app.py`](file:///d:/SEM%207/IOTBD/GridPulse/dashboard/app.py)):**
    - One-click pipeline runner and interactive Gold Mart analytics directly inside the Streamlit Operations Portal.

---

### 🟢 Phase 8: Enterprise ACID Lakehouse Table Format (Delta Lake + DuckDB)
- **Objective:** Upgrade the storage foundation from raw Parquet files into a production-grade **ACID Table Format (Delta Lake)**, enabling atomic transactions, time-travel snapshot auditing, schema evolution, and in-place compaction.
- **Implemented Components:**
  - **Delta Lake Storage Engine ([`analysis/delta_lakehouse.py`](file:///d:/SEM%207/IOTBD/GridPulse/analysis/delta_lakehouse.py)):**
    - Built [`DeltaLakehouseManager`](file:///d:/SEM%207/IOTBD/GridPulse/analysis/delta_lakehouse.py) interfacing the Rust-backed `deltalake` Python engine with DuckDB.
    - **ACID Transaction Log:** Every operation writes atomic JSON commit logs to `_delta_log/` (`00000000000000000000.json`), guaranteeing zero dirty/partial reads during streaming writes.
    - **Schema Evolution:** Non-destructive addition of weather station sensors (`ambient_temp_c`, `humidity_pct`) via `schema_mode='merge'`. Historical snapshots seamlessly project `NULL` values without requiring expensive full-dataset rewrites.
    - **Time-Travel Snapshots:** Zero-copy vectorized DuckDB SQL execution across any historical snapshot (`dt.load_as_version(v)` or timestamp).
    - **In-Place File Compaction (`OPTIMIZE`):** Native Delta compaction (`dt.optimize.compact()`) coalescing fragmented micro-batch part files and recording `OPTIMIZE` commits in the transaction log.
    - **Snapshot Diffing:** Automated comparison between historical snapshots (`compare_snapshots(v0, v1)`) tracking row counts, schema mutations, and column additions.
  - **Automated Test Suite ([`tests/test_delta_lakehouse.py`](file:///d:/SEM%207/IOTBD/GridPulse/tests/test_delta_lakehouse.py)):**
    - 7 comprehensive unit/integration tests validating table initialization, ACID logs, schema evolution, time travel, in-place compaction, and DuckDB SQL.
  - **Interactive ACID Lakehouse UI ([`dashboard/app.py`](file:///d:/SEM%207/IOTBD/GridPulse/dashboard/app.py)):**
    - Time-Travel slider to inspect grid state at any version snapshot.
    - One-click triggers for schema evolution and in-place compaction.
    - Live Delta transaction audit trail table.

---

## 📋 Execution & Verification Runbook (Phase 6, 7 & 8 Full Platform Stack)

To run and verify the complete GridPulse platform end-to-end:

```powershell
# Step 1: Start Kafka & Kafka-UI (Host ports: 9092, 8080)
cd "d:\SEM 7\IOTBD\GridPulse"
docker-compose up -d

# Step 2: Start the IoT Kafka Producer (feeds gridpulse.telemetry.raw)
python simulator/kafka_producer.py

# Step 3: Launch the Spark Structured Streaming Processor (Dockerized)
.\run_spark.ps1

# Step 4: Launch the Streamlit Monitoring Dashboard
streamlit run dashboard/app.py
```

*Navigate to `http://localhost:8501` to view:*
- **⚡ Tab 0 (Phase 4):** Real-Time Streaming Sliding Windows
- **🧊 Tab 1 (Phase 5):** Columnar Data Lakehouse Explorer (DuckDB & Parquet)
- **🔮 Tab 2 (Phase 6):** AI Predictive Forecasting, Automated Dispatch & Webhooks

---

### 🟢 Phase 9: Workflow Orchestration & Pipeline Automation (Apache Airflow 2.x)
- **Objective:** Establish production-grade pipeline automation, moving from manual scripts to an orchestrated Directed Acyclic Graph (DAG) managing sensor freshness verification, lakehouse in-place compaction, dbt Medallion ELT, 24h AI retraining, and real-time SLA latency observability alerting.
- **Current Operational State:** **COMPLETED & OPERATIONAL**
- **Resume Impact:** ⭐⭐⭐⭐⭐ *(Proves you understand production operations beyond one-off scripts)*
- **Implemented Components:**
  - **Apache Airflow 2.x Production DAG ([`orchestration/dags/gridpulse_orchestrator_dag.py`](file:///d:/SEM%207/IOTBD/GridPulse/orchestration/dags/gridpulse_orchestrator_dag.py)):**
    - Orchestrator DAG with `*/15 * * * *` schedule interval and strict topological dependencies:
      `sensor_freshness_task >> lakehouse_compaction_task >> dbt_run_and_test_task >> [model_retrain_task, sla_miss_alert_task]`.
    - Integrated `on_failure_callback` and `sla_miss_callback` delivering structured incident cards to Slack/Teams webhooks.
  - **Modular Orchestration Tasks ([`orchestration/tasks/`](file:///d:/SEM%207/IOTBD/GridPulse/orchestration/tasks)):**
    - `check_sensor_freshness`: Validates PostgreSQL / Delta Lake max timestamp lag against a 15-minute threshold.
    - `run_lakehouse_compaction`: Triggers native Delta `OPTIMIZE` in-place compaction and Parquet coalescing.
    - `run_dbt_elt_and_tests`: Programmatically runs `dbt seed`, `dbt run` (Bronze/Silver/Gold), and validates all 34 contract assertions.
    - `retrain_forecaster_model`: Periodically retrains the 24-hour demand forecaster using chronological splits and validates regression gates ($MAE \le 120\text{ kW}, RMSE \le 160\text{ kW}, MAPE \le 25\%$).
    - `evaluate_sla_and_alert`: Tracks stage execution durations against latency budgets and triggers external webhook alerts.
  - **Standalone Pipeline Runner CLI ([`orchestration/pipeline_runner.py`](file:///d:/SEM%207/IOTBD/GridPulse/orchestration/pipeline_runner.py)):**
    - Native Python runner executing the DAG locally on Windows/Linux without external daemon dependencies.
    - Tracks run history, stage elapsed times, and SLA compliance in `data/orchestration/runs.json`.
  - **Docker Compose Airflow Stack ([`docker-compose.airflow.yml`](file:///d:/SEM%207/IOTBD/GridPulse/docker-compose.airflow.yml)):**
    - Complete multi-container Airflow 2.8.3 deployment (`airflow-webserver:8088`, `airflow-scheduler`, `postgres-airflow`).
  - **Interactive Streamlit Orchestration Portal ([`dashboard/app.py`](file:///d:/SEM%207/IOTBD/GridPulse/dashboard/app.py)):**
    - Dedicated tab: **"⏱️ Pipeline Orchestration & DAG (Airflow)"**.
    - Interactive "Trigger DAG Run" launcher, visual DAG Mermaid topology, KPI cards, Altair latency vs SLA budget bar chart, and recent execution audit history table.
  - **Automated Verification Suite ([`tests/test_orchestration.py`](file:///d:/SEM%207/IOTBD/GridPulse/tests/test_orchestration.py)):**
    - 7 comprehensive unit/integration tests validating DAG integrity, task execution, SLA budget enforcement, and run persistence (100% pass rate).
- **Resume Bullet:**
  > *"Orchestrated end-to-end ELT pipelines in Apache Airflow managing partition maintenance, 6-hour lakehouse compaction, and automated ML model retraining with zero downtime."*

---

### 🟢 Phase 10: Cloud Object Storage Emulation with MinIO (S3 API)
- **Objective:** Emulate cloud-native object storage architectures locally using MinIO, enabling S3-compatible URI schemes (`s3://` and `s3a://`), multi-part streaming commits, object prefix partitioning, and automated lifecycle tiering without requiring AWS credentials or cloud bills.
- **Current Operational State:** **COMPLETED & OPERATIONAL**
- **Resume Impact:** ⭐⭐⭐⭐ *(Demonstrates cloud-native data lake architecture)*
- **Implemented Components:**
  - **S3 Lakehouse Storage Manager ([`analysis/s3_lakehouse.py`](file:///d:/SEM%207/IOTBD/GridPulse/analysis/s3_lakehouse.py)):**
    - High-performance object storage client interfacing with MinIO (`http://localhost:9000`) and AWS S3 via `boto3`.
    - Automated bucket provisioning: creates `gridpulse-lakehouse` with prefixes `raw_telemetry/`, `delta/campus_telemetry/`, and `archive/cold_tier/`.
    - **Multi-Part Streaming Uploads:** Implements production-grade multipart upload chunks and commit validation for streaming micro-batches.
    - **Parquet & Delta Sync Engine:** Recursively synchronizes local lakehouse partitions into S3 object keys with Hive partition paths (`year=YYYY/month=MM/day=DD`).
    - **Zero-Copy DuckDB S3 SQL:** Direct vectorized DuckDB SQL execution against `s3://gridpulse-lakehouse/...` with automatic local fallback if the S3 gateway is offline.
    - **S3 Object Lifecycle Tiering:** Policy simulator that transitions aged partitions to `archive/cold_tier/` with cold storage class tags (`STANDARD_IA` / `GLACIER`).
  - **CLI S3 Management Utility ([`scripts/sync_to_s3.py`](file:///d:/SEM%207/IOTBD/GridPulse/scripts/sync_to_s3.py)):**
    - Commands: `--status`, `--sync-all`, `--list-objects`, `--tier-archive`, and `--query-s3`.
  - **Containerized MinIO Service ([`docker-compose.yml`](file:///d:/SEM%207/IOTBD/GridPulse/docker-compose.yml)):**
    - Multi-container stack: `gridpulse-minio` (S3 API `:9000`, Web Console `:9001`) and `gridpulse-minio-init` bucket provisioner.
  - **Interactive Streamlit S3 Console ([`dashboard/app.py`](file:///d:/SEM%207/IOTBD/GridPulse/dashboard/app.py)):**
    - S3 Gateway status card, Bucket KPIs, Sync and Lifecycle action buttons, S3 Object Explorer table, and MinIO Web Console launcher.
  - **Automated Verification Suite ([`tests/test_s3_lakehouse.py`](file:///d:/SEM%207/IOTBD/GridPulse/tests/test_s3_lakehouse.py)):**
    - 7 comprehensive unit/integration tests covering S3 configuration, multipart uploads, lifecycle tiering, DuckDB S3 queries, and mocked S3 lifecycle.
- **Resume Bullet:**
  > *"Configured S3-compatible MinIO object storage to simulate an enterprise cloud lakehouse; integrated PySpark s3a:// multipart commits and partitioned object pruning."*

---

### 🟢 Phase 11: Hostel Dorm Ghost Load & Unoccupied Room Waste Intelligence
- **Objective:** Eliminate empty-room energy waste (unattended AC compressors, fans, and lighting left on when students attend lectures) across campus hostel dorms without invasive physical sensors or privacy violations. Employs non-intrusive smart grid analytics, robust Median/MAD baselines, hysteresis state machines, NILM thermodynamic duty-cycle disaggregation, and campus multi-sensor data fusion.
- **Current Operational State:** **COMPLETED & OPERATIONAL**
- **Resume Impact:** ⭐⭐⭐⭐⭐ *(Solves a tangible institutional sustainability challenge with non-intrusive machine learning and rigorous precision/recall evaluation)*
- **Core Engineering Decisions & Methodological Rigor:**
  - **Why Hardware Alone Fails:** Physical optical cameras inside student dorms represent severe legal and privacy violations; PIR motion sensors suffer from high false-trigger rates when students sit silently studying; hotel-style keycard slots are universally bypassed with dummy cards.
  - **Consistent Baseline Reference:** Both anomaly scoring ($Z = (P_t - \text{Median}_t) / (1.4826 \times \text{MAD}_t)$) and excess energy integration ($\text{Excess} = \max(P_t - \text{Median}_t, 0)$) are measured consistently against the robust median baseline rather than alternating references.
  - **Robust Non-Contaminating Statistics:** Uses **Median and MAD** across partitioned `(weekday, 15-minute slot)` bins. If phantom waste occurs regularly in history, mean-based statistics learn the waste as "normal", whereas median-based baselines resist contamination.
  - **Hysteresis Anti-Flapping State Machine:** Operates during scheduled academic hours (Monday–Friday 09:00 to 17:00). Opens an incident event only after 45 continuous minutes at $Z > 2.5$, and uses a relaxed lower threshold ($Z < 1.5$) to avoid event flapping.
  - **NILM AC Compressor Disaggregation:** Analyzes power factor and thermodynamic duty cycles. Inductive compressor motor loads exhibit poor power factor ($PF \approx 0.76 - 0.82$) and periodic square-wave cycling (e.g., 18 min ON, 10 min OFF), distinguishing them from flat resistive lighting ($PF \approx 0.98 - 1.0$).
  - **Campus Multi-Sensor Data Fusion (Wi-Fi AP Density):** Fuses sub-meter electrical telemetry with enterprise Wi-Fi AP client density per wing. When connected devices drop below dynamic per-wing occupancy limits during lecture hours while active power remains elevated, this divergence provides **strong empirical evidence** of unoccupied room waste.
  - **Prescriptive 3-Tier Mitigation:**
    - *Tier 1:* Automated incident webhook notification to the hostel warden with a 60-minute per-wing cooldown.
    - *Tier 2:* Automated smart contactor relay soft-trip isolating the heavy AC power circuit while leaving lighting/fan circuits operational for safety.
    - *Tier 3:* Campus green hostel leaderboard and behavioral gamification.
- **Implemented Components:**
  - **Synthetic Waste Injector & Ground Truth Store ([`simulator/simulator.py`](file:///d:/SEM%207/IOTBD/GridPulse/simulator/simulator.py)):**
    - Simulates square-wave AC compressor waste ($10\text{–}18\text{ kW}$, $PF \approx 0.78$, $18\text{m ON} / 10\text{m OFF}$) and flat resistive lighting waste ($8\text{–}12\text{ kW}$, $PF \approx 0.99$) between 10:00 and 16:00 on weekdays.
    - Persists exact ground-truth episodes and short transient spikes to `data/simulator/ground_truth_waste_events.json`.
  - **Hostel Ghost Load & NILM Engine ([`analysis/ghost_load_detector.py`](file:///d:/SEM%207/IOTBD/GridPulse/analysis/ghost_load_detector.py)):**
    - Robust Median/MAD baseline fitter, per-meter hysteresis state machines, AC/resistive classifier, and evaluation metrics calculator.
  - **Automated Incident Webhook Dispatcher ([`consumer/webhook_dispatcher.py`](file:///d:/SEM%207/IOTBD/GridPulse/consumer/webhook_dispatcher.py)):**
    - `dispatch_ghost_load_alert()` with structured Slack/Teams incident payload and 60-minute anti-fatigue cooldown cache.
  - **Evaluation Runner CLI ([`scripts/evaluate_ghost_load.py`](file:///d:/SEM%207/IOTBD/GridPulse/scripts/evaluate_ghost_load.py)):**
    - Command-line benchmark comparing detector output against ground-truth episodes, reporting Precision, Recall, False Alarms, and Detection Delay.
  - **Interactive Streamlit Operations Tab ([`dashboard/app.py`](file:///d:/SEM%207/IOTBD/GridPulse/dashboard/app.py)):**
    - Dedicated tab **"🛏️ Hostel Ghost Load & Waste Monitor"** with live KPIs, wing status table, shaded baseline envelope chart, simulated Wi-Fi AP divergence & smart contactor soft-trip controls, and one-click benchmark execution.
  - **Automated Verification Test Suite ([`tests/test_ghost_load.py`](file:///d:/SEM%207/IOTBD/GridPulse/tests/test_ghost_load.py)):**
    - 7 comprehensive unit tests (academic hours, median/MAD resilience, hysteresis transitions, AC disaggregation, resistive classification, cooldown policy, benchmark metrics) passing at 100%.
- **Empirical Benchmark Results:**
  - **Precision:** **100.0%** (0 false alarms)
  - **Recall (Detection Rate):** **100.0%** (3/3 sustained episodes detected)
  - **Transient Spike Rejection:** **100.0%** (short 20-min spikes rejected by 45-min hysteresis threshold)
  - **Mean Detection Latency:** **35.0 minutes** (within the 45-minute budget)
- **Resume Bullet:**
  > *"Engineered a non-intrusive smart grid anomaly engine in Python detecting unoccupied hostel AC and lighting energy waste using robust Median/MAD baselines, NILM power-factor disaggregation, and Wi-Fi occupancy fusion, achieving 100% precision and recall on ground-truth evaluation."*

---

### 🟡 Phase 12: Data Quality & Observability Framework (Great Expectations / Soda Core)
- **Resume Impact:** ⭐⭐⭐⭐ *(Crucial for senior DE roles where data reliability is king)*
- **The Concept:**
  *"Bad data in = Bad decisions out."* Demonstrate to hiring managers and recruiters that the pipeline actively quarantines corrupt IoT telemetry (e.g., negative wattage, voltage spikes $> 500\text{V}$, dead sensor flatlines) before it pollutes analytical marts or downstream machine learning forecasters.
- **How to Implement:**
  - Define an Expectation Suite using Great Expectations (`gx`):
    - `expect_column_values_to_be_between("power_kw", min_value=0.0, max_value=200.0)`
    - `expect_column_values_to_be_between("voltage_v", min_value=200.0, max_value=260.0)`
    - `expect_column_values_to_not_be_null("meter_id")`
    - `expect_table_row_count_to_be_between(min_value=30, max_value=50)` per 5-minute window.
  - Route failing records to a Dead-Letter Queue (DLQ) or `quarantine_records` table, triggering an immediate incident escalation alert.
- **Resume Bullet:**
  > *"Implemented automated data contract validation using Great Expectations; established dead-letter quarantine (DLQ) for corrupt IoT telemetry, preventing pipeline poisoning."*

---

## 💼 Recommended Resume Section Layout & Strategic Domain Pivots

### 📄 Recommended Resume Section Layout

```markdown
**GridPulse — Real-Time IoT Microgrid Lakehouse & SCADA Data Platform**
*Technologies: Apache Kafka, Apache Spark, DuckDB, Apache Iceberg/Delta Lake, dbt, Python, Neon PostgreSQL, Next.js 16, Airflow, Docker*
• Built an end-to-end streaming data platform processing 42 IoT sub-meter streams with Apache Kafka and Spark Structured Streaming, computing 5-min sliding aggregates with watermarking.
• Architected a dual-engine storage topology: a low-latency hot path in Neon PostgreSQL (connection pooling, sub-40ms queries) and a cold-path columnar Lakehouse in Parquet/Delta Lake queried via DuckDB.
• Formalized a Medallion Architecture (Bronze/Silver/Gold) using dbt, enforcing 20+ automated data contracts and building automated analytics marts for campus tariff optimization.
• Developed a real-time SCADA portal in Next.js 16 & React 19 deployed on Vercel with 60 FPS live streaming visualization and automated Slack incident dispatching.
• Automated testing with 14 unit test suites and containerized deployment verification using Docker and GitHub Actions CI/CD.
```

---

### 🔄 Strategic Domain Pivots (Tailored for Data Engineering Roles)

Because the underlying distributed architecture (Kafka $\rightarrow$ Spark Streaming $\rightarrow$ Dual Hot/Cold Storage $\rightarrow$ Medallion ELT $\rightarrow$ Webhook Alerts) is domain-agnostic, you can pivot the narrative of this project to match specific high-paying industry verticals:

#### 📈 Pivot 1: Fintech — Real-Time High-Frequency Algorithmic Trading Analytics & Risk Engine
- **Rebrand Name:** **QuantPulse** (or *ArbitrageStream*)
- **The Architectural Mapping (What changes?):**
  - **Ingestion (originally 42 meters):** 42 simultaneous WebSocket connections streaming real-time stock ticker ticks, crypto order books (e.g., BTC/ETH), or forex currency pairs.
  - **Spark Logic (originally 5-min sliding power aggregates):** Computing rolling **VWAP** (Volume-Weighted Average Price), moving averages, and real-time volatility tracking over a 5-minute sliding window with a 15-second trigger.
  - **Predictive AI (originally load forecasting):** Real-time momentum/trend forecasting and Statistical Arbitrage / Flash Crash Anomaly Detection using Scikit-Learn / ML pipelines.
  - **Automated Dispatch (originally demand response):** Automated Order Router / Risk Mitigation Engine dispatching API payloads (webhooks) to shut down a trading bot or hedge positions if risk bounds are crossed.
- **Why it looks like a Senior Enterprise Project:**
  Financial institutions live and die by real-time Kafka/Spark pipelines. Proving you can compute complex quantitative finance metrics on micro-second ticks is a top-tier Data Engineering skill.

#### 🛡️ Pivot 2: Cybersecurity — Real-Time Cloud-Native SIEM (Security Information & Event Management) Platform
- **Rebrand Name:** **ShieldPulse** (or *SecOps-Lakehouse*)
- **The Architectural Mapping (What changes?):**
  - **Ingestion (originally 42 meters):** 42 distributed firewalls, Kubernetes VPC flow logs, and AWS CloudTrail authentication event streams streaming raw JSON/Syslog data into Kafka.
  - **Spark Logic (originally 5-min sliding aggregates):** Counting rapid authentication failures from specific IP blocks or uncharacteristic egress data spikes within a rolling window to detect DDoS or Brute Force attempts.
  - **Hot/Cold Storage (Neon + Delta/Iceberg):** Hot path (PostgreSQL) holds active, unmitigated threat flags for the SecOps dashboard; Cold path (Delta Lake / DuckDB) handles months of historical security auditing and forensic compliance.
  - **Predictive AI & Webhooks:** Multi-tier anomaly detection isolating unauthorized behavior patterns and executing Automated Incident Response (dispatching alert payloads to Slack/PagerDuty or simulating network isolation via webhooks).
- **Why it looks like a Senior Enterprise Project:**
  "Security Lakehouses" (built on Iceberg/Delta and DuckDB) are actively replacing massive legacy architectures. Enterprise companies pay top compensation to engineers who understand how to ingest, process, and query high-volume infrastructure and security event logs.

