'use client';

import React, { useEffect, useRef, useState, useCallback } from 'react';

interface DOMLadderProps {
  bids: [number, number, number][]; // [price, size, cumNotional]
  asks: [number, number, number][];
  bestBid: number;
  bestAsk: number;
  spreadBps: number;
  microPrice: number;
  symbol: string;
  onPriceSelect?: (price: number) => void;
}

export const DOMLadderCanvas: React.FC<DOMLadderProps> = ({
  bids,
  asks,
  bestBid,
  bestAsk,
  spreadBps,
  microPrice,
  symbol,
  onPriceSelect,
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [hoveredLevel, setHoveredLevel] = useState<{ price: number; type: 'bid' | 'ask'; size: number } | null>(null);

  // High-performance 60 FPS Canvas Renderer
  const renderCanvas = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const width = canvas.width;
    const height = canvas.height;

    // Clear background (OLED pitch black)
    ctx.fillStyle = '#000000';
    ctx.fillRect(0, 0, width, height);

    const rowHeight = 22;
    const maxRows = Math.min(12, Math.min(bids.length, asks.length));
    const centerY = height / 2;

    // Find max cumulative notional for horizontal bar scaling
    const maxCumBid = bids[maxRows - 1]?.[2] || 1;
    const maxCumAsk = asks[maxRows - 1]?.[2] || 1;
    const maxCum = Math.max(maxCumBid, maxCumAsk);

    // 1. Draw Asks (Top Half, descending from top towards spread)
    for (let i = 0; i < maxRows; i++) {
      const askIdx = maxRows - 1 - i;
      const ask = asks[askIdx];
      if (!ask) continue;
      const [price, size, cumNotional] = ask;

      const y = centerY - 24 - (i + 1) * rowHeight;
      const barWidth = (cumNotional / maxCum) * (width * 0.45);

      // Depth bar (refined soft crimson gradient)
      const grad = ctx.createLinearGradient(width - barWidth, 0, width, 0);
      grad.addColorStop(0, 'rgba(239, 68, 68, 0.03)');
      grad.addColorStop(1, 'rgba(239, 68, 68, 0.18)');
      ctx.fillStyle = grad;
      ctx.fillRect(width - barWidth, y, barWidth, rowHeight - 2);

      // Price text (Crimson)
      ctx.fillStyle = '#EF4444';
      ctx.font = '500 11px "JetBrains Mono", monospace';
      ctx.textAlign = 'left';
      ctx.fillText(price.toLocaleString(undefined, { minimumFractionDigits: 2 }), 14, y + 14);

      // Size text
      ctx.fillStyle = '#A3A3A3';
      ctx.font = '400 10.5px "JetBrains Mono", monospace';
      ctx.textAlign = 'right';
      ctx.fillText(size.toFixed(4), width * 0.55, y + 14);

      // Cumulative Notional
      ctx.fillStyle = '#525252';
      ctx.font = '400 10px "JetBrains Mono", monospace';
      ctx.textAlign = 'right';
      ctx.fillText(`$${(cumNotional / 1000).toFixed(1)}k`, width - 14, y + 14);
    }

    // 2. Draw Center Spread Banner (Minimalist OLED)
    const bannerY = centerY - 18;
    ctx.fillStyle = '#080808';
    ctx.fillRect(0, bannerY, width, 36);

    ctx.strokeStyle = '#1A1A1A';
    ctx.lineWidth = 1;
    ctx.strokeRect(0, bannerY, width, 36);

    // Spread readout (Refined Silver)
    ctx.fillStyle = '#A3A3A3';
    ctx.font = '600 11px "Inter", sans-serif';
    ctx.textAlign = 'left';
    ctx.fillText(`SPREAD: ${spreadBps.toFixed(4)} bps`, 14, bannerY + 22);

    // Micro-price needle marker
    const mid = (bestBid + bestAsk) / 2;
    const microSkewBps = ((microPrice - mid) / mid) * 10000;
    const microColor = microPrice >= mid ? '#10B981' : '#EF4444';

    ctx.fillStyle = microColor;
    ctx.font = '500 10px "JetBrains Mono", monospace';
    ctx.textAlign = 'right';
    ctx.fillText(`μ-Px: $${microPrice.toFixed(2)} (${microSkewBps > 0 ? '+' : ''}${microSkewBps.toFixed(2)} bps)`, width - 14, bannerY + 22);

    // 3. Draw Bids (Bottom Half, descending from spread downwards)
    for (let i = 0; i < maxRows; i++) {
      const bid = bids[i];
      if (!bid) continue;
      const [price, size, cumNotional] = bid;

      const y = centerY + 24 + i * rowHeight;
      const barWidth = (cumNotional / maxCum) * (width * 0.45);

      // Depth bar (refined soft emerald gradient)
      const grad = ctx.createLinearGradient(width - barWidth, 0, width, 0);
      grad.addColorStop(0, 'rgba(16, 185, 129, 0.03)');
      grad.addColorStop(1, 'rgba(16, 185, 129, 0.18)');
      ctx.fillStyle = grad;
      ctx.fillRect(width - barWidth, y, barWidth, rowHeight - 2);

      // Price text (Emerald)
      ctx.fillStyle = '#10B981';
      ctx.font = '500 11px "JetBrains Mono", monospace';
      ctx.textAlign = 'left';
      ctx.fillText(price.toLocaleString(undefined, { minimumFractionDigits: 2 }), 14, y + 14);

      // Size text
      ctx.fillStyle = '#A3A3A3';
      ctx.font = '400 10.5px "JetBrains Mono", monospace';
      ctx.textAlign = 'right';
      ctx.fillText(size.toFixed(4), width * 0.55, y + 14);

      // Cumulative Notional
      ctx.fillStyle = '#525252';
      ctx.font = '400 10px "JetBrains Mono", monospace';
      ctx.textAlign = 'right';
      ctx.fillText(`$${(cumNotional / 1000).toFixed(1)}k`, width - 14, y + 14);
    }
  }, [bids, asks, bestBid, bestAsk, spreadBps, microPrice]);

  // Handle Resize & Canvas Pixel Ratio Scaling for crisp HiDPI displays
  useEffect(() => {
    const handleResize = () => {
      const canvas = canvasRef.current;
      const container = containerRef.current;
      if (!canvas || !container) return;

      const rect = container.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;

      const ctx = canvas.getContext('2d');
      if (ctx) ctx.scale(dpr, dpr);

      renderCanvas();
    };

    handleResize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [renderCanvas]);

  // Request Animation Frame loop (60 FPS)
  useEffect(() => {
    let animId: number;
    const loop = () => {
      renderCanvas();
      animId = requestAnimationFrame(loop);
    };
    animId = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(animId);
  }, [renderCanvas]);

  const handleCanvasClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!onPriceSelect || !hoveredLevel) return;
    onPriceSelect(hoveredLevel.price);
  };

  return (
    <div className="flex flex-col h-full bg-[#0A0A0A] border border-[#1A1A1A] rounded-xl overflow-hidden shadow-2xl">
      {/* Header bar */}
      <div className="flex items-center justify-between px-3 py-2 bg-[#000000] border-b border-[#1A1A1A]">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          <span className="text-xs font-semibold uppercase tracking-wider text-[#FFFFFF]">
            60 FPS DOM Ladder
          </span>
          <span className="text-[10px] font-mono text-[#A3A3A3] px-1.5 py-0.5 bg-[#171717] rounded border border-[#262626]">
            {symbol}
          </span>
        </div>
        <div className="flex items-center gap-3 text-[11px] font-mono">
          <span className="text-emerald-400">Bid: {bestBid.toFixed(2)}</span>
          <span className="text-[#525252]">|</span>
          <span className="text-rose-400">Ask: {bestAsk.toFixed(2)}</span>
        </div>
      </div>

      {/* Ladder Column Header */}
      <div className="flex items-center justify-between px-3 py-1.5 bg-[#050505] text-[10px] font-medium text-[#A3A3A3] border-b border-[#1A1A1A]">
        <span>PRICE (USD)</span>
        <span className="pr-4">SIZE</span>
        <span>CUMULATIVE</span>
      </div>

      {/* 60 FPS HTML5 Canvas Container */}
      <div ref={containerRef} className="relative flex-1 w-full min-h-[460px] cursor-crosshair">
        <canvas
          ref={canvasRef}
          className="w-full h-full block"
          onClick={handleCanvasClick}
        />
      </div>

      {/* Footer Info */}
      <div className="flex items-center justify-between px-3 py-1.5 bg-[#000000] border-t border-[#1A1A1A] text-[10px] text-[#A3A3A3]">
        <span>Hardware-Accelerated L2 Engine</span>
        <span className="text-[#737373] font-mono">Sub-Millisecond Depth Sync</span>
      </div>
    </div>
  );
};
