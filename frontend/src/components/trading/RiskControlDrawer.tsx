'use client';

import React from 'react';
import { Sliders, X, RotateCcw, Check, Shield } from 'lucide-react';

export interface RiskConfigState {
  maxSpreadBps: number;
  minDepthUsd: number;
  maxVpinThreshold: number;
  maxDailyDrawdownPct: number;
  maxNetDeltaUsd: number;
  softLossThrottlePct: number;
}

interface RiskControlDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  config: RiskConfigState;
  onChangeConfig: (newConfig: RiskConfigState) => void;
  onResetDefaults: () => void;
}

export const RiskControlDrawer: React.FC<RiskControlDrawerProps> = ({
  isOpen,
  onClose,
  config,
  onChangeConfig,
  onResetDefaults,
}) => {
  if (!isOpen) return null;

  const handleChange = (key: keyof RiskConfigState, value: number) => {
    onChangeConfig({
      ...config,
      [key]: value,
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/80 backdrop-blur-md transition-opacity">
      <div className="w-full max-w-md h-full bg-[#0A0A0A] border-l border-[#1A1A1A] shadow-2xl p-6 flex flex-col gap-6 overflow-y-auto">
        {/* Drawer Header */}
        <div className="flex items-center justify-between border-b border-[#1A1A1A] pb-4">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-[#141414] border border-[#262626]">
              <Sliders className="w-4 h-4 text-[#FFFFFF]" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-[#FFFFFF] uppercase tracking-wide">Risk Parameters Control</h3>
              <p className="text-xs text-[#A3A3A3]">Modify pre-trade collars and threshold limits in real time</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg text-[#A3A3A3] hover:text-[#FFFFFF] hover:bg-[#171717] transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Form Controls */}
        <div className="flex flex-col gap-3.5 flex-1">
          {/* Max Spread Collar (bps) */}
          <div className="bg-[#000000] p-3 rounded-lg border border-[#1A1A1A] flex flex-col gap-2">
            <div className="flex justify-between items-center text-xs">
              <span className="font-medium text-[#FFFFFF]">Max Spread Collar (bps)</span>
              <span className="font-mono text-[#FFFFFF] font-bold">{config.maxSpreadBps.toFixed(1)} bps</span>
            </div>
            <input
              type="range"
              min="5.0"
              max="50.0"
              step="1.0"
              value={config.maxSpreadBps}
              onChange={(e) => handleChange('maxSpreadBps', parseFloat(e.target.value))}
              className="w-full h-1.5 bg-[#171717] rounded-lg appearance-none cursor-pointer accent-white"
            />
            <span className="text-[10px] text-[#A3A3A3]">Rejects market/limit orders when spread exceeds this collar.</span>
          </div>

          {/* Max VPIN Toxicity Ceiling */}
          <div className="bg-[#000000] p-3 rounded-lg border border-[#1A1A1A] flex flex-col gap-2">
            <div className="flex justify-between items-center text-xs">
              <span className="font-medium text-[#FFFFFF]">Max VPIN Toxicity Ceiling</span>
              <span className="font-mono text-[#FFFFFF] font-bold">{config.maxVpinThreshold.toFixed(2)}</span>
            </div>
            <input
              type="range"
              min="0.60"
              max="0.95"
              step="0.01"
              value={config.maxVpinThreshold}
              onChange={(e) => handleChange('maxVpinThreshold', parseFloat(e.target.value))}
              className="w-full h-1.5 bg-[#171717] rounded-lg appearance-none cursor-pointer accent-white"
            />
            <span className="text-[10px] text-[#A3A3A3]">Halts orders when informed order toxicity breaches this ceiling.</span>
          </div>

          {/* Min Top-5 Depth Floor ($) */}
          <div className="bg-[#000000] p-3 rounded-lg border border-[#1A1A1A] flex flex-col gap-2">
            <div className="flex justify-between items-center text-xs">
              <span className="font-medium text-[#FFFFFF]">Min Top-5 Depth Floor ($)</span>
              <span className="font-mono text-[#FFFFFF] font-bold">${config.minDepthUsd.toLocaleString()}</span>
            </div>
            <input
              type="range"
              min="2000"
              max="50000"
              step="1000"
              value={config.minDepthUsd}
              onChange={(e) => handleChange('minDepthUsd', parseFloat(e.target.value))}
              className="w-full h-1.5 bg-[#171717] rounded-lg appearance-none cursor-pointer accent-white"
            />
            <span className="text-[10px] text-[#A3A3A3]">Rejects trades if aggregate top-5 book depth is thinner than this floor.</span>
          </div>

          {/* Max Daily Drawdown (%) */}
          <div className="bg-[#000000] p-3 rounded-lg border border-[#1A1A1A] flex flex-col gap-2">
            <div className="flex justify-between items-center text-xs">
              <span className="font-medium text-[#FFFFFF]">Tier 3 Drawdown Circuit Breaker</span>
              <span className="font-mono text-[#FFFFFF] font-bold">{(config.maxDailyDrawdownPct * 100).toFixed(1)}%</span>
            </div>
            <input
              type="range"
              min="0.01"
              max="0.10"
              step="0.005"
              value={config.maxDailyDrawdownPct}
              onChange={(e) => handleChange('maxDailyDrawdownPct', parseFloat(e.target.value))}
              className="w-full h-1.5 bg-[#171717] rounded-lg appearance-none cursor-pointer accent-white"
            />
            <span className="text-[10px] text-[#A3A3A3]">Triggers emergency kill switch if intraday drawdown reaches this level.</span>
          </div>

          {/* Max Net Delta Exposure ($) */}
          <div className="bg-[#000000] p-3 rounded-lg border border-[#1A1A1A] flex flex-col gap-2">
            <div className="flex justify-between items-center text-xs">
              <span className="font-medium text-[#FFFFFF]">Tier 2 Net Delta Cap ($)</span>
              <span className="font-mono text-[#FFFFFF] font-bold">${config.maxNetDeltaUsd.toLocaleString()}</span>
            </div>
            <input
              type="range"
              min="25000"
              max="250000"
              step="5000"
              value={config.maxNetDeltaUsd}
              onChange={(e) => handleChange('maxNetDeltaUsd', parseFloat(e.target.value))}
              className="w-full h-1.5 bg-[#171717] rounded-lg appearance-none cursor-pointer accent-white"
            />
            <span className="text-[10px] text-[#A3A3A3]">Emits automated delta-neutral hedge orders when net directional exposure exceeds this cap.</span>
          </div>

          {/* Tier 1 Sizing Throttle Budget Ratio */}
          <div className="bg-[#000000] p-3 rounded-lg border border-[#1A1A1A] flex flex-col gap-2">
            <div className="flex justify-between items-center text-xs">
              <span className="font-medium text-[#FFFFFF]">Tier 1 Sizing Cut Trigger</span>
              <span className="font-mono text-[#FFFFFF] font-bold">{(config.softLossThrottlePct * 100).toFixed(0)}% of Budget</span>
            </div>
            <input
              type="range"
              min="0.20"
              max="0.80"
              step="0.05"
              value={config.softLossThrottlePct}
              onChange={(e) => handleChange('softLossThrottlePct', parseFloat(e.target.value))}
              className="w-full h-1.5 bg-[#171717] rounded-lg appearance-none cursor-pointer accent-white"
            />
            <span className="text-[10px] text-[#A3A3A3]">Automatically halves maximum child order size when daily loss reaches this budget fraction.</span>
          </div>
        </div>

        {/* Footer Actions */}
        <div className="flex items-center justify-between border-t border-[#1A1A1A] pt-4">
          <button
            onClick={onResetDefaults}
            className="flex items-center gap-1.5 px-3 py-2 bg-[#121212] hover:bg-[#1C1C1C] text-[#A3A3A3] hover:text-[#FFFFFF] border border-[#1A1A1A] rounded-lg text-xs font-medium transition-all"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span>Reset Defaults</span>
          </button>

          <button
            onClick={onClose}
            className="flex items-center gap-1.5 px-4 py-2 bg-[#FFFFFF] hover:bg-[#E5E5E5] text-[#000000] rounded-lg text-xs font-semibold transition-all shadow-sm"
          >
            <Check className="w-4 h-4" />
            <span>Apply to Engine</span>
          </button>
        </div>
      </div>
    </div>
  );
};
