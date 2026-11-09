'use client';

import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Activity,
  Layers,
  ShieldAlert,
  Zap,
  DollarSign,
  TrendingUp,
  TrendingDown,
  RefreshCw,
  PlusCircle,
  Sliders,
  Lock,
  Unlock,
  Radio,
  Clock,
  Compass,
  History,
  Flame,
  CheckCircle2,
  AlertTriangle,
} from 'lucide-react';

import { DOMLadderCanvas } from '@/components/trading/DOMLadderCanvas';
import { TradingViewChart } from '@/components/trading/TradingViewChart';
import { RiskHUD } from '@/components/trading/RiskHUD';
import { DecisionExplainer } from '@/components/trading/DecisionExplainer';
import { RiskControlDrawer, RiskConfigState } from '@/components/trading/RiskControlDrawer';
import { CrisisSimulatorModal } from '@/components/trading/CrisisSimulatorModal';
import { AdminUnlockModal } from '@/components/trading/AdminUnlockModal';
import { ManualOrderModal } from '@/components/trading/ManualOrderModal';
import { ReplayController } from '@/components/trading/ReplayController';

const DEFAULT_RISK_CONFIG: RiskConfigState = {
  maxSpreadBps: 25.0,
  minDepthUsd: 5000.0,
  maxVpinThreshold: 0.85,
  maxDailyDrawdownPct: 0.03, // 3.0% max drawdown
  maxNetDeltaUsd: 100000.0,
  softLossThrottlePct: 0.50,
};

const SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'NVDA', 'AAPL', 'SPY', 'EUR/USD'];

export default function QuantPulseTerminalPage() {
  // Master Operating Mode: LIVE (Binance), REPLAY (Historical Tape), or CRISIS (Synthetic Stress Engine)
  const [feedMode, setFeedMode] = useState<'live' | 'replay' | 'crisis'>('live');

  // Master Instrument & Scenario State
  const [selectedSymbol, setSelectedSymbol] = useState('BTC/USDT');
  const [activeScenario, setActiveScenario] = useState('normal');

  // Replay Mode State
  const [replayTickIndex, setReplayTickIndex] = useState(120);
  const [isReplayPlaying, setIsReplayPlaying] = useState(false);
  const [replaySpeed, setReplaySpeed] = useState(5);

  // Risk Parameters & Portfolio State
  const [riskConfig, setRiskConfig] = useState<RiskConfigState>(DEFAULT_RISK_CONFIG);
  const [portfolio, setPortfolio] = useState({
    totalEquity: 1000000.0,
    realizedPnl: 0.0,
    unrealizedPnl: 14280.0,
    currentDrawdownPct: 0.004,
    marginMaintenanceRatio: 3.42,
    netDeltaUsd: 38500.0,
  });

  const [killSwitchActive, setKillSwitchActive] = useState(false);

  // Market & Decision Telemetry
  const [marketData, setMarketData] = useState<any>(null);
  const [decision, setDecision] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [lastTickTime, setLastTickTime] = useState<string>('');

  // Modals & Drawers
  const [isRiskControlOpen, setIsRiskControlOpen] = useState(false);
  const [isCrisisModalOpen, setIsCrisisModalOpen] = useState(false);
  const [isAdminUnlockOpen, setIsAdminUnlockOpen] = useState(false);
  const [isManualOrderOpen, setIsManualOrderOpen] = useState(false);

  // Fetch Market Data & Evaluate Decision Arbiter
  const fetchMarketAndEvaluate = useCallback(async () => {
    try {
      // 1. Fetch live market stream snapshot based on active mode
      const queryParams = new URLSearchParams({
        symbol: selectedSymbol,
        mode: feedMode,
        scenario: activeScenario,
        tickIndex: replayTickIndex.toString(),
      });

      const mktRes = await fetch(`/api/quant/market?${queryParams.toString()}`);
      const mktJson = await mktRes.json();
      setMarketData(mktJson);
      setLastTickTime(new Date().toLocaleTimeString());

      // 2. Query Decision Arbiter with live microstructure telemetry
      const bidDepth = mktJson.orderBook?.totalBidDepthUsd || 1;
      const askDepth = mktJson.orderBook?.totalAskDepthUsd || 1;
      const computedOfi = (bidDepth - askDepth) / (bidDepth + askDepth);

      const decRes = await fetch('/api/quant/decision', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol: selectedSymbol,
          price: mktJson.price,
          scenario: activeScenario,
          mode: feedMode,
          liveTelemetry: {
            spreadBps: mktJson.spreadBps,
            microPrice: mktJson.microPrice,
            ofi: computedOfi,
            vpin: feedMode === 'live' ? 0.35 : undefined,
          },
          config: riskConfig,
          portfolioState: portfolio,
          customKillSwitchActive: killSwitchActive,
        }),
      });
      const decJson = await decRes.json();
      setDecision(decJson);

      // Auto-trip kill switch if decision triggered Tier 3
      if (decJson.killSwitchActive && !killSwitchActive) {
        setKillSwitchActive(true);
      }
    } catch (err) {
      console.error('Error fetching market or decision telemetry:', err);
    } finally {
      setIsLoading(false);
    }
  }, [selectedSymbol, feedMode, activeScenario, replayTickIndex, riskConfig, portfolio, killSwitchActive]);

  // Periodic real-time poll (1.5 seconds) for LIVE and CRISIS modes
  useEffect(() => {
    fetchMarketAndEvaluate();
    const interval = setInterval(() => {
      if (feedMode !== 'replay' || isReplayPlaying) {
        fetchMarketAndEvaluate();
      }
    }, 1500);
    return () => clearInterval(interval);
  }, [fetchMarketAndEvaluate, feedMode, isReplayPlaying]);

  // Replay timeline automatic advancement timer
  useEffect(() => {
    if (feedMode !== 'replay' || !isReplayPlaying) return;

    const interval = setInterval(() => {
      setReplayTickIndex((prev) => (prev + replaySpeed >= 1500 ? 0 : prev + replaySpeed));
    }, 800);

    return () => clearInterval(interval);
  }, [feedMode, isReplayPlaying, replaySpeed]);

  // Handlers
  const handleTriggerKillSwitch = () => {
    setKillSwitchActive(true);
    if (decision) {
      setDecision({
        ...decision,
        killSwitchActive: true,
        riskTier: 'TIER_3_KILL_SWITCH',
        riskState: 'EMERGENCY_HALT',
        action: 'HOLD',
        tradePermitted: false,
        sizeMultiplier: 0.0,
      });
    }
  };

  const handleAdminUnlock = (token: string): boolean => {
    if (token === 'QUANT_PULSE_SECURE_TOKEN_2026') {
      setKillSwitchActive(false);
      setActiveScenario('normal');
      setPortfolio((prev) => ({
        ...prev,
        currentDrawdownPct: 0.005,
        marginMaintenanceRatio: 2.8,
      }));
      return true;
    }
    return false;
  };

  const handleExecuteFill = (order: { symbol: string; side: 'BUY' | 'SELL'; quantity: number; price: number }) => {
    const notional = order.quantity * order.price;
    const deltaChange = order.side === 'BUY' ? notional : -notional;

    setPortfolio((prev) => ({
      ...prev,
      netDeltaUsd: prev.netDeltaUsd + deltaChange,
      unrealizedPnl: prev.unrealizedPnl + (order.side === 'BUY' ? +250 : -250),
    }));

    fetchMarketAndEvaluate();
  };

  if (isLoading || !marketData) {
    return (
      <div className="flex h-screen w-full items-center justify-center bg-[#000000] text-[#A3A3A3]">
        <div className="flex flex-col items-center gap-3">
          <RefreshCw className="w-6 h-6 text-[#FFFFFF] animate-spin" />
          <span className="text-xs font-semibold tracking-widest uppercase font-mono text-[#737373]">
            Initializing QuantPulse Terminal...
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col min-h-screen bg-[#000000] text-[#FFFFFF] font-sans selection:bg-[#262626] selection:text-[#FFFFFF]">
      {/* ========================================================================= */}
      {/* 1. Global Navigation & Tri-Mode Architecture Status Bar                    */}
      {/* ========================================================================= */}
      <header className="sticky top-0 z-40 bg-[#0A0A0A]/95 backdrop-blur-md border-b border-[#1A1A1A] px-4 py-2.5 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-5">
          {/* Logo & Platform Name */}
          <div className="flex items-center gap-2.5">
            <div className="p-1.5 rounded-lg bg-[#121212] border border-[#1A1A1A]">
              <Activity className="w-4 h-4 text-[#FFFFFF]" />
            </div>
            <div>
              <div className="text-sm font-extrabold tracking-tight uppercase flex items-center gap-1.5">
                <span className="text-[#FFFFFF]">Quant</span>
                <span className="text-[#A3A3A3]">Pulse</span>
                <span className="text-[10px] font-mono font-medium px-1.5 py-0.2 rounded bg-[#141414] text-[#A3A3A3] border border-[#262626]">
                  v2.0 PRO
                </span>
              </div>
              <div className="text-[10px] text-[#525252] font-mono flex items-center gap-1">
                <span>HFT Microstructure Lakehouse</span>
              </div>
            </div>
          </div>

          {/* Tri-Mode Architecture Segmented Switcher */}
          <div className="flex items-center bg-[#000000] p-1 rounded-xl border border-[#1A1A1A]">
            {/* Mode 1: LIVE */}
            <button
              onClick={() => {
                setFeedMode('live');
                setActiveScenario('normal');
                setIsReplayPlaying(false);
              }}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono font-semibold transition-all border ${
                feedMode === 'live'
                  ? 'bg-[#1F1F1F] text-[#FFFFFF] border-[#2B2B2B] shadow-sm'
                  : 'text-[#737373] hover:text-[#FFFFFF] border-transparent hover:bg-[#121212]'
              }`}
            >
              <span className={`w-1.5 h-1.5 rounded-full ${feedMode === 'live' ? 'bg-emerald-400 animate-pulse' : 'bg-[#525252]'}`} />
              <span>LIVE</span>
              <span className="text-[9px] uppercase px-1 rounded bg-[#141414] text-[#737373] border border-[#1F1F1F]">
                Binance
              </span>
            </button>

            {/* Mode 2: REPLAY */}
            <button
              onClick={() => {
                setFeedMode('replay');
                setActiveScenario('normal');
              }}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono font-semibold transition-all border ${
                feedMode === 'replay'
                  ? 'bg-[#1F1F1F] text-[#FFFFFF] border-[#2B2B2B] shadow-sm'
                  : 'text-[#737373] hover:text-[#FFFFFF] border-transparent hover:bg-[#121212]'
              }`}
            >
              <History className="w-3.5 h-3.5" />
              <span>REPLAY</span>
              <span className="text-[9px] uppercase px-1 rounded bg-[#141414] text-[#737373] border border-[#1F1F1F]">
                Tape
              </span>
            </button>

            {/* Mode 3: CRISIS SIM */}
            <button
              onClick={() => {
                setFeedMode('crisis');
                setIsCrisisModalOpen(true);
                setIsReplayPlaying(false);
              }}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono font-semibold transition-all border ${
                feedMode === 'crisis'
                  ? 'bg-[#1F1F1F] text-[#FFFFFF] border-[#2B2B2B] shadow-sm'
                  : 'text-[#737373] hover:text-[#FFFFFF] border-transparent hover:bg-[#121212]'
              }`}
            >
              <span className={`w-1.5 h-1.5 rounded-full ${feedMode === 'crisis' ? 'bg-amber-400' : 'bg-[#525252]'}`} />
              <span>CRISIS SIM</span>
              <span className="text-[9px] uppercase px-1 rounded bg-[#141414] text-[#737373] border border-[#1F1F1F]">
                Sandbox
              </span>
            </button>
          </div>

          {/* Instrument Selector Pill */}
          <div className="hidden md:flex items-center gap-1 bg-[#000000] p-1 rounded-lg border border-[#1A1A1A] overflow-x-auto">
            {SYMBOLS.map((sym) => (
              <button
                key={sym}
                onClick={() => setSelectedSymbol(sym)}
                className={`px-2.5 py-1 rounded text-xs font-mono font-medium transition-all border ${
                  selectedSymbol === sym
                    ? 'bg-[#1A1A1A] text-[#FFFFFF] border-[#2B2B2B] shadow-sm'
                    : 'text-[#737373] hover:text-[#FFFFFF] border-transparent hover:bg-[#121212]'
                }`}
              >
                {sym}
              </button>
            ))}
          </div>
        </div>

        {/* Right Status Badges & Quick Action Buttons */}
        <div className="flex items-center gap-2.5">
          {/* Active Data Provenance Badge */}
          <div className="hidden sm:flex items-center gap-2 px-3 py-1.5 bg-[#000000] border border-[#1A1A1A] rounded-lg text-xs font-mono">
            {feedMode === 'live' && (
              <span className="text-[#FFFFFF] flex items-center gap-1.5 font-medium">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                <span>{marketData?.metadata?.source || 'Binance Stream (Live)'}</span>
                <span className="text-[#525252]">({marketData?.metadata?.latencyMs || 42}ms)</span>
              </span>
            )}
            {feedMode === 'replay' && (
              <span className="text-[#FFFFFF] flex items-center gap-1.5 font-medium">
                <History className="w-3.5 h-3.5 text-[#A3A3A3]" />
                <span>Historical Replay ({replaySpeed}x)</span>
                <span className="text-[#525252]">[{replayTickIndex}/1500]</span>
              </span>
            )}
            {feedMode === 'crisis' && (
              <span className="text-amber-400 flex items-center gap-1.5 font-medium">
                <Flame className="w-3.5 h-3.5 text-amber-400" />
                <span>Stress Sandbox: {activeScenario.toUpperCase()}</span>
              </span>
            )}
          </div>

          {/* Manual Order Trigger */}
          <button
            onClick={() => setIsManualOrderOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-[#FFFFFF] hover:bg-[#E5E5E5] text-[#000000] font-semibold text-xs rounded-lg transition-all shadow-sm border border-white/20"
          >
            <PlusCircle className="w-3.5 h-3.5" />
            <span>New Order</span>
          </button>

          {/* Last Tick Timestamp */}
          <div className="text-[11px] font-mono text-[#A3A3A3] flex items-center gap-1 bg-[#000000] px-2.5 py-1.5 rounded border border-[#1A1A1A]">
            <Clock className="w-3 h-3 text-[#525252]" />
            <span>{lastTickTime}</span>
          </div>
        </div>
      </header>

      {/* ========================================================================= */}
      {/* 2. Main Terminal Content Layout                                           */}
      {/* ========================================================================= */}
      <main className="flex-1 p-4 flex flex-col gap-4 max-w-[1920px] mx-auto w-full">
        {/* REPLAY CONTROLLER: Shown exclusively in REPLAY Mode */}
        {feedMode === 'replay' && (
          <ReplayController
            isPlaying={isReplayPlaying}
            onTogglePlay={() => setIsReplayPlaying(!isReplayPlaying)}
            tickIndex={replayTickIndex}
            totalTicks={1500}
            speed={replaySpeed}
            onSpeedChange={(spd) => setReplaySpeed(spd)}
            onSeek={(tick) => setReplayTickIndex(tick)}
            onStep={(delta) => setReplayTickIndex((prev) => Math.max(0, Math.min(1500, prev + delta)))}
            onReset={() => {
              setReplayTickIndex(0);
              setIsReplayPlaying(false);
            }}
          />
        )}

        {/* CRISIS SIMULATION CONTEXT BANNER: Shown in CRISIS Mode */}
        {feedMode === 'crisis' && (
          <div className="bg-[#0A0A0A] border border-[#1A1A1A] border-l-2 border-l-amber-500 rounded-xl p-3.5 flex flex-col md:flex-row items-center justify-between gap-3 shadow-lg">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-[#141414] border border-[#262626] text-amber-400">
                <AlertTriangle className="w-4 h-4" />
              </div>
              <div>
                <div className="text-xs font-semibold text-[#FFFFFF] flex items-center gap-2">
                  <span>CRISIS & STRESS TESTING SANDBOX</span>
                  <span className="text-[10px] px-1.5 py-0.2 rounded bg-[#171717] text-amber-400 font-mono border border-[#2B2B2B]">
                    Active: {activeScenario.toUpperCase()}
                  </span>
                </div>
                <div className="text-[11px] text-[#A3A3A3] mt-0.5">
                  Simulating extreme microstructure conditions (VPIN surge, liquidity vacuum, flash crashes) to verify that the Decision Arbiter properly enforces vetoes and circuit breakers.
                </div>
              </div>
            </div>

            <div className="flex items-center gap-2 shrink-0">
              <button
                onClick={() => setIsCrisisModalOpen(true)}
                className="px-3 py-1.5 bg-[#171717] hover:bg-[#262626] text-[#FFFFFF] font-medium text-xs rounded-lg transition-all border border-[#2B2B2B] flex items-center gap-1.5"
              >
                <Flame className="w-3.5 h-3.5 text-amber-400" />
                <span>Change Scenario</span>
              </button>
              <button
                onClick={() => {
                  setActiveScenario('normal');
                  setFeedMode('live');
                }}
                className="px-2.5 py-1.5 bg-[#121212] hover:bg-[#1C1C1C] text-[#A3A3A3] hover:text-[#FFFFFF] text-xs rounded-lg transition-all font-mono border border-[#1A1A1A]"
              >
                Return to Live
              </button>
            </div>
          </div>
        )}

        {/* Tier 1 / Risk HUD Banner */}
        <RiskHUD
          portfolio={portfolio}
          riskTier={decision?.riskTier || 'TIER_0_NORMAL'}
          killSwitchActive={killSwitchActive}
          onTriggerKillSwitch={handleTriggerKillSwitch}
          onOpenUnlockModal={() => setIsAdminUnlockOpen(true)}
          onOpenControlDrawer={() => setIsRiskControlOpen(true)}
          onOpenCrisisModal={() => setIsCrisisModalOpen(true)}
        />

        {/* Primary Interactive Trading View: Candlestick Chart + DOM Ladder */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-stretch">
          {/* Left: TradingView Candlestick Chart with Rolling VWAP & AI Confidence Ribbons (8 cols) */}
          <div className="lg:col-span-8 flex flex-col h-[520px]">
            <TradingViewChart
              candles={marketData.candles || []}
              forecastRibbon={marketData.forecastRibbon || []}
              symbol={selectedSymbol}
            />
          </div>

          {/* Right: 60 FPS HTML5 Canvas DOM Ladder (4 cols) */}
          <div className="lg:col-span-4 flex flex-col h-[520px]">
            <DOMLadderCanvas
              bids={marketData.orderBook?.bids || []}
              asks={marketData.orderBook?.asks || []}
              bestBid={marketData.bestBid || 0}
              bestAsk={marketData.bestAsk || 0}
              spreadBps={marketData.spreadBps || 0}
              microPrice={marketData.microPrice || 0}
              symbol={selectedSymbol}
              onPriceSelect={(px) => setIsManualOrderOpen(true)}
            />
          </div>
        </div>

        {/* Decision Explainability & Transparency Matrix */}
        {decision && (
          <DecisionExplainer decision={decision} />
        )}

        {/* Bottom Recent Executions & Trade Stream Table */}
        <div className="bg-[#0A0A0A] border border-[#1A1A1A] rounded-xl p-4 shadow-2xl">
          <div className="flex items-center justify-between pb-3 border-b border-[#1A1A1A]">
            <div className="flex items-center gap-2">
              <Radio className="w-3.5 h-3.5 text-[#A3A3A3]" />
              <h3 className="text-xs font-semibold text-[#FFFFFF] uppercase tracking-wider">
                {feedMode === 'live' ? 'Live Binance High-Frequency Trade Stream' : feedMode === 'replay' ? 'Historical Replay Execution Stream' : 'Stress Simulator Trade Stream'}
              </h3>
            </div>
            <span className="text-[10px] font-mono text-[#A3A3A3]">
              Showing last 15 trade fills across book
            </span>
          </div>

          <div className="overflow-x-auto mt-2">
            <table className="w-full text-left text-xs font-mono">
              <thead>
                <tr className="text-[#A3A3A3] border-b border-[#1A1A1A] text-[10px] uppercase">
                  <th className="py-2 px-3">Trade ID</th>
                  <th className="py-2 px-3">Timestamp</th>
                  <th className="py-2 px-3">Side</th>
                  <th className="py-2 px-3 text-right">Price</th>
                  <th className="py-2 px-3 text-right">Size</th>
                  <th className="py-2 px-3 text-right">Total USD</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#1A1A1A]">
                {(marketData.recentTrades || []).map((t: any) => {
                  const totalUsd = t.price * t.size;
                  return (
                    <tr key={t.id} className="hover:bg-[#121212] transition-colors">
                      <td className="py-1.5 px-3 text-[#A3A3A3]">{t.id}</td>
                      <td className="py-1.5 px-3 text-[#A3A3A3]">{new Date(t.time).toLocaleTimeString()}</td>
                      <td className="py-1.5 px-3">
                        <span
                          className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                            t.side === 'BUY'
                              ? 'bg-emerald-950 text-emerald-400'
                              : 'bg-rose-950 text-rose-400'
                          }`}
                        >
                          {t.side}
                        </span>
                      </td>
                      <td
                        className={`py-1.5 px-3 text-right font-bold ${
                          t.side === 'BUY' ? 'text-emerald-400' : 'text-rose-400'
                        }`}
                      >
                        ${t.price.toFixed(2)}
                      </td>
                      <td className="py-1.5 px-3 text-right text-[#FFFFFF]">{t.size.toFixed(4)}</td>
                      <td className="py-1.5 px-3 text-right text-[#A3A3A3]">
                        ${totalUsd.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </main>

      {/* ========================================================================= */}
      {/* 3. Interactive Modals & Drawers                                            */}
      {/* ========================================================================= */}
      <RiskControlDrawer
        isOpen={isRiskControlOpen}
        onClose={() => setIsRiskControlOpen(false)}
        config={riskConfig}
        onChangeConfig={(newCfg) => {
          setRiskConfig(newCfg);
          fetchMarketAndEvaluate();
        }}
        onResetDefaults={() => {
          setRiskConfig(DEFAULT_RISK_CONFIG);
          fetchMarketAndEvaluate();
        }}
      />

      <CrisisSimulatorModal
        isOpen={isCrisisModalOpen}
        onClose={() => setIsCrisisModalOpen(false)}
        activeScenario={activeScenario}
        onSelectScenario={(sc) => {
          setActiveScenario(sc);
          if (sc !== 'normal') {
            setFeedMode('crisis');
          }
          fetchMarketAndEvaluate();
        }}
      />

      <AdminUnlockModal
        isOpen={isAdminUnlockOpen}
        onClose={() => setIsAdminUnlockOpen(false)}
        onUnlock={handleAdminUnlock}
      />

      <ManualOrderModal
        isOpen={isManualOrderOpen}
        onClose={() => setIsManualOrderOpen(false)}
        symbol={selectedSymbol}
        currentPrice={marketData?.price || 64000.0}
        onExecuteFill={handleExecuteFill}
        isKillSwitchActive={killSwitchActive}
      />
    </div>
  );
}
