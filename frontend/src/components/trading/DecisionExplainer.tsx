'use client';

import React from 'react';
import {
  ShieldAlert,
  ShieldCheck,
  CheckCircle2,
  AlertOctagon,
  TrendingUp,
  TrendingDown,
  Layers,
  Activity,
  AlertTriangle,
  Info,
  Clock,
  ArrowRight,
  Flame,
  Zap,
} from 'lucide-react';

interface DecisionExplainerProps {
  decision: {
    action: string;
    candidateAction: string;
    confidence: number;
    reasons: string[];
    riskState: string;
    tradePermitted: boolean;
    vetoReasons: string[];
    sizeMultiplier: number;
    riskTier: string;
    killSwitchActive: boolean;
    hedgeOrders: Array<{ action: string; symbol: string; quantity: number; reason: string }>;
    emergencyOrders: Array<{ orderType: string; reason: string }>;
    telemetry: {
      midPrice: number;
      spreadBps: number;
      orderFlowImbalance: number;
      vpin: number;
      depthDropPct: number;
      realizedVolatility: number;
    };
    statArbTelemetry: {
      spreadZScore: number;
      statArbState: string;
    };
    evaluationLatencyMs: number;
  };
}

export const DecisionExplainer: React.FC<DecisionExplainerProps> = ({ decision }) => {
  const isApproved = decision.tradePermitted;
  const isVetoed = !decision.tradePermitted && decision.candidateAction !== 'HOLD';

  const getActionColor = (action: string) => {
    if (action === 'BUY') return 'bg-emerald-500/20 text-emerald-400 border-emerald-500/50';
    if (action === 'SELL') return 'bg-rose-500/20 text-rose-400 border-rose-500/50';
    return 'bg-amber-500/20 text-amber-400 border-amber-500/50';
  };

  const vpinVal = decision.telemetry?.vpin || 0;
  const isVpinToxic = vpinVal >= 0.85;

  const ofiVal = decision.telemetry?.orderFlowImbalance || 0;
  const depthDrop = decision.telemetry?.depthDropPct || 0;
  const isDepthVacuum = depthDrop >= 70;

  return (
    <div className="bg-[#0A0A0A] border border-[#1A1A1A] rounded-xl p-5 shadow-2xl flex flex-col gap-5">
      {/* Top Header: Final Action & Consensus Summary */}
      <div className="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-[#1A1A1A]">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-[#141414] border border-[#262626]">
            <Activity className="w-4 h-4 text-[#FFFFFF]" />
          </div>
          <div>
            <h2 className="text-sm font-bold text-[#FFFFFF] uppercase tracking-wider flex items-center gap-2">
              Decision Arbiter & Transparency Matrix
              <span className="text-[10px] font-mono text-[#A3A3A3] bg-[#141414] px-2 py-0.5 rounded border border-[#262626]">
                {decision.evaluationLatencyMs.toFixed(3)} ms latency
              </span>
            </h2>
            <p className="text-xs text-[#A3A3A3] mt-0.5">
              Multi-signal fusion of GBDT Alpha, Kalman Stat-Arb pairs, and microstructure surveillance
            </p>
          </div>
        </div>

        {/* Action Badge & Confidence Gauge */}
        <div className="flex items-center gap-4">
          <div className="text-right">
            <div className="text-[10px] text-[#A3A3A3] uppercase font-medium">Composite Confidence</div>
            <div className="text-base font-bold font-mono text-[#FFFFFF]">
              {(decision.confidence * 100).toFixed(1)}%
            </div>
          </div>

          <div className={`px-4 py-2 rounded-lg border text-sm font-bold tracking-wider uppercase flex items-center gap-2 ${getActionColor(decision.action)}`}>
            {decision.action === 'BUY' && <TrendingUp className="w-4 h-4" />}
            {decision.action === 'SELL' && <TrendingDown className="w-4 h-4" />}
            {decision.action === 'HOLD' && <AlertOctagon className="w-4 h-4" />}
            <span>FINAL: {decision.action}</span>
          </div>

          {/* Sizing Multiplier Badge */}
          <div className="px-3 py-2 bg-[#000000] border border-[#1A1A1A] rounded-lg text-xs font-mono text-[#A3A3A3]">
            Sizing: <span className="font-bold text-[#FFFFFF]">{decision.sizeMultiplier.toFixed(2)}x</span>
          </div>
        </div>
      </div>

      {/* Grid: 3 Analytical Columns */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Column 1: Multi-Signal Consensus & Forecasting */}
        <div className="bg-[#000000] border border-[#1A1A1A] rounded-lg p-3.5 flex flex-col gap-3">
          <div className="flex items-center justify-between text-xs font-semibold text-[#FFFFFF] border-b border-[#1A1A1A] pb-2">
            <span className="flex items-center gap-1.5">
              <Layers className="w-3.5 h-3.5 text-[#A3A3A3]" />
              Signal Consensus
            </span>
            <span className="text-[10px] font-mono text-[#A3A3A3]">Horizon: 5m</span>
          </div>

          {/* Candidate vs Arbitrated Direction */}
          <div className="flex items-center justify-between text-xs bg-[#0A0A0A] p-2 rounded border border-[#1A1A1A]">
            <span className="text-[#A3A3A3]">Candidate (Raw Alpha):</span>
            <span className="font-bold font-mono text-[#FFFFFF]">{decision.candidateAction}</span>
          </div>

          {/* Stat-Arb Cointegration Spread Z-score */}
          <div className="flex items-center justify-between text-xs bg-[#0A0A0A] p-2 rounded border border-[#1A1A1A]">
            <span className="text-[#A3A3A3]">Stat-Arb Cointegration Z:</span>
            <span className="font-bold font-mono text-[#FFFFFF]">
              {decision.statArbTelemetry?.spreadZScore ? `${decision.statArbTelemetry.spreadZScore > 0 ? '+' : ''}${decision.statArbTelemetry.spreadZScore}σ` : 'N/A'}
            </span>
          </div>

          {/* Contributing Reasons */}
          <div className="flex flex-col gap-1.5 mt-1">
            <div className="text-[10px] font-semibold text-[#A3A3A3] uppercase tracking-wider">
              Active Rationale:
            </div>
            <div className="flex flex-col gap-1 max-h-28 overflow-y-auto pr-1">
              {decision.reasons.length > 0 ? (
                decision.reasons.map((r, idx) => (
                  <div key={idx} className="text-[11px] text-[#D4D4D4] flex items-start gap-1.5 leading-snug">
                    <CheckCircle2 className="w-3 h-3 text-[#A3A3A3] mt-0.5 shrink-0" />
                    <span>{r}</span>
                  </div>
                ))
              ) : (
                <div className="text-[11px] text-[#525252] italic">No strong directional consensus.</div>
              )}
            </div>
          </div>
        </div>

        {/* Column 2: Microstructure Toxicity & Depth Health */}
        <div className="bg-[#000000] border border-[#1A1A1A] rounded-lg p-3.5 flex flex-col gap-3">
          <div className="flex items-center justify-between text-xs font-semibold text-[#FFFFFF] border-b border-[#1A1A1A] pb-2">
            <span className="flex items-center gap-1.5">
              <Flame className="w-3.5 h-3.5 text-amber-400" />
              Microstructure Health
            </span>
            <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${
              decision.riskState === 'NORMAL' ? 'bg-emerald-950 text-emerald-400' : 'bg-red-950 text-red-400'
            }`}>
              {decision.riskState}
            </span>
          </div>

          {/* VPIN Toxicity Bar */}
          <div className="flex flex-col gap-1">
            <div className="flex items-center justify-between text-xs">
              <span className="text-[#A3A3A3]">VPIN (Toxicity):</span>
              <span className={`font-mono font-bold ${isVpinToxic ? 'text-rose-400 animate-pulse' : 'text-[#FFFFFF]'}`}>
                {vpinVal.toFixed(3)} {isVpinToxic && '(TOXIC SURGE)'}
              </span>
            </div>
            <div className="w-full bg-[#171717] rounded-full h-1.5 overflow-hidden">
              <div
                className={`h-full transition-all duration-300 ${
                  isVpinToxic ? 'bg-rose-500' : vpinVal > 0.65 ? 'bg-amber-400' : 'bg-emerald-400'
                }`}
                style={{ width: `${Math.min(100, vpinVal * 100)}%` }}
              />
            </div>
          </div>

          {/* Order Flow Imbalance (OFI) */}
          <div className="flex flex-col gap-1">
            <div className="flex items-center justify-between text-xs">
              <span className="text-[#A3A3A3]">Order Flow Imbalance:</span>
              <span className={`font-mono font-bold ${ofiVal > 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                {ofiVal > 0 ? '+' : ''}{ofiVal.toFixed(3)}
              </span>
            </div>
            <div className="w-full bg-[#171717] rounded-full h-1.5 relative overflow-hidden">
              <div
                className={`h-full absolute top-0 transition-all ${ofiVal >= 0 ? 'bg-emerald-400 left-1/2' : 'bg-rose-500 right-1/2'}`}
                style={{ width: `${Math.min(50, Math.abs(ofiVal) * 50)}%` }}
              />
            </div>
          </div>

          {/* Order Book Depth Evacuation % */}
          <div className="flex items-center justify-between text-xs bg-[#0A0A0A] p-2 rounded border border-[#1A1A1A]">
            <span className="text-[#A3A3A3]">L2 Depth Evacuation:</span>
            <span className={`font-mono font-bold ${isDepthVacuum ? 'text-rose-400' : 'text-slate-300'}`}>
              {depthDrop.toFixed(1)}% {isDepthVacuum && '(VACUUM)'}
            </span>
          </div>

          {/* Spread Readout */}
          <div className="flex items-center justify-between text-xs bg-[#0A0A0A] p-2 rounded border border-[#1A1A1A]">
            <span className="text-[#A3A3A3]">Spread Bps:</span>
            <span className="font-mono text-[#FFFFFF] font-bold">
              {decision.telemetry?.spreadBps?.toFixed(4) || '0.0000'} bps
            </span>
          </div>
        </div>

        {/* Column 3: 3-Tier Risk Guardrail Vetoes & Automated Actions */}
        <div className="bg-[#000000] border border-[#1A1A1A] rounded-lg p-3.5 flex flex-col gap-3">
          <div className="flex items-center justify-between text-xs font-semibold text-[#FFFFFF] border-b border-[#1A1A1A] pb-2">
            <span className="flex items-center gap-1.5">
              <ShieldAlert className="w-3.5 h-3.5 text-rose-400" />
              Risk Guardrail Vetoes & Actions
            </span>
            <span className="text-[10px] font-mono text-[#A3A3A3]">{decision.riskTier}</span>
          </div>

          {/* Execution Status */}
          <div className="flex items-center justify-between text-xs bg-[#0A0A0A] p-2 rounded border border-[#1A1A1A]">
            <span className="text-[#A3A3A3]">Trade Permitted:</span>
            <span className={`font-bold font-mono px-2 py-0.5 rounded text-[11px] ${
              isApproved
                ? 'bg-[#141414] text-emerald-400 border border-emerald-800/40'
                : 'bg-[#141414] text-rose-400 border border-rose-800/40'
            }`}>
              {isApproved ? 'YES [PERMITTED]' : 'NO [VETOED / BLOCKED]'}
            </span>
          </div>

          {/* Active Veto Logs */}
          <div className="flex flex-col gap-1.5 mt-1">
            <div className="text-[10px] font-semibold text-[#A3A3A3] uppercase tracking-wider">
              Veto Explanations ({decision.vetoReasons.length}):
            </div>
            <div className="flex flex-col gap-1 max-h-24 overflow-y-auto pr-1">
              {decision.vetoReasons.length > 0 ? (
                decision.vetoReasons.map((v, idx) => (
                  <div key={idx} className="text-[11px] text-rose-300 bg-[#141414] border border-rose-900/40 p-1.5 rounded flex items-start gap-1.5 leading-snug">
                    <AlertTriangle className="w-3 h-3 text-rose-400 mt-0.5 shrink-0" />
                    <span>{v}</span>
                  </div>
                ))
              ) : (
                <div className="text-[11px] text-emerald-400/90 flex items-center gap-1.5 italic">
                  <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
                  All 6 pre-trade risk guardrails passed cleanly.
                </div>
              )}
            </div>
          </div>

          {/* Automated Hedging / Emergency Orders */}
          {(decision.hedgeOrders.length > 0 || decision.emergencyOrders.length > 0) && (
            <div className="flex flex-col gap-1 border-t border-[#1A1A1A] pt-2">
              <div className="text-[10px] font-semibold text-amber-400 uppercase tracking-wider">
                Automated Safeguard Orders:
              </div>
              {decision.hedgeOrders.map((h, i) => (
                <div key={i} className="text-[10px] font-mono text-[#FFFFFF] bg-[#141414] p-1 rounded border border-[#262626]">
                  [HEDGE] {h.action} {h.quantity} {h.symbol}
                </div>
              ))}
              {decision.emergencyOrders.map((e, i) => (
                <div key={i} className="text-[10px] font-mono text-rose-400 bg-[#141414] p-1 rounded border border-rose-900/40 font-bold">
                  [CRITICAL] {e.orderType}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
