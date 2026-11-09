'use client';

import React from 'react';
import {
  ShieldAlert,
  ShieldCheck,
  AlertTriangle,
  Zap,
  TrendingDown,
  TrendingUp,
  Lock,
  Unlock,
  DollarSign,
  PieChart,
} from 'lucide-react';

interface RiskHUDProps {
  portfolio: {
    totalEquity: number;
    realizedPnl: number;
    unrealizedPnl: number;
    currentDrawdownPct: number;
    marginMaintenanceRatio: number;
    netDeltaUsd: number;
  };
  riskTier: string;
  killSwitchActive: boolean;
  onTriggerKillSwitch: () => void;
  onOpenUnlockModal: () => void;
  onOpenControlDrawer: () => void;
  onOpenCrisisModal: () => void;
}

export const RiskHUD: React.FC<RiskHUDProps> = ({
  portfolio,
  riskTier,
  killSwitchActive,
  onTriggerKillSwitch,
  onOpenUnlockModal,
  onOpenControlDrawer,
  onOpenCrisisModal,
}) => {
  const totalPnl = portfolio.realizedPnl + portfolio.unrealizedPnl;
  const isPnlPositive = totalPnl >= 0;

  // Margin ratio formatting
  const marginPct = (portfolio.marginMaintenanceRatio * 100).toFixed(0);
  const isMarginCritical = portfolio.marginMaintenanceRatio < 1.30;

  // Tier configuration badges
  const getTierBadge = () => {
    if (killSwitchActive || riskTier === 'TIER_3_KILL_SWITCH') {
      return {
        label: 'TIER 3: EMERGENCY HALT',
        color: 'bg-[#141414] text-rose-400 border-rose-500/40',
        icon: ShieldAlert,
      };
    }
    if (riskTier === 'TIER_2_HEDGING_ACTIVE') {
      return {
        label: 'TIER 2: AUTO-HEDGING ENGAGED',
        color: 'bg-[#141414] text-[#FFFFFF] border-[#333333]',
        icon: Zap,
      };
    }
    if (riskTier === 'TIER_1_THROTTLED') {
      return {
        label: 'TIER 1: SIZING THROTTLED (50%)',
        color: 'bg-[#141414] text-amber-400 border-amber-500/40',
        icon: AlertTriangle,
      };
    }
    return {
      label: 'TIER 0: NOMINAL ACTIVE',
      color: 'bg-[#141414] text-[#A3A3A3] border-[#262626]',
      icon: ShieldCheck,
    };
  };

  const badge = getTierBadge();
  const BadgeIcon = badge.icon;

  return (
    <div className={`p-4 rounded-xl border transition-all shadow-2xl ${
      killSwitchActive
        ? 'bg-[#0A0A0A] border-rose-600/60 shadow-lg'
        : 'bg-[#0A0A0A] border border-[#1A1A1A]'
    }`}>
      <div className="flex flex-wrap items-center justify-between gap-4">
        {/* Left: Portfolio Metrics */}
        <div className="flex flex-wrap items-center gap-6">
          {/* Total Equity */}
          <div>
            <div className="text-[11px] font-medium text-[#A3A3A3] uppercase tracking-wider flex items-center gap-1">
              <DollarSign className="w-3.5 h-3.5 text-[#A3A3A3]" />
              Total Equity
            </div>
            <div className="text-xl font-bold font-mono text-[#FFFFFF] mt-0.5">
              ${portfolio.totalEquity.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </div>
          </div>

          {/* Net PnL */}
          <div className="border-l border-[#1A1A1A] pl-6">
            <div className="text-[11px] font-medium text-[#A3A3A3] uppercase tracking-wider flex items-center gap-1">
              {isPnlPositive ? (
                <TrendingUp className="w-3.5 h-3.5 text-emerald-400" />
              ) : (
                <TrendingDown className="w-3.5 h-3.5 text-rose-400" />
              )}
              Net PnL (Unrealized)
            </div>
            <div className={`text-xl font-bold font-mono mt-0.5 ${
              isPnlPositive ? 'text-emerald-400' : 'text-rose-400'
            }`}>
              {isPnlPositive ? '+' : ''}${totalPnl.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </div>
          </div>

          {/* Intraday Drawdown */}
          <div className="border-l border-[#1A1A1A] pl-6">
            <div className="text-[11px] font-medium text-[#A3A3A3] uppercase tracking-wider">
              Drawdown
            </div>
            <div className={`text-xl font-bold font-mono mt-0.5 ${
              portfolio.currentDrawdownPct > 0.02 ? 'text-amber-400' : 'text-[#FFFFFF]'
            }`}>
              {(portfolio.currentDrawdownPct * 100).toFixed(2)}%
            </div>
          </div>

          {/* Margin Maintenance Ratio */}
          <div className="border-l border-[#1A1A1A] pl-6">
            <div className="text-[11px] font-medium text-[#A3A3A3] uppercase tracking-wider flex items-center gap-1">
              <PieChart className="w-3.5 h-3.5 text-[#A3A3A3]" />
              Margin Health
            </div>
            <div className={`text-xl font-bold font-mono mt-0.5 ${
              isMarginCritical ? 'text-rose-400 animate-pulse' : 'text-[#FFFFFF]'
            }`}>
              {marginPct}%
            </div>
          </div>

          {/* Net Delta Exposure */}
          <div className="border-l border-[#1A1A1A] pl-6">
            <div className="text-[11px] font-medium text-[#A3A3A3] uppercase tracking-wider">
              Net Delta Exposure
            </div>
            <div className="text-xl font-bold font-mono text-[#FFFFFF] mt-0.5">
              ${Math.abs(portfolio.netDeltaUsd).toLocaleString()} <span className="text-xs text-[#525252]">{portfolio.netDeltaUsd >= 0 ? '(LONG)' : '(SHORT)'}</span>
            </div>
          </div>
        </div>

        {/* Right: Risk Badge & Emergency Kill Switch Trigger */}
        <div className="flex items-center gap-2.5">
          {/* Active Risk Tier Badge */}
          <div className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-xs font-mono font-medium ${badge.color}`}>
            <BadgeIcon className="w-3.5 h-3.5" />
            <span>{badge.label}</span>
          </div>

          {/* Crisis Simulator Button */}
          <button
            onClick={onOpenCrisisModal}
            className="px-3 py-1.5 bg-[#121212] hover:bg-[#1C1C1C] text-[#A3A3A3] hover:text-[#FFFFFF] border border-[#262626] rounded-lg text-xs font-medium flex items-center gap-1.5 transition-all"
          >
            <Zap className="w-3.5 h-3.5 text-[#A3A3A3]" />
            <span>Crisis Sim</span>
          </button>

          {/* Risk Control Drawer Button */}
          <button
            onClick={onOpenControlDrawer}
            className="px-3 py-1.5 bg-[#121212] hover:bg-[#1C1C1C] text-[#A3A3A3] hover:text-[#FFFFFF] border border-[#262626] rounded-lg text-xs font-medium transition-all"
          >
            Risk Controls
          </button>

          {/* One-Click Emergency Kill Switch or Unlock */}
          {killSwitchActive ? (
            <button
              onClick={onOpenUnlockModal}
              className="px-3.5 py-1.5 bg-[#FFFFFF] hover:bg-[#E5E5E5] text-[#000000] border border-white/20 rounded-lg text-xs font-semibold uppercase tracking-wider flex items-center gap-1.5 transition-all shadow-sm"
            >
              <Unlock className="w-3.5 h-3.5" />
              <span>Admin Unlock</span>
            </button>
          ) : (
            <button
              onClick={onTriggerKillSwitch}
              className="px-3.5 py-1.5 bg-[#141414] hover:bg-[#1F1414] text-rose-400 border border-rose-500/40 rounded-lg text-xs font-semibold uppercase tracking-wider flex items-center gap-1.5 transition-all shadow-sm"
            >
              <Lock className="w-3.5 h-3.5" />
              <span>Kill Switch</span>
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
