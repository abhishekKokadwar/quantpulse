'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import {
  Zap,
  Activity,
  ShieldAlert,
  Clock,
  Database,
  ArrowLeft,
  Server,
  Cpu,
  Layers,
  CheckCircle2,
  AlertTriangle,
  Flame,
  Radio,
  BarChart3,
  Sliders,
  ExternalLink,
  BedDouble,
  BookOpen,
  Info,
  Sparkles,
  Search,
  Code2,
  Workflow,
  ChevronRight,
  GitBranch,
  Terminal,
  FileText,
  Wifi,
} from 'lucide-react';
import { Tooltip } from '@/components/Tooltip';
import { FeatureExplainerModal } from '@/components/FeatureExplainerModal';

interface ArchitectureNode {
  id: string;
  name: string;
  phase: string;
  category: 'ingestion' | 'processing' | 'storage' | 'intelligence' | 'presentation';
  tech: string;
  latencySla: string;
  codePath: string;
  description: string;
  inputs: string[];
  outputs: string[];
  keyDecisions: string[];
}

export default function HowItWorksPage() {
  const [selectedNodeId, setSelectedNodeId] = useState<string>('ghost-load');
  const [activeTab, setActiveTab] = useState<'pipeline' | 'ghostload' | 'lakehouse' | 'dispatch' | 'math' | 'qa'>('ghostload');
  const [isExplainerOpen, setIsExplainerOpen] = useState<boolean>(false);

  const architectureNodes: ArchitectureNode[] = [
    {
      id: 'edge-meters',
      name: 'IoT Edge Smart Sub-Meters',
      phase: 'Phase 1',
      category: 'ingestion',
      tech: 'Python Simulator / Modbus RS-485 / MQTT',
      latencySla: '1000 ms (1 Hz)',
      codePath: 'simulator/simulator.py',
      description: '42 smart energy meters distributed across 22 campus facilities (hostels, lecture halls, computer labs, library, dining). Continuously samples active power (kW), phase voltage (V), current (A), and power factor.',
      inputs: ['Building electrical loads', 'Ambient weather curves', 'Academic schedule timetable'],
      outputs: ['Structured JSON electrical telemetry payload', 'Synthetic waste injection toggle'],
      keyDecisions: [
        'Organized into 4 major campus categories with realistic diurnal load signatures.',
        'Hierarchical sub-meter distribution (e.g. 3 sub-meters per hostel representing wings/floors).',
      ],
    },
    {
      id: 'kafka-buffer',
      name: 'Apache Kafka Message Broker',
      phase: 'Phase 2',
      category: 'ingestion',
      tech: 'Kafka 3.7 / Docker Compose',
      latencySla: '< 15 ms',
      codePath: 'kafka/docker-compose.yml',
      description: 'High-throughput, persistent distributed message buffer decoupling telemetry ingestion from stream processing engines. Partitioned by building category to guarantee in-order delivery.',
      inputs: ['Raw IoT meter telemetry streams'],
      outputs: ['Partitioned topic: campus.telemetry.raw'],
      keyDecisions: [
        'Decouples high-frequency producers from database writes to absorb telemetry bursts.',
        'Enables multiple downstream consumers (Spark, Lakehouse sink, anomaly alerts) simultaneously.',
      ],
    },
    {
      id: 'spark-streaming',
      name: 'Apache Spark Structured Streaming',
      phase: 'Phase 4',
      category: 'processing',
      tech: 'PySpark 3.5 / 1-Min Tumbling Windows',
      latencySla: '< 2500 ms',
      codePath: 'stream_processor/spark_processor.py',
      description: 'Distributed stream processing engine aggregating high-frequency sensor readings into 1-minute tumbling windows. Calculates rolling average kW, min/max voltage sags, and active building counts.',
      inputs: ['Kafka topic: campus.telemetry.raw'],
      outputs: ['Rolling aggregated windows pushed to PostgreSQL and Parquet cold path'],
      keyDecisions: [
        'Watermarking set to 2 minutes to handle late-arriving IoT network packets.',
        'Zero data loss with write-ahead logs (WAL) and checkpoint directories.',
      ],
    },
    {
      id: 'hot-postgres',
      name: 'Neon Cloud PostgreSQL (Hot Path)',
      phase: 'Phase 3',
      category: 'storage',
      tech: 'PostgreSQL 16 / Neon Serverless',
      latencySla: '< 50 ms query latency',
      codePath: 'database/schema.sql',
      description: 'Serves real-time SCADA queries and live dashboard feeds. Stores latest meter readings, aggregated sliding windows, building metadata, and active incident alarms.',
      inputs: ['Spark stream micro-batches', 'Direct edge telemetry fallback'],
      outputs: ['Real-time Next.js SCADA portal endpoints', 'Active alert state table'],
      keyDecisions: [
        'B-tree indexes on (meter_id, timestamp) and (building_id, timestamp) for sub-50ms lookups.',
        'SSL enabled with connection pooling for web tier resilience.',
      ],
    },
    {
      id: 'cold-lakehouse',
      name: 'Medallion Data Lakehouse & dbt',
      phase: 'Phase 5 & 6',
      category: 'storage',
      tech: 'Parquet / DuckDB / dbt-duckdb',
      latencySla: 'Sub-second analytical queries',
      codePath: 'dbt_lakehouse/ & analysis/lake_analytics.py',
      description: 'Columnar analytical storage following the Medallion pattern: Bronze (raw Parquet partitioned by year/month/day), Silver (cleaned & deduplicated), Gold (daily dispatch & facility efficiency marts).',
      inputs: ['Raw streaming telemetry micro-batches'],
      outputs: ['Aggregated Gold marts: dim_facility_efficiency, fct_daily_campus_dispatch'],
      keyDecisions: [
        '34 dbt automated contract assertions enforce schema integrity and zero nulls.',
        'DuckDB enables zero-copy vectorized SQL directly on Parquet files without spinning up cloud clusters.',
      ],
    },
    {
      id: 'lake-compactor',
      name: 'In-Place Parquet Compactor',
      phase: 'Phase 5',
      category: 'storage',
      tech: 'Python / DuckDB Parquet Engine',
      latencySla: 'Scheduled (every 6 hours)',
      codePath: 'scripts/compact_lake.py',
      description: 'Solves the small-file problem caused by high-frequency streaming micro-batches. Coalesces fragmented 2KB part-files into consolidated Snappy-compressed columnar Parquet files.',
      inputs: ['Fragmented micro-batch Parquet directories'],
      outputs: ['Consolidated Snappy Parquet files (~90% file count reduction)'],
      keyDecisions: [
        'Graceful dual-engine fallback (DuckDB / PyArrow) ensuring operation across all OS environments.',
        'Preserves Hive partition directory hierarchy (year/month/day).',
      ],
    },
    {
      id: 'delta-lake-s3',
      name: 'Delta Lake ACID Log & MinIO S3',
      phase: 'Phase 7 & 10',
      category: 'storage',
      tech: 'Delta Lake (deltalake) / MinIO S3 / boto3',
      latencySla: '< 100 ms commit time',
      codePath: 'analysis/delta_lakehouse.py & analysis/s3_lakehouse.py',
      description: 'Enterprise ACID transaction log (_delta_log/*.json) providing atomic commits, time-travel auditing across historical versions, schema evolution, and S3 lifecycle storage tiering.',
      inputs: ['Micro-batch DataFrames', 'Schema additions (ambient_temp_c, humidity_pct)'],
      outputs: ['ACID-compliant Delta tables', 'S3 Glacier archive cold tiering'],
      keyDecisions: [
        'Schema evolution mode="merge" allows new IoT sensor types without rewriting historical data.',
        'Graceful offline fallback allowing the entire system to run zero-cloud and zero-cost.',
      ],
    },
    {
      id: 'airflow-orchestration',
      name: 'Workflow Orchestration (Airflow)',
      phase: 'Phase 9',
      category: 'processing',
      tech: 'Apache Airflow 2.8 / Python DAGs',
      latencySla: 'Every 15 mins (freshness) / Daily (ML)',
      codePath: 'orchestration/dags/gridpulse_orchestration_dag.py',
      description: 'Enterprise orchestrator executing end-to-end data pipeline DAGs with retries, dependency management, sensor freshness SLA checks, automated dbt validation, and ML model retraining.',
      inputs: ['Pipeline schedules', 'Sensor freshness heartbeat'],
      outputs: ['Automated pipeline execution runs', 'SLA miss Slack webhooks'],
      keyDecisions: [
        'Stand-alone Programmatic Pipeline Runner allows executing the full DAG without heavyweight local Airflow daemons.',
        'SLA latency budget enforcement alerts operators if sensor latency exceeds 15 minutes.',
      ],
    },
    {
      id: 'ai-forecaster',
      name: 'AI Demand Forecaster & Peak Shaving',
      phase: 'Phase 8',
      category: 'intelligence',
      tech: 'Scikit-Learn (Ridge / XGBoost) / Python',
      latencySla: '< 200 ms inference',
      codePath: 'analysis/forecaster.py & consumer/dispatch_engine.py',
      description: 'Predicts campus load 24 hours in advance using lag power features, hour-of-day, and day-of-week. When projected demand breaches contract thresholds (800 kW), triggers a 3-tier demand response curtailment rule.',
      inputs: ['Historical hourly facility power profiles'],
      outputs: ['24-hour demand forecast curve', 'Tier 1/2/3 curtailment commands', 'INR penalty savings'],
      keyDecisions: [
        'Contract penalty avoidance saves thousands of rupees by preventing 15-minute maximum demand ceiling breaches.',
        'Tier 1 (Soft shed EV/pumps), Tier 2 (HVAC setback), Tier 3 (Diesel generator / battery dispatch).',
      ],
    },
    {
      id: 'ghost-load',
      name: 'Hostel Ghost Load & NILM Engine',
      phase: 'Phase 11',
      category: 'intelligence',
      tech: 'Median & MAD Robust Statistics / NILM State Machine',
      latencySla: '< 50 ms per reading',
      codePath: 'analysis/ghost_load_detector.py',
      description: 'Detects unattended split ACs and lighting left ON in unoccupied hostel rooms during lecture hours (Mon-Fri 10:00–16:00). Uses robust Median/MAD baselines, 45-min hysteresis state machines, and NILM disaggregation.',
      inputs: ['Wing sub-meter telemetry (kW, PF, timestamp)', 'Wi-Fi AP client occupancy density'],
      outputs: ['Tier 1 Ghost Load Incident Alert', 'Wasted kWh, INR cost, and CO2 emissions', 'NILM cause classification'],
      keyDecisions: [
        'Uses Median & MAD instead of Mean & Std Dev: resists contamination up to 50% from regular historical waste.',
        '45-minute hysteresis window (Z > 2.5 to accumulate, Z < 1.5 to reset) eliminates false alarms from electric kettles or irons.',
        '100% Precision and 100% Recall achieved on deterministic ground-truth benchmarks.',
      ],
    },
    {
      id: 'scada-presentation',
      name: 'Next.js SCADA Portal & Webhooks',
      phase: 'Phase 4 & 11',
      category: 'presentation',
      tech: 'Next.js 16 / React 19 / Recharts / Webhooks',
      latencySla: '60 FPS UI rendering',
      codePath: 'frontend/src/app/ & consumer/webhook_dispatcher.py',
      description: 'Ultra-fast operational command center. Features real-time load telemetry, 3-tier peak-shaving dispatch, hostel ghost load monitor, interactive tooltips, and automated Slack/Teams webhook alerts.',
      inputs: ['PostgreSQL API endpoints', 'Real-time WebSocket / SSE telemetry', 'User interactive controls'],
      outputs: ['Interactive visual analytics', 'Simulated breaker soft-trip', 'Multi-channel warden incident cards'],
      keyDecisions: [
        'Rich dark-mode SCADA aesthetic with glassmorphism and informative hover tooltips across all screens.',
        'Simulated contactor controls and Wi-Fi occupancy sliders allow seamless offline demonstrations.',
      ],
    },
  ];

  const selectedNode = architectureNodes.find(n => n.id === selectedNodeId) || architectureNodes[9];

  return (
    <div className="min-h-screen bg-black text-white flex flex-col font-sans selection:bg-white selection:text-black">
      {/* TOP HEADER */}
      <header className="sticky top-0 z-40 bg-black/90 backdrop-blur-xl border-b border-[#1A1A1A] px-6 py-4 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <Link
            href="/"
            className="flex items-center gap-2 text-xs font-semibold px-3 py-1.5 rounded-xl bg-[#111111] border border-[#222222] hover:border-[#333333] text-[#A3A3A3] hover:text-white transition"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Back to Live SCADA Operations</span>
          </Link>
          <div className="h-4 w-px bg-[#1A1A1A] hidden sm:block" />
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-xl bg-[#141414] border border-[#262626] flex items-center justify-center text-white">
              <Workflow className="w-4 h-4" />
            </div>
            <div>
              <h1 className="text-sm font-extrabold text-white tracking-tight flex items-center gap-2">
                <span>GridPulse Architectural Blueprint &amp; Pipeline Engine</span>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-white/10 text-white border border-white/20">
                  Phases 1–11
                </span>
              </h1>
              <p className="text-[11px] text-[#A3A3A3]">
                End-to-end data pipeline, statistical formulations, and engineering defense guide.
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          <button
            onClick={() => setIsExplainerOpen(true)}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl bg-white hover:bg-neutral-200 text-black text-xs font-semibold transition shadow-sm"
          >
            <BookOpen className="w-3.5 h-3.5" />
            <span>💡 Feature Guide / Explainer</span>
          </button>
          <button
            onClick={() => window.print()}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-[#111111] hover:bg-[#1A1A1A] border border-[#222222] text-xs font-semibold text-white transition"
            title="Print or Save as PDF"
          >
            <FileText className="w-3.5 h-3.5 text-[#A3A3A3]" />
            <span>Print Blueprint</span>
          </button>
        </div>
      </header>

      {/* MAIN CONTAINER */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-6 space-y-8">
        {/* INTERACTIVE VISUAL PIPELINE FLOW DIAGRAM */}
        <section className="glass-panel p-6 rounded-3xl border border-slate-800 relative overflow-hidden">
          <div className="absolute top-0 right-0 w-96 h-96 bg-amber-500/5 rounded-full blur-3xl pointer-events-none -mr-20 -mt-20" />
          <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
            <div>
              <span className="text-[11px] font-mono font-bold uppercase tracking-wider text-amber-400 flex items-center gap-1.5">
                <Radio className="w-3.5 h-3.5 text-amber-400 animate-pulse" />
                <span>Interactive Pipeline Block Architecture</span>
              </span>
              <h2 className="text-base font-extrabold text-white mt-1">
                Click any pipeline block below to inspect its technical specification &amp; SLAs:
              </h2>
            </div>
            <div className="flex items-center gap-2 text-xs font-mono text-slate-400">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
              <span>11 Operational Stages Mapped</span>
            </div>
          </div>

          {/* FLOW DIAGRAM GRID */}
          <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-4 gap-3 pt-2">
            {architectureNodes.map((node, index) => {
              const isSelected = node.id === selectedNodeId;
              return (
                <div
                  key={node.id}
                  onClick={() => setSelectedNodeId(node.id)}
                  className={`cursor-pointer p-4 rounded-2xl border transition-all relative overflow-hidden group ${
                    isSelected
                      ? 'bg-amber-500/10 border-amber-500/60 shadow-lg shadow-amber-500/10 ring-1 ring-amber-500/40'
                      : 'bg-slate-900/60 border-slate-800/80 hover:border-slate-700 hover:bg-slate-900/90'
                  }`}
                >
                  <div className="flex items-center justify-between gap-1 mb-2">
                    <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-slate-800/80 text-amber-300 border border-slate-700">
                      {node.phase}
                    </span>
                    <span className="text-[10px] font-mono text-slate-500">{node.latencySla}</span>
                  </div>
                  <h3 className="font-bold text-xs text-white group-hover:text-amber-300 transition">
                    {node.name}
                  </h3>
                  <p className="text-[11px] text-slate-400 font-mono mt-1 truncate">{node.tech}</p>
                  <div className="mt-3 flex items-center justify-between text-[10px] text-slate-500 border-t border-slate-800/60 pt-2 font-mono">
                    <span className="capitalize">{node.category}</span>
                    <span className="text-amber-400 flex items-center gap-0.5">
                      <span>Inspect</span>
                      <ChevronRight className="w-3 h-3" />
                    </span>
                  </div>
                </div>
              );
            })}
          </div>

          {/* SELECTED NODE INSPECTION CARD */}
          <div className="mt-6 p-5 rounded-2xl bg-slate-950/80 border border-amber-500/30 grid grid-cols-1 lg:grid-cols-3 gap-6 animate-in fade-in duration-200">
            <div className="lg:col-span-2 space-y-3">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-xs font-mono font-bold px-2.5 py-0.5 rounded-md bg-amber-500/20 text-amber-300 border border-amber-500/40">
                  {selectedNode.phase}
                </span>
                <h3 className="text-base font-extrabold text-white">{selectedNode.name}</h3>
                <span className="text-xs font-mono text-cyan-400">[{selectedNode.tech}]</span>
              </div>
              <p className="text-xs text-slate-300 leading-relaxed">{selectedNode.description}</p>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
                <div className="p-3 rounded-xl bg-slate-900/60 border border-slate-800">
                  <span className="text-[10px] font-mono uppercase font-bold text-slate-400 flex items-center gap-1 mb-1.5">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                    <span>Inputs &amp; Data Sources:</span>
                  </span>
                  <ul className="space-y-1 text-xs text-slate-300 font-mono">
                    {selectedNode.inputs.map((inp, i) => (
                      <li key={i} className="text-[11px]">
                        • {inp}
                      </li>
                    ))}
                  </ul>
                </div>
                <div className="p-3 rounded-xl bg-slate-900/60 border border-slate-800">
                  <span className="text-[10px] font-mono uppercase font-bold text-slate-400 flex items-center gap-1 mb-1.5">
                    <Sparkles className="w-3.5 h-3.5 text-amber-400" />
                    <span>Outputs &amp; Deliverables:</span>
                  </span>
                  <ul className="space-y-1 text-xs text-slate-300 font-mono">
                    {selectedNode.outputs.map((out, i) => (
                      <li key={i} className="text-[11px]">
                        • {out}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>

            {/* Meta & Key Decisions Column */}
            <div className="space-y-3 border-t lg:border-t-0 lg:border-l border-slate-800 lg:pl-6">
              <div>
                <span className="text-[10px] font-mono text-slate-500 uppercase">Repository Code Location:</span>
                <div className="mt-1 flex items-center gap-1.5 text-xs font-mono text-amber-300 bg-slate-900 px-2.5 py-1.5 rounded-lg border border-slate-800 truncate">
                  <Code2 className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                  <span className="truncate">{selectedNode.codePath}</span>
                </div>
              </div>

              <div>
                <span className="text-[10px] font-mono text-slate-500 uppercase">Latency Budget SLA:</span>
                <p className="text-xs font-mono font-bold text-emerald-400 mt-0.5">{selectedNode.latencySla}</p>
              </div>

              <div>
                <span className="text-[10px] font-mono text-slate-500 uppercase">Engineering Rationale:</span>
                <ul className="mt-1 space-y-1 text-xs text-slate-300">
                  {selectedNode.keyDecisions.map((dec, i) => (
                    <li key={i} className="text-[11px] leading-relaxed">
                      • {dec}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </section>

        {/* DETAILED ENGINEERING DEEP-DIVE TABS */}
        <section className="space-y-4">
          <div className="flex items-center gap-2 border-b border-slate-800 pb-px overflow-x-auto">
            {[
              { id: 'ghostload', label: '🛏️ Hostel Waste & NILM Machine Learning', icon: BedDouble },
              { id: 'math', label: '📐 Mathematical Formulas & Statistics', icon: BookOpen },
              { id: 'qa', label: '🎯 Evaluator Q&A Defense Cheat-Sheet', icon: ShieldAlert },
              { id: 'lakehouse', label: '🏛️ ACID Lakehouse & S3 Storage Engine', icon: Database },
              { id: 'dispatch', label: '🔮 Peak-Shaving & Demand Curtailment', icon: Sliders },
              { id: 'pipeline', label: '⚡ Stream Processing & Kafka Ingestion', icon: Radio },
            ].map(tab => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id as any)}
                  className={`flex items-center gap-2 px-4 py-2.5 rounded-t-xl text-xs font-bold transition-all border-t border-x whitespace-nowrap ${
                    isActive
                      ? 'bg-slate-900 border-slate-700 text-amber-400 shadow-sm'
                      : 'border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-900/40'
                  }`}
                >
                  <Icon className={`w-3.5 h-3.5 ${isActive ? 'text-amber-400' : 'text-slate-500'}`} />
                  <span>{tab.label}</span>
                </button>
              );
            })}
          </div>

          {/* TAB 1: HOSTEL GHOST LOAD DEEP DIVE */}
          {activeTab === 'ghostload' && (
            <div className="glass-panel p-6 rounded-2xl border border-slate-800 space-y-6 animate-in fade-in">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h3 className="text-base font-extrabold text-white">
                    Hostel Ghost Load Detection: The Non-Intrusive Intelligence Strategy
                  </h3>
                  <p className="text-xs text-slate-400 mt-1 max-w-3xl">
                    Addressing unattended power wastage when students leave hostel rooms for lectures without installing invasive or expensive hardware sensors in 500+ rooms.
                  </p>
                </div>
                <Link
                  href="/"
                  className="px-3 py-1.5 rounded-xl bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/30 text-xs font-semibold text-amber-300 transition shrink-0"
                >
                  View Live in Dashboard →
                </Link>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800 space-y-2">
                  <div className="flex items-center gap-2 text-amber-400 font-bold text-xs">
                    <span className="w-5 h-5 rounded-full bg-amber-500/20 flex items-center justify-center text-[11px]">1</span>
                    <span>Robust Median &amp; MAD Baseline</span>
                  </div>
                  <p className="text-xs text-slate-300 leading-relaxed">
                    Computes typical power per <code className="text-amber-300 font-mono">(day_of_week, 15_min_slot)</code> tuple. Because waste already happens regularly, a Gaussian mean-based baseline learns waste as normal. The median has a breakdown point of 50%, resisting contamination.
                  </p>
                </div>

                <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800 space-y-2">
                  <div className="flex items-center gap-2 text-amber-400 font-bold text-xs">
                    <span className="w-5 h-5 rounded-full bg-amber-500/20 flex items-center justify-center text-[11px]">2</span>
                    <span>Hysteresis State Machine</span>
                  </div>
                  <p className="text-xs text-slate-300 leading-relaxed">
                    Operates with dual thresholds: <code className="text-rose-300 font-mono">Z &gt; 2.5</code> accumulates elevated minutes, while <code className="text-emerald-300 font-mono">Z &lt; 1.5</code> resets the buffer. An incident only opens when <code className="text-amber-300 font-mono">elevated_minutes &ge; 45</code>, preventing alert flapping from short kettle boils or irons.
                  </p>
                </div>

                <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800 space-y-2">
                  <div className="flex items-center gap-2 text-amber-400 font-bold text-xs">
                    <span className="w-5 h-5 rounded-full bg-amber-500/20 flex items-center justify-center text-[11px]">3</span>
                    <span>NILM Load Disaggregation</span>
                  </div>
                  <p className="text-xs text-slate-300 leading-relaxed">
                    Separates inductive compressor motors (<code className="text-amber-300 font-mono">PF ~0.78</code> with 20–40 min periodic duty cycles) from resistive lighting and study lamps (<code className="text-purple-300 font-mono">PF ~0.99</code> flat load).
                  </p>
                </div>
              </div>

              {/* Wi-Fi & Safety Contactor */}
              <div className="p-4 rounded-xl bg-gradient-to-r from-cyan-950/30 to-slate-950/60 border border-cyan-500/30 space-y-2">
                <h4 className="font-bold text-xs text-cyan-300 flex items-center gap-2">
                  <Wifi className="w-4 h-4 text-cyan-400" />
                  <span>Wi-Fi Occupancy Density Cross-Validation (Zero Hardware Addition)</span>
                </h4>
                <p className="text-xs text-slate-300 leading-relaxed">
                  Campus Cisco/Aruba Wi-Fi access points log connected MAC addresses per wing. When wing electrical demand surges to 28 kW during lecture hours while the Wi-Fi controller reports only 1–3 connected devices, this divergence delivers strong empirical evidence of unoccupied waste without invading student privacy.
                </p>
              </div>
            </div>
          )}

          {/* TAB 2: MATHEMATICAL FORMULATIONS */}
          {activeTab === 'math' && (
            <div className="glass-panel p-6 rounded-2xl border border-slate-800 space-y-6 animate-in fade-in">
              <div>
                <h3 className="text-base font-extrabold text-white">Mathematical Formulations &amp; Statistical Formats</h3>
                <p className="text-xs text-slate-400 mt-1">
                  Equations implemented across the GridPulse analytics engine for robust detection and energy accounting.
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-2">
                  <span className="text-xs font-mono font-bold text-amber-400 uppercase">
                    1. Robust Median Absolute Deviation (MAD):
                  </span>
                  <div className="bg-slate-900 p-3 rounded-lg font-mono text-xs text-slate-200 border border-slate-800">
                    MAD = median(|P_i - median(P)|)<br />
                    sigma_robust = 1.4826 * MAD
                  </div>
                  <p className="text-[11px] text-slate-400">
                    The constant 1.4826 normalizes the MAD to match the standard deviation of a normal distribution while resisting up to 50% outliers.
                  </p>
                </div>

                <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-2">
                  <span className="text-xs font-mono font-bold text-amber-400 uppercase">
                    2. Robust Anomaly Z-Score:
                  </span>
                  <div className="bg-slate-900 p-3 rounded-lg font-mono text-xs text-slate-200 border border-slate-800">
                    Z = (P_observed - Median_baseline) / (1.4826 * MAD + 1e-6)
                  </div>
                  <p className="text-[11px] text-slate-400">
                    Z &gt; 2.5 flags an anomaly (+2.5 robust standard deviations above baseline). Z &lt; 1.5 clears the anti-flapping buffer.
                  </p>
                </div>

                <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-2">
                  <span className="text-xs font-mono font-bold text-amber-400 uppercase">
                    3. Consistent Excess Energy &amp; Cost Integration:
                  </span>
                  <div className="bg-slate-900 p-3 rounded-lg font-mono text-xs text-slate-200 border border-slate-800">
                    Excess_kW = max(P_observed - Median_baseline, 0)<br />
                    Wasted_kWh = sum(Excess_kW / 60) [1-min samples]<br />
                    Cost_INR = Wasted_kWh * 8.00<br />
                    CO2_kg = Wasted_kWh * 0.82
                  </div>
                  <p className="text-[11px] text-slate-400">
                    Both anomaly scoring and excess power integration use the consistent Median_baseline reference.
                  </p>
                </div>

                <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-2">
                  <span className="text-xs font-mono font-bold text-amber-400 uppercase">
                    4. Periodic Compressor Lag Autocorrelation:
                  </span>
                  <div className="bg-slate-900 p-3 rounded-lg font-mono text-xs text-slate-200 border border-slate-800">
                    R_xx(k) = sum((P_t - mu)*(P_(t+k) - mu)) / sum((P_t - mu)^2)<br />
                    Peak at k in [20, 40] min confirms AC compressor cycle
                  </div>
                  <p className="text-[11px] text-slate-400">
                    Thermostatic cycling produces a signature periodic lag in the 20 to 40 minute window, confirming automated AC cycling.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* TAB 3: EVALUATOR Q&A DEFENSE */}
          {activeTab === 'qa' && (
            <div className="glass-panel p-6 rounded-2xl border border-slate-800 space-y-6 animate-in fade-in">
              <div>
                <h3 className="text-base font-extrabold text-white">Evaluator &amp; Faculty Presentation Defense Cheat-Sheet</h3>
                <p className="text-xs text-slate-400 mt-1">
                  Crisp, technically rigorous answers to challenging faculty questions during your demonstration.
                </p>
              </div>

              <div className="space-y-4">
                <div className="p-4 rounded-xl bg-slate-950/80 border border-slate-800 space-y-1.5">
                  <h4 className="text-xs font-bold text-amber-400 flex items-center gap-2">
                    <span className="text-slate-500 font-mono">Q1:</span>
                    <span>&quot;Why not install motion sensors (PIR) or smart plugs in every hostel room?&quot;</span>
                  </h4>
                  <p className="text-xs text-slate-300 leading-relaxed">
                    <strong>Answer:</strong> Installing PIR sensors or smart plugs across 500+ rooms incurs major capital expenditure (~$50–100/room), ongoing battery maintenance, and student pushback regarding surveillance in private living spaces. GridPulse proves that <em>existing wing-level electrical sub-meters</em> already contain the high-resolution signal needed when paired with robust statistics (Median/MAD) and NILM disaggregation.
                  </p>
                </div>

                <div className="p-4 rounded-xl bg-slate-950/80 border border-slate-800 space-y-1.5">
                  <h4 className="text-xs font-bold text-amber-400 flex items-center gap-2">
                    <span className="text-slate-500 font-mono">Q2:</span>
                    <span>&quot;Why did you choose Median &amp; MAD over Gaussian Mean &amp; Standard Deviation?&quot;</span>
                  </h4>
                  <p className="text-xs text-slate-300 leading-relaxed">
                    <strong>Answer:</strong> In campus facilities where waste happens regularly, a Mean/Std Dev baseline incorporates the waste into &quot;normal&quot; behavior. Standard deviation has an breakdown point of 0% (a single outlier corrupts it). In contrast, Median and MAD have a 50% breakdown point, resisting contamination and maintaining a true baseline.
                  </p>
                </div>

                <div className="p-4 rounded-xl bg-slate-950/80 border border-slate-800 space-y-1.5">
                  <h4 className="text-xs font-bold text-amber-400 flex items-center gap-2">
                    <span className="text-slate-500 font-mono">Q3:</span>
                    <span>&quot;How do you prevent false alarms when students boil a kettle or iron clothes?&quot;</span>
                  </h4>
                  <p className="text-xs text-slate-300 leading-relaxed">
                    <strong>Answer:</strong> We implement a dual-threshold hysteresis state machine with a 45-minute persistence filter. Boiling a kettle creates a 10-minute spike that will not open an event. An event opens only when Z &gt; 2.5 persists for &ge; 45 continuous minutes, and resets when load drops below Z &lt; 1.5. This hysteresis gap prevents flapping.
                  </p>
                </div>

                <div className="p-4 rounded-xl bg-slate-950/80 border border-slate-800 space-y-1.5">
                  <h4 className="text-xs font-bold text-amber-400 flex items-center gap-2">
                    <span className="text-slate-500 font-mono">Q4:</span>
                    <span>&quot;What is your benchmark ground-truth accuracy?&quot;</span>
                  </h4>
                  <p className="text-xs text-slate-300 leading-relaxed">
                    <strong>Answer:</strong> We evaluated the system using deterministic ground-truth episodes injected via the simulator. Out of 4 episodes, 3 sustained episodes (&ge; 45m) were correctly detected (100% Recall), 0 false alarms were triggered (100% Precision, 100% F1-Score), and 1 transient spike was successfully ignored. Mean detection delay was 35 minutes.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* TAB 4: LAKEHOUSE STORAGE ENGINE */}
          {activeTab === 'lakehouse' && (
            <div className="glass-panel p-6 rounded-2xl border border-slate-800 space-y-6 animate-in fade-in">
              <div>
                <h3 className="text-base font-extrabold text-white">ACID Data Lakehouse, S3 MinIO &amp; Medallion Architecture</h3>
                <p className="text-xs text-slate-400 mt-1">
                  Separating high-frequency operational SCADA from cost-effective long-term columnar analytical storage.
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="p-4 rounded-xl bg-slate-950/60 border border-amber-900/40 space-y-2">
                  <span className="text-[10px] font-mono font-bold text-amber-400 uppercase">Bronze Layer</span>
                  <h4 className="font-bold text-xs text-white">Raw Append-Only Parquet</h4>
                  <p className="text-[11px] text-slate-300 leading-relaxed">
                    Partitioned by Hive convention: <code className="text-amber-300 font-mono">year/month/day</code>. Captures raw micro-batch streams from Kafka and Spark without mutation.
                  </p>
                </div>

                <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-700/60 space-y-2">
                  <span className="text-[10px] font-mono font-bold text-slate-300 uppercase">Silver Layer</span>
                  <h4 className="font-bold text-xs text-white">Cleaned &amp; Validated Models</h4>
                  <p className="text-[11px] text-slate-300 leading-relaxed">
                    Executed via dbt. Deduplicates event IDs, bounds voltage to nominal limits (180V–260V), and joins facility metadata.
                  </p>
                </div>

                <div className="p-4 rounded-xl bg-slate-950/60 border border-amber-500/40 space-y-2">
                  <span className="text-[10px] font-mono font-bold text-amber-400 uppercase">Gold Layer</span>
                  <h4 className="font-bold text-xs text-white">Aggregated Analytical Marts</h4>
                  <p className="text-[11px] text-slate-300 leading-relaxed">
                    <code className="text-amber-300 font-mono">dim_facility_efficiency</code> computes load factors. <code className="text-amber-300 font-mono">fct_daily_campus_dispatch</code> tracks daily peak demand.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* TAB 5: PEAK SHAVING DISPATCH */}
          {activeTab === 'dispatch' && (
            <div className="glass-panel p-6 rounded-2xl border border-slate-800 space-y-6 animate-in fade-in">
              <div>
                <h3 className="text-base font-extrabold text-white">Automated 3-Tier Peak-Shaving Demand Response</h3>
                <p className="text-xs text-slate-400 mt-1">
                  Defending campus utility contracts against expensive maximum demand (MD) penalty tariffs.
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="p-4 rounded-xl bg-slate-950/60 border border-amber-500/30 space-y-2">
                  <span className="text-[10px] font-mono font-bold text-amber-400 uppercase">Tier 1: Soft Shedding</span>
                  <h4 className="font-bold text-xs text-white">Overload &lt; 50 kW</h4>
                  <p className="text-[11px] text-slate-300 leading-relaxed">
                    Temporarily cuts non-critical infrastructure: EV chargers, campus decorative lighting, and auxiliary fountain pumps (~45 kW total shed).
                  </p>
                </div>

                <div className="p-4 rounded-xl bg-slate-950/60 border border-purple-500/30 space-y-2">
                  <span className="text-[10px] font-mono font-bold text-purple-400 uppercase">Tier 2: Chiller Cycling</span>
                  <h4 className="font-bold text-xs text-white">Overload 50–120 kW</h4>
                  <p className="text-[11px] text-slate-300 leading-relaxed">
                    Enacts 15-minute staggered duty cycling on central HVAC chillers in academic complexes. Thermal inertia maintains indoor room comfort (~85 kW shed).
                  </p>
                </div>

                <div className="p-4 rounded-xl bg-slate-950/60 border border-rose-500/30 space-y-2">
                  <span className="text-[10px] font-mono font-bold text-rose-400 uppercase">Tier 3: Generation Dispatch</span>
                  <h4 className="font-bold text-xs text-white">Overload &gt; 120 kW</h4>
                  <p className="text-[11px] text-slate-300 leading-relaxed">
                    Syncs campus rooftop solar battery storage and diesel gensets onto the microgrid bus to shave the peak from the supply side.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* TAB 6: STREAM PROCESSING */}
          {activeTab === 'pipeline' && (
            <div className="glass-panel p-6 rounded-2xl border border-slate-800 space-y-6 animate-in fade-in">
              <div>
                <h3 className="text-base font-extrabold text-white">Real-Time Stream Ingestion &amp; Kafka Topology</h3>
                <p className="text-xs text-slate-400 mt-1">
                  Fault-tolerant event-driven pipeline capable of handling thousands of sensor readings per second.
                </p>
              </div>

              <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 font-mono text-xs text-slate-300 space-y-2">
                <div className="text-amber-400 font-bold">Kafka Topic Architecture:</div>
                <div className="p-3 bg-slate-900 rounded-lg text-[11px] space-y-1">
                  <div>• <code>campus.telemetry.raw</code> (Partitions: 4, Replication Factor: 1)</div>
                  <div>• Key: <code>building_id</code> (Guarantees ordered delivery per facility)</div>
                  <div>• Serialization: JSON schema with ISO-8601 timestamps and electrical metrics</div>
                </div>
              </div>
            </div>
          )}
        </section>
      </main>

      {/* FOOTER */}
      <footer className="border-t border-slate-800/80 px-6 py-4 bg-slate-950/60 text-xs text-slate-500 flex flex-wrap items-center justify-between gap-4 font-mono">
        <div>GridPulse SCADA Engineering Blueprint • Complete 11-Phase Autonomous Microgrid</div>
        <div className="flex items-center gap-4">
          <Link href="/" className="hover:text-amber-400 transition">Live Dashboard</Link>
          <span>•</span>
          <Link href="/howItWorks" className="hover:text-amber-400 transition">/howItWorks</Link>
        </div>
      </footer>

      {/* SEARCHABLE FEATURE EXPLAINER MODAL */}
      <FeatureExplainerModal isOpen={isExplainerOpen} onClose={() => setIsExplainerOpen(false)} />
    </div>
  );
}
