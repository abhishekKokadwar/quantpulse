'use client';

import React from 'react';
import { Play, Pause, RotateCcw, FastForward, SkipForward, SkipBack, Clock, History } from 'lucide-react';

interface ReplayControllerProps {
  isPlaying: boolean;
  onTogglePlay: () => void;
  tickIndex: number;
  totalTicks: number;
  speed: number;
  onSpeedChange: (speed: number) => void;
  onSeek: (tick: number) => void;
  onStep: (delta: number) => void;
  onReset: () => void;
}

export const ReplayController: React.FC<ReplayControllerProps> = ({
  isPlaying,
  onTogglePlay,
  tickIndex,
  totalTicks,
  speed,
  onSpeedChange,
  onSeek,
  onStep,
  onReset,
}) => {
  const speeds = [1, 5, 10, 25, 60];

  // Calculate simulated historical timestamp based on tickIndex
  const baseTime = new Date('2026-03-15T09:30:00Z').getTime();
  const simulatedTime = new Date(baseTime + tickIndex * 800);
  const timeStr = simulatedTime.toLocaleTimeString('en-US', { hour12: false });

  const progressPct = ((tickIndex / Math.max(1, totalTicks)) * 100).toFixed(1);

  return (
    <div className="bg-[#0A0A0A] border border-[#1A1A1A] rounded-xl p-3 shadow-2xl flex flex-col md:flex-row items-center justify-between gap-4">
      {/* Left: Replay Status & Timestamp */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-[#141414] border border-[#262626] text-[#FFFFFF] text-xs font-medium">
          <History className="w-3.5 h-3.5 text-[#A3A3A3]" />
          <span>HISTORICAL REPLAY</span>
        </div>
        <div className="flex items-center gap-1 text-xs text-[#A3A3A3] font-mono">
          <Clock className="w-3.5 h-3.5 text-[#525252]" />
          <span className="text-[#FFFFFF]">{timeStr} UTC</span>
          <span className="text-[#525252]">({progressPct}%)</span>
        </div>
      </div>

      {/* Center: Playback Controls & Scrubber */}
      <div className="flex-1 max-w-xl flex items-center gap-3 w-full">
        {/* Step Back */}
        <button
          onClick={() => onStep(-1)}
          title="Step Backward (1 Tick)"
          className="p-1.5 rounded-lg bg-[#121212] hover:bg-[#1C1C1C] text-[#A3A3A3] hover:text-[#FFFFFF] border border-[#1A1A1A] transition-colors"
        >
          <SkipBack className="w-4 h-4" />
        </button>

        {/* Play / Pause */}
        <button
          onClick={onTogglePlay}
          title={isPlaying ? 'Pause Playback' : 'Start Playback'}
          className={`px-3.5 py-1.5 rounded-lg font-semibold text-xs flex items-center gap-1.5 transition-all shadow-sm ${
            isPlaying
              ? 'bg-[#1F1F1F] hover:bg-[#2B2B2B] text-amber-400 border border-amber-500/30'
              : 'bg-[#FFFFFF] hover:bg-[#E5E5E5] text-[#000000]'
          }`}
        >
          {isPlaying ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5 fill-current" />}
          <span>{isPlaying ? 'PAUSE' : 'PLAY'}</span>
        </button>

        {/* Step Forward */}
        <button
          onClick={() => onStep(1)}
          title="Step Forward (1 Tick)"
          className="p-1.5 rounded-lg bg-[#121212] hover:bg-[#1C1C1C] text-[#A3A3A3] hover:text-[#FFFFFF] border border-[#1A1A1A] transition-colors"
        >
          <SkipForward className="w-4 h-4" />
        </button>

        {/* Timeline Slider */}
        <div className="flex-1 flex items-center gap-2">
          <input
            type="range"
            min={0}
            max={totalTicks}
            value={tickIndex}
            onChange={(e) => onSeek(parseInt(e.target.value, 10))}
            className="w-full h-1.5 bg-[#171717] rounded-lg appearance-none cursor-pointer accent-white"
          />
          <span className="text-[11px] font-mono text-[#A3A3A3] min-w-[58px] text-right">
            {tickIndex}/{totalTicks}
          </span>
        </div>

        {/* Reset */}
        <button
          onClick={onReset}
          title="Reset to Beginning"
          className="p-1.5 rounded-lg bg-[#121212] hover:bg-[#1C1C1C] text-[#525252] hover:text-[#FFFFFF] border border-[#1A1A1A] transition-colors"
        >
          <RotateCcw className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Right: Speed Multiplier Selector */}
      <div className="flex items-center gap-1 bg-[#000000] p-1 rounded-lg border border-[#1A1A1A]">
        <FastForward className="w-3 h-3 text-[#525252] ml-1 mr-0.5" />
        {speeds.map((s) => (
          <button
            key={s}
            onClick={() => onSpeedChange(s)}
            className={`px-2 py-0.5 rounded text-[11px] font-mono transition-colors border ${
              speed === s
                ? 'bg-[#1F1F1F] text-[#FFFFFF] font-bold border-[#2B2B2B]'
                : 'text-[#737373] hover:text-[#FFFFFF] border-transparent hover:bg-[#121212]'
            }`}
          >
            {s}x
          </button>
        ))}
      </div>
    </div>
  );
};
