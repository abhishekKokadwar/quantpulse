'use client';

import React from 'react';
import { Zap, X, AlertTriangle, ShieldAlert, TrendingDown, RefreshCw, Flame, Check } from 'lucide-react';

interface CrisisSimulatorModalProps {
  isOpen: boolean;
  onClose: () => void;
  activeScenario: string;
  onSelectScenario: (scenario: string) => void;
}

export const CrisisSimulatorModal: React.FC<CrisisSimulatorModalProps> = ({
  isOpen,
  onClose,
  activeScenario,
  onSelectScenario,
}) => {
  if (!isOpen) return null;

  const scenarios = [
    {
      id: 'normal',
      name: 'Normal Balanced Market (Nominal Regime)',
      description: 'Standard Brownian motion trading with balanced buy/sell flow, tight bid-ask spread, and deep healthy order books.',
      badge: 'TIER 0 NOMINAL',
      badgeColor: 'text-[#A3A3A3] bg-[#141414] border-[#262626]',
      icon: Check,
      iconColor: 'text-emerald-400',
    },
    {
      id: 'toxic_dump',
      name: 'Predatory Toxic Flow (VPIN Surge)',
      description: 'Informed institutional seller dumps aggressively against bids. VPIN surges > 0.85. Watch the Arbiter veto naive dip-buying alpha signals.',
      badge: 'VPIN VETO TRIGGER',
      badgeColor: 'text-amber-400 bg-[#171717] border-amber-500/30',
      icon: Flame,
      iconColor: 'text-amber-400',
    },
    {
      id: 'liquidity_vacuum',
      name: 'Liquidity Vacuum (Depth Evacuation)',
      description: 'Market makers pull 85% of quotes in < 3 seconds. L2 book empties, spread blows out. Watch the Arbiter block executions to prevent slippage.',
      badge: 'SLIPPAGE COLLAR',
      badgeColor: 'text-amber-400 bg-[#171717] border-amber-500/30',
      icon: AlertTriangle,
      iconColor: 'text-amber-400',
    },
    {
      id: 'flash_crash',
      name: 'Flash Crash Collapse (Circuit Breaker)',
      description: 'Cascading price decline, complete depth evacuation, extreme toxicity. Watch Tier 3 Emergency Kill Switch trip and lock out all executions.',
      badge: 'TIER 3 HARD HALT',
      badgeColor: 'text-rose-400 bg-[#171717] border-rose-500/30',
      icon: ShieldAlert,
      iconColor: 'text-rose-400',
    },
    {
      id: 'cointegration_divergence',
      name: 'Stat-Arb Cointegration Breakdown',
      description: 'Correlated pair spread diverges beyond 3.5 standard deviations. Watch Tier 2 emit automated pair liquidation and stop-loss orders.',
      badge: 'TIER 2 AUTO-HEDGE',
      badgeColor: 'text-[#FFFFFF] bg-[#141414] border-[#262626]',
      icon: TrendingDown,
      iconColor: 'text-[#A3A3A3]',
    },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md p-4">
      <div className="w-full max-w-xl bg-[#0A0A0A] border border-[#1A1A1A] rounded-xl shadow-2xl p-6 flex flex-col gap-5 animate-in fade-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[#1A1A1A] pb-4">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-[#141414] border border-[#262626]">
              <Zap className="w-4 h-4 text-[#FFFFFF]" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-[#FFFFFF] tracking-wide uppercase">Live Crisis Injection Sandbox</h3>
              <p className="text-xs text-[#A3A3A3]">Stress-test the Arbiter and observe 3-tier risk safeguards in real time</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg text-[#A3A3A3] hover:text-[#FFFFFF] hover:bg-[#171717] transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Scenarios List */}
        <div className="flex flex-col gap-2.5 max-h-[420px] overflow-y-auto pr-1">
          {scenarios.map((sc) => {
            const isSelected = activeScenario === sc.id;
            const Icon = sc.icon;
            return (
              <div
                key={sc.id}
                onClick={() => {
                  onSelectScenario(sc.id);
                  onClose();
                }}
                className={`p-3.5 rounded-xl border cursor-pointer transition-all flex flex-col gap-1.5 ${
                  isSelected
                    ? 'bg-[#141414] border-[#333333] shadow-md'
                    : 'bg-[#000000] border-[#1A1A1A] hover:border-[#262626] hover:bg-[#0A0A0A]'
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 font-medium text-[#FFFFFF] text-xs">
                    <Icon className={`w-3.5 h-3.5 ${sc.iconColor}`} />
                    <span>{sc.name}</span>
                  </div>
                  <span className={`text-[10px] font-mono px-2 py-0.5 rounded border font-medium ${sc.badgeColor}`}>
                    {sc.badge}
                  </span>
                </div>
                <p className="text-[11px] text-[#A3A3A3] leading-relaxed pl-5.5">
                  {sc.description}
                </p>
              </div>
            );
          })}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-[#1A1A1A] pt-4 text-[11px] text-[#525252]">
          <span>Selecting a scenario immediately mutates streaming order flow.</span>
          <button
            onClick={onClose}
            className="px-3.5 py-1.5 bg-[#171717] hover:bg-[#262626] text-[#FFFFFF] rounded-lg text-xs font-medium border border-[#262626] transition-all"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
