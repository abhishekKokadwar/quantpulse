'use client';

import React, { useEffect, useRef, useState } from 'react';
import {
  createChart,
  IChartApi,
  ISeriesApi,
  CandlestickData,
  LineData,
  Time,
  CandlestickSeries,
  LineSeries,
} from 'lightweight-charts';
import { TrendingUp, Layers, Activity } from 'lucide-react';

interface ChartProps {
  candles: {
    time: number;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
    vwap: number;
  }[];
  forecastRibbon?: {
    time: number;
    meanPrice: number;
    upperConfidence: number;
    lowerConfidence: number;
  }[];
  symbol: string;
  onTimeframeChange?: (tf: string) => void;
}

export const TradingViewChart: React.FC<ChartProps> = ({
  candles,
  forecastRibbon,
  symbol,
  onTimeframeChange,
}) => {
  const chartContainerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const vwapSeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
  const upperRibbonRef = useRef<ISeriesApi<'Line'> | null>(null);
  const lowerRibbonRef = useRef<ISeriesApi<'Line'> | null>(null);
  const meanRibbonRef = useRef<ISeriesApi<'Line'> | null>(null);

  const [activeTimeframe, setActiveTimeframe] = useState<'1s' | '1m' | '5m'>('1m');
  const [showVwap, setShowVwap] = useState(true);
  const [showAiRibbon, setShowAiRibbon] = useState(true);

  // Initialize Lightweight Charts
  useEffect(() => {
    if (!chartContainerRef.current) return;

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { color: '#000000' },
        textColor: '#A3A3A3',
        fontSize: 11,
        fontFamily: "'Inter', sans-serif",
      },
      grid: {
        vertLines: { color: 'rgba(255, 255, 255, 0.03)' },
        horzLines: { color: 'rgba(255, 255, 255, 0.03)' },
      },
      crosshair: {
        mode: 1, // Magnet mode
        vertLine: {
          color: 'rgba(255, 255, 255, 0.25)',
          width: 1,
          style: 3,
        },
        horzLine: {
          color: 'rgba(255, 255, 255, 0.25)',
          width: 1,
          style: 3,
        },
      },
      rightPriceScale: {
        borderColor: '#1A1A1A',
        scaleMargins: {
          top: 0.1,
          bottom: 0.2,
        },
      },
      timeScale: {
        borderColor: '#1A1A1A',
        timeVisible: true,
        secondsVisible: true,
      },
    });

    chartRef.current = chart;

    // 1. Candlestick Series
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#10B981',
      downColor: '#EF4444',
      borderVisible: false,
      wickUpColor: '#10B981',
      wickDownColor: '#EF4444',
    });
    candleSeriesRef.current = candleSeries;

    // 2. Rolling VWAP Line Series (Golden Accent)
    const vwapSeries = chart.addSeries(LineSeries, {
      color: '#F59E0B',
      lineWidth: 2,
      priceLineVisible: false,
      title: 'VWAP',
    });
    vwapSeriesRef.current = vwapSeries;

    // 3. AI Forecaster Confidence Ribbon (Purple / Cyan)
    const upperRibbon = chart.addSeries(LineSeries, {
      color: 'rgba(168, 85, 247, 0.5)',
      lineWidth: 1,
      lineStyle: 2, // Dashed
      priceLineVisible: false,
      title: 'AI Upper Conf',
    });
    const lowerRibbon = chart.addSeries(LineSeries, {
      color: 'rgba(168, 85, 247, 0.5)',
      lineWidth: 1,
      lineStyle: 2,
      priceLineVisible: false,
      title: 'AI Lower Conf',
    });
    const meanRibbon = chart.addSeries(LineSeries, {
      color: '#A855F7',
      lineWidth: 2,
      priceLineVisible: false,
      title: 'AI Trajectory',
    });

    upperRibbonRef.current = upperRibbon;
    lowerRibbonRef.current = lowerRibbon;
    meanRibbonRef.current = meanRibbon;

    // Resize Observer
    const resizeObserver = new ResizeObserver((entries) => {
      if (entries.length === 0 || !entries[0].contentRect) return;
      const { width, height } = entries[0].contentRect;
      chart.applyOptions({ width, height });
    });
    resizeObserver.observe(chartContainerRef.current);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
    };
  }, []);

  // Update Data
  useEffect(() => {
    if (!candleSeriesRef.current || !candles.length) return;

    // Format candles for lightweight-charts
    const sortedCandles = [...candles].sort((a, b) => a.time - b.time);
    const cData: CandlestickData<Time>[] = sortedCandles.map((c) => ({
      time: c.time as Time,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }));
    candleSeriesRef.current.setData(cData);

    // Update VWAP
    if (vwapSeriesRef.current && showVwap) {
      const vData: LineData<Time>[] = sortedCandles.map((c) => ({
        time: c.time as Time,
        value: c.vwap,
      }));
      vwapSeriesRef.current.setData(vData);
    }

    // Update AI Forecast Ribbon
    if (forecastRibbon && forecastRibbon.length > 0 && showAiRibbon) {
      const lastCandle = sortedCandles[sortedCandles.length - 1];
      const anchorPoint = {
        time: lastCandle.time as Time,
        value: lastCandle.close,
      };

      if (meanRibbonRef.current && upperRibbonRef.current && lowerRibbonRef.current) {
        meanRibbonRef.current.setData([
          anchorPoint,
          ...forecastRibbon.map((f) => ({ time: f.time as Time, value: f.meanPrice })),
        ]);
        upperRibbonRef.current.setData([
          anchorPoint,
          ...forecastRibbon.map((f) => ({ time: f.time as Time, value: f.upperConfidence })),
        ]);
        lowerRibbonRef.current.setData([
          anchorPoint,
          ...forecastRibbon.map((f) => ({ time: f.time as Time, value: f.lowerConfidence })),
        ]);
      }
    }
  }, [candles, forecastRibbon, showVwap, showAiRibbon]);

  const handleTfClick = (tf: '1s' | '1m' | '5m') => {
    setActiveTimeframe(tf);
    if (onTimeframeChange) onTimeframeChange(tf);
  };

  return (
    <div className="flex flex-col h-full bg-[#0A0A0A] border border-[#1A1A1A] rounded-xl overflow-hidden shadow-2xl">
      {/* Top Header Controls */}
      <div className="flex items-center justify-between px-3 py-2 bg-[#000000] border-b border-[#1A1A1A]">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-[#A3A3A3]" />
            <span className="text-xs font-semibold text-[#FFFFFF]">
              TradingView Canvas Terminal
            </span>
          </div>

          {/* Timeframe Buttons */}
          <div className="flex items-center bg-[#050505] rounded-lg p-0.5 border border-[#1A1A1A]">
            {(['1s', '1m', '5m'] as const).map((tf) => (
              <button
                key={tf}
                onClick={() => handleTfClick(tf)}
                className={`px-2.5 py-0.5 text-[11px] font-mono font-medium rounded transition-all border ${
                  activeTimeframe === tf
                    ? 'bg-[#1F1F1F] text-[#FFFFFF] border-[#2B2B2B] shadow-sm'
                    : 'text-[#737373] hover:text-[#FFFFFF] border-transparent'
                }`}
              >
                {tf}
              </button>
            ))}
          </div>
        </div>

        {/* Indicator Toggles */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowVwap(!showVwap)}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-[11px] font-medium border transition-all ${
              showVwap
                ? 'bg-[#141414] text-amber-400 border-amber-500/30'
                : 'bg-[#0A0A0A] text-[#525252] border-[#1A1A1A] hover:text-[#A3A3A3]'
            }`}
          >
            <Activity className="w-3 h-3" />
            <span>VWAP</span>
          </button>

          <button
            onClick={() => setShowAiRibbon(!showAiRibbon)}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-[11px] font-medium border transition-all ${
              showAiRibbon
                ? 'bg-[#141414] text-[#FFFFFF] border-[#333333]'
                : 'bg-[#0A0A0A] text-[#525252] border-[#1A1A1A] hover:text-[#A3A3A3]'
            }`}
          >
            <Layers className="w-3 h-3" />
            <span>AI Ribbon</span>
          </button>
        </div>
      </div>

      {/* Chart Canvas Area */}
      <div ref={chartContainerRef} className="relative flex-1 w-full min-h-[460px]" />

      {/* Footer Legend */}
      <div className="flex items-center justify-between px-3 py-1.5 bg-[#000000] border-t border-[#1A1A1A] text-[10px] text-[#A3A3A3]">
        <div className="flex items-center gap-4">
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-amber-400" />
            Rolling Microstructure VWAP
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-purple-400" />
            AI Forecaster Trajectory Cone (95% CI)
          </span>
        </div>
        <span className="font-mono text-[#525252]">Lightweight Charts Engine v5</span>
      </div>
    </div>
  );
};
