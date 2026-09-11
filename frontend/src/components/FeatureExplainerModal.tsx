'use client';

import React, { useState } from 'react';
import {
  X,
  Search,
  BookOpen,
  Zap,
  BedDouble,
  Sliders,
  Database,
  Radio,
  ExternalLink,
  ShieldCheck,
  CheckCircle2,
  AlertTriangle,
} from 'lucide-react';
import Link from 'next/link';

interface FeatureExplainerModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function FeatureExplainerModal({ isOpen, onClose }: FeatureExplainerModalProps) {
  const [searchTerm, setSearchTerm] = useState('');
  const [activeCategory, setActiveCategory] = useState<string>('all');

  if (!isOpen) return null;

  const features = [
    {
      id: 'ghost-load',
      title: 'Hostel Ghost Load & Unoccupied Room Waste Monitor (Phase 11)',
      category: 'ghostload',
      icon: BedDouble,
      badge: 'ML / NILM',
      summary: 'Detects unattended ACs and lighting in unoccupied hostel rooms using wing-level smart meters.',
      bullets: [
        'Robust Median & MAD Baseline: Computes typical power per (weekday, 15-min slot). Unlike Mean/Std Dev, Median is impervious to historical waste contamination.',
        'Hysteresis State Machine: Requires Z-Score > 2.5 for >= 45 consecutive minutes before triggering an alert. Automatically resets when Z < 1.5, preventing alert flapping from tea kettles or irons.',
        'NILM Disaggregation: Distinguishes AC compressor cycles (PF ~0.78, 20-40 min lag autocorrelation) from resistive lighting/heaters (PF ~0.99, flat profile).',
        'Simulated Wi-Fi Cross-Validation: Correlates wing power against connected Wi-Fi AP density (e.g. 2 devices with 32 kW demand = 96% waste confidence).',
        'Quantified Benchmark: Evaluated against injected ground truth with 100% Precision and 100% Recall (35 min mean detection latency).',
      ],
      talkingPoint: 'Why not PIR sensors in every room? Installing sensors in 500+ rooms costs thousands of dollars and raises student privacy issues. Wing-level smart meters provide strong empirical evidence non-intrusively.',
    },
    {
      id: 'realtime-stream',
      title: 'Real-Time Power Telemetry & 1-Second Sliding Windows (Phase 2 & 4)',
      category: 'streaming',
      icon: Radio,
      badge: 'Kafka + Spark',
      summary: 'Monitors high-frequency telemetry across 42 smart meters with instantaneous power, voltage, and power factor.',
      bullets: [
        'High-Frequency Sampling: Emulates real-time IoT feeds pushed into Apache Kafka and Spark Streaming.',
        'Phase Diagnostics: Tracks phase voltage (220-240V nominal) and grid frequency (50.00 Hz) to detect brownouts, sags, and surges.',
        'Live Load Curves: Real-time Recharts visualization with 60 FPS SVG interpolation.',
      ],
      talkingPoint: 'Proves full-duplex stream processing: the streaming pipeline processes 1-minute tumbling windows in sub-second latency.',
    },
    {
      id: 'peak-shaving',
      title: 'AI Peak-Shaving & Demand Response Dispatch (Phase 8)',
      category: 'dispatch',
      icon: Sliders,
      badge: 'AI Dispatch',
      summary: 'Prevents expensive utility maximum demand (MD) penalty tariffs using ML forecasts and automated curtailment.',
      bullets: [
        '24-Hour ML Forecaster: Ridge / XGBoost models trained on lag features and ambient weather predict campus demand.',
        '3-Tier Automated Curtailment: Tier 1 (Soft shed of non-critical EV chargers), Tier 2 (Academic HVAC duty cycling), Tier 3 (Diesel generator sync & battery dispatch).',
        'Warden Webhook Dispatch: Generates rich Slack and Teams incident cards with cost avoidance metrics in INR.',
      ],
      talkingPoint: 'Commercial electricity tariffs charge massive penalty rates if campus demand exceeds contract limits for even 15 minutes. This system saves hundreds of thousands of rupees annually.',
    },
    {
      id: 'lakehouse-storage',
      title: 'ACID Data Lakehouse & S3 MinIO Storage Tiering (Phase 5, 6, 10)',
      category: 'lakehouse',
      icon: Database,
      badge: 'Delta + DuckDB',
      summary: 'Columnar Parquet and Delta Lake storage engine supporting time-travel auditing and vectorized SQL.',
      bullets: [
        'Medallion Architecture: Bronze (raw streaming Parquet), Silver (cleaned & deduplicated), Gold (aggregated marts).',
        'In-Place Compaction (OPTIMIZE): Coalesces streaming micro-batch files to solve the small-file problem.',
        'Zero-Copy DuckDB Analytics: Executes sub-second analytical SQL over millions of telemetry rows.',
      ],
      talkingPoint: 'Demonstrates enterprise lakehouse design: separation of storage and compute without expensive vendor lock-in.',
    },
  ];

  const filtered = features.filter(f => {
    const matchesSearch =
      f.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
      f.summary.toLowerCase().includes(searchTerm.toLowerCase()) ||
      f.bullets.some(b => b.toLowerCase().includes(searchTerm.toLowerCase()));
    const matchesCat = activeCategory === 'all' || f.category === activeCategory;
    return matchesSearch && matchesCat;
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-black/80 backdrop-blur-md animate-in fade-in duration-200">
      <div className="bg-slate-900 border border-slate-700/80 rounded-2xl w-full max-w-4xl max-h-[90vh] flex flex-col shadow-2xl overflow-hidden">
        {/* Modal Header */}
        <div className="px-6 py-5 border-b border-slate-800 flex items-center justify-between bg-slate-950/60">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-400">
              <BookOpen className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-white flex items-center gap-2">
                GridPulse Feature & Operational Explainer Guide
              </h2>
              <p className="text-xs text-slate-400">
                Detailed technical breakdown of every algorithm, ML detector, and engineering design choice.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg bg-slate-800/80 text-slate-400 hover:text-white hover:bg-slate-700 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Search & Categories Bar */}
        <div className="px-6 py-3 border-b border-slate-800/80 bg-slate-900/40 flex flex-wrap items-center justify-between gap-3">
          <div className="relative flex-1 min-w-[240px]">
            <Search className="w-4 h-4 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Search features, ML algorithms, statistics (e.g. MAD, Hysteresis, NILM)..."
              value={searchTerm}
              onChange={e => setSearchTerm(e.target.value)}
              className="w-full pl-9 pr-3 py-1.5 text-xs bg-slate-950/60 border border-slate-800 rounded-lg text-slate-200 placeholder-slate-500 focus:outline-none focus:border-amber-500/50"
            />
          </div>
          <div className="flex items-center gap-1 text-xs">
            {[
              { id: 'all', label: 'All Modules' },
              { id: 'ghostload', label: 'Hostel Waste (Phase 11)' },
              { id: 'streaming', label: 'Telemetry Stream' },
              { id: 'dispatch', label: 'Peak Shaving' },
              { id: 'lakehouse', label: 'Lakehouse' },
            ].map(cat => (
              <button
                key={cat.id}
                onClick={() => setActiveCategory(cat.id)}
                className={`px-2.5 py-1 rounded-md transition font-medium ${
                  activeCategory === cat.id
                    ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {cat.label}
              </button>
            ))}
          </div>
        </div>

        {/* Modal Body */}
        <div className="p-6 overflow-y-auto space-y-6 flex-1">
          {filtered.length === 0 ? (
            <div className="text-center py-12 text-slate-400 text-xs">
              No matching features found for &quot;{searchTerm}&quot;.
            </div>
          ) : (
            filtered.map(feature => {
              const Icon = feature.icon;
              return (
                <div
                  key={feature.id}
                  className="glass-panel p-5 rounded-xl border border-slate-800 hover:border-slate-700 transition"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-lg bg-slate-800 border border-slate-700 flex items-center justify-center text-amber-400">
                        <Icon className="w-4 h-4" />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <h3 className="font-bold text-sm text-white">{feature.title}</h3>
                          <span className="text-[10px] font-mono font-semibold px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/30">
                            {feature.badge}
                          </span>
                        </div>
                        <p className="text-xs text-slate-300 mt-1">{feature.summary}</p>
                      </div>
                    </div>
                  </div>

                  <div className="mt-4 space-y-2 border-t border-slate-800/80 pt-3">
                    <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                      Technical Mechanisms:
                    </span>
                    <ul className="space-y-1.5 text-xs text-slate-300">
                      {feature.bullets.map((b, idx) => (
                        <li key={idx} className="flex items-start gap-2">
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0 mt-0.5" />
                          <span>{b}</span>
                        </li>
                      ))}
                    </ul>
                  </div>

                  {feature.talkingPoint && (
                    <div className="mt-3.5 p-3 rounded-lg bg-amber-500/5 border border-amber-500/20 text-xs">
                      <span className="font-semibold text-amber-300 flex items-center gap-1.5 mb-1">
                        <Zap className="w-3.5 h-3.5 text-amber-400" />
                        Key Defense Talking Point for Evaluators:
                      </span>
                      <p className="text-slate-300 leading-relaxed text-[11px]">{feature.talkingPoint}</p>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>

        {/* Modal Footer */}
        <div className="px-6 py-4 border-t border-slate-800 bg-slate-950/60 flex items-center justify-between">
          <Link
            href="/howItWorks"
            className="flex items-center gap-1.5 text-xs font-semibold text-amber-400 hover:text-amber-300 transition"
          >
            <span>Open Complete Architectural Blueprint &amp; Flow Diagram (/howItWorks)</span>
            <ExternalLink className="w-3.5 h-3.5" />
          </Link>
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-medium text-slate-200 transition"
          >
            Close Guide
          </button>
        </div>
      </div>
    </div>
  );
}

export default FeatureExplainerModal;
