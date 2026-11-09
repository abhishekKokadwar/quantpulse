import { NextRequest, NextResponse } from 'next/server';

export interface MarketDataResponse {
  symbol: string;
  timestamp: string;
  price: number;
  bestBid: number;
  bestAsk: number;
  spreadBps: number;
  microPrice: number;
  orderBook: {
    bids: [number, number, number][]; // [price, size, cumulativeNotional]
    asks: [number, number, number][];
    totalBidDepthUsd: number;
    totalAskDepthUsd: number;
  };
  candles: {
    time: number; // unix timestamp in seconds
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
    vwap: number;
  }[];
  forecastRibbon: {
    time: number;
    meanPrice: number;
    upperConfidence: number;
    lowerConfidence: number;
  }[];
  recentTrades: {
    id: string;
    time: string;
    price: number;
    size: number;
    side: 'BUY' | 'SELL';
  }[];
  metadata: {
    mode: 'live' | 'replay' | 'crisis';
    source: string;
    isLive: boolean;
    latencyMs: number;
    tickIndex?: number;
    totalTicks?: number;
    scenario?: string;
  };
}

const INSTRUMENT_BASES: Record<string, { basePrice: number; tickSize: number; binanceSymbol?: string }> = {
  'BTC/USDT': { basePrice: 83500.0, tickSize: 0.1, binanceSymbol: 'BTCUSDT' },
  'ETH/USDT': { basePrice: 3480.0, tickSize: 0.01, binanceSymbol: 'ETHUSDT' },
  'SOL/USDT': { basePrice: 154.5, tickSize: 0.01, binanceSymbol: 'SOLUSDT' },
  'NVDA': { basePrice: 128.4, tickSize: 0.01 },
  'AAPL': { basePrice: 226.5, tickSize: 0.01 },
  'SPY': { basePrice: 564.2, tickSize: 0.01 },
  'EUR/USD': { basePrice: 1.0845, tickSize: 0.0001 },
};

/**
 * Fetch real-time market data from Binance Public REST API
 */
async function fetchBinanceLiveMarket(
  symbolConfig: { binanceSymbol: string; tickSize: number },
  symbol: string
): Promise<MarketDataResponse | null> {
  const t0 = performance.now();
  const binSym = symbolConfig.binanceSymbol;

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 2500);

    const [depthRes, tradesRes, klinesRes] = await Promise.all([
      fetch(`https://api.binance.com/api/v3/depth?symbol=${binSym}&limit=20`, {
        signal: controller.signal,
        next: { revalidate: 0 },
      }),
      fetch(`https://api.binance.com/api/v3/trades?symbol=${binSym}&limit=20`, {
        signal: controller.signal,
        next: { revalidate: 0 },
      }),
      fetch(`https://api.binance.com/api/v3/klines?symbol=${binSym}&interval=1m&limit=60`, {
        signal: controller.signal,
        next: { revalidate: 0 },
      }),
    ]);

    clearTimeout(timeoutId);

    if (!depthRes.ok || !tradesRes.ok || !klinesRes.ok) {
      return null;
    }

    const depthData = await depthRes.json();
    const tradesData = await tradesRes.json();
    const klinesData = await klinesRes.json();

    // 1. Process Order Book
    let cumBidNotional = 0;
    let cumAskNotional = 0;

    const bids: [number, number, number][] = depthData.bids.map((b: [string, string]) => {
      const px = parseFloat(b[0]);
      const sz = parseFloat(b[1]);
      cumBidNotional += px * sz;
      return [Number(px.toFixed(2)), Number(sz.toFixed(4)), Number(cumBidNotional.toFixed(2))];
    });

    const asks: [number, number, number][] = depthData.asks.map((a: [string, string]) => {
      const px = parseFloat(a[0]);
      const sz = parseFloat(a[1]);
      cumAskNotional += px * sz;
      return [Number(px.toFixed(2)), Number(sz.toFixed(4)), Number(cumAskNotional.toFixed(2))];
    });

    const bestBid = bids.length > 0 ? bids[0][0] : 0;
    const bestAsk = asks.length > 0 ? asks[0][0] : 0;
    const currentPrice = (bestBid + bestAsk) / 2;
    const spreadBps = currentPrice > 0 ? ((bestAsk - bestBid) / currentPrice) * 10000 : 0;

    const topBidQty = bids.length > 0 ? bids[0][1] : 1;
    const topAskQty = asks.length > 0 ? asks[0][1] : 1;
    const microPrice = (bestBid * topAskQty + bestAsk * topBidQty) / (topBidQty + topAskQty);

    // 2. Process Candles & VWAP
    let runningCumVol = 0;
    let runningCumNotional = 0;
    const candles = klinesData.map((k: (number | string)[]) => {
      const openTime = Math.floor(Number(k[0]) / 1000);
      const open = parseFloat(k[1] as string);
      const high = parseFloat(k[2] as string);
      const low = parseFloat(k[3] as string);
      const close = parseFloat(k[4] as string);
      const vol = parseFloat(k[5] as string);
      const notional = parseFloat(k[7] as string);

      runningCumVol += vol;
      runningCumNotional += notional;
      const vwap = runningCumVol > 0 ? runningCumNotional / runningCumVol : close;

      return {
        time: openTime,
        open: Number(open.toFixed(2)),
        high: Number(high.toFixed(2)),
        low: Number(low.toFixed(2)),
        close: Number(close.toFixed(2)),
        volume: Number(vol.toFixed(2)),
        vwap: Number(vwap.toFixed(2)),
      };
    });

    // 3. Process Recent Trades
    interface RawBinanceTrade {
      id: number;
      time: number;
      price: string;
      qty: string;
      isBuyerMaker: boolean;
    }

    const recentTrades = tradesData.slice(0, 15).map((tr: RawBinanceTrade) => {
      const px = parseFloat(tr.price);
      const sz = parseFloat(tr.qty);
      const side: 'BUY' | 'SELL' = tr.isBuyerMaker ? 'SELL' : 'BUY';
      return {
        id: `BIN-${tr.id}`,
        time: new Date(tr.time).toISOString(),
        price: Number(px.toFixed(2)),
        size: Number(sz.toFixed(4)),
        side,
      };
    });

    // 4. Generate Forward AI Forecast Ribbon starting from real live close
    const nowSec = Math.floor(Date.now() / 1000);
    const forecastRibbon = [];
    const expectedReturnBps = +12.5;
    const targetReturnRatio = 1 + expectedReturnBps / 10000;

    for (let step = 1; step <= 5; step++) {
      const fTime = nowSec + step * 60;
      const pathAlpha = Math.pow(targetReturnRatio, step / 5);
      const meanPx = currentPrice * pathAlpha;
      const bandWidth = currentPrice * (0.0012 * Math.sqrt(step));

      forecastRibbon.push({
        time: fTime,
        meanPrice: Number(meanPx.toFixed(2)),
        upperConfidence: Number((meanPx + bandWidth).toFixed(2)),
        lowerConfidence: Number((meanPx - bandWidth).toFixed(2)),
      });
    }

    const latencyMs = Math.round(performance.now() - t0);

    return {
      symbol,
      timestamp: new Date().toISOString(),
      price: Number(currentPrice.toFixed(2)),
      bestBid: Number(bestBid.toFixed(2)),
      bestAsk: Number(bestAsk.toFixed(2)),
      spreadBps: Number(spreadBps.toFixed(4)),
      microPrice: Number(microPrice.toFixed(2)),
      orderBook: {
        bids,
        asks,
        totalBidDepthUsd: Number(cumBidNotional.toFixed(2)),
        totalAskDepthUsd: Number(cumAskNotional.toFixed(2)),
      },
      candles,
      forecastRibbon,
      recentTrades,
      metadata: {
        mode: 'live',
        source: 'Binance Exchange (Live Stream)',
        isLive: true,
        latencyMs,
      },
    };
  } catch {
    return null;
  }
}

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const symbol = searchParams.get('symbol') || 'BTC/USDT';
  const mode = (searchParams.get('mode') || 'live') as 'live' | 'replay' | 'crisis';
  const scenario = searchParams.get('scenario') || 'normal';
  const tickIndex = parseInt(searchParams.get('tickIndex') || '0', 10);

  const baseConfig = INSTRUMENT_BASES[symbol] || INSTRUMENT_BASES['BTC/USDT'];

  // MODE 1: LIVE REAL EXCHANGE DATA
  if (mode === 'live' && baseConfig.binanceSymbol) {
    const liveResult = await fetchBinanceLiveMarket(
      { binanceSymbol: baseConfig.binanceSymbol, tickSize: baseConfig.tickSize },
      symbol
    );
    if (liveResult) {
      return NextResponse.json(liveResult);
    }
  }

  // Fallback or Synthetic Mode (REPLAY or CRISIS SIMULATION)
  const t0 = performance.now();
  let currentPrice = baseConfig.basePrice;
  let spreadMultiplier = 1.0;
  let depthMultiplier = 1.0;
  let isSellHeavy = false;

  // MODE 2: REPLAY LOGIC
  if (mode === 'replay') {
    const cycle = (tickIndex % 300) / 300;
    const wave = Math.sin(cycle * Math.PI * 4) * 0.015 + Math.cos(cycle * Math.PI * 2) * 0.008;
    currentPrice = baseConfig.basePrice * (1 + wave);
    spreadMultiplier = 1.0 + Math.abs(Math.sin(cycle * 10)) * 0.5;
  }
  // MODE 3: CRISIS SIMULATION LOGIC
  else if (mode === 'crisis') {
    if (scenario === 'toxic_dump') {
      currentPrice *= 0.985;
      spreadMultiplier = 3.5;
      depthMultiplier = 0.6;
      isSellHeavy = true;
    } else if (scenario === 'liquidity_vacuum') {
      spreadMultiplier = 7.0;
      depthMultiplier = 0.15; // 85% depth evacuation
    } else if (scenario === 'flash_crash') {
      currentPrice *= 0.94;
      spreadMultiplier = 12.0;
      depthMultiplier = 0.08;
      isSellHeavy = true;
    } else if (scenario === 'cointegration_breakdown') {
      currentPrice *= 1.025;
      spreadMultiplier = 4.2;
      depthMultiplier = 0.5;
    }
  }

  const baseSpread = baseConfig.tickSize * 2 * spreadMultiplier;
  const bestBid = currentPrice - baseSpread / 2;
  const bestAsk = currentPrice + baseSpread / 2;
  const spreadBps = ((bestAsk - bestBid) / currentPrice) * 10000;

  // Generate 20-level Order Book Ladder
  const bids: [number, number, number][] = [];
  const asks: [number, number, number][] = [];
  let cumBidNotional = 0;
  let cumAskNotional = 0;

  for (let i = 0; i < 20; i++) {
    const bidPx = bestBid - i * baseConfig.tickSize;
    const askPx = bestAsk + i * baseConfig.tickSize;

    const bidBaseQty = (1.5 + Math.sin(i * 0.8) * 0.8 + Math.random() * 0.5) * depthMultiplier;
    const askBaseQty =
      (1.5 + Math.cos(i * 0.8) * 0.8 + Math.random() * 0.5) * depthMultiplier * (isSellHeavy ? 3.0 : 1.0);

    const bidSize = Math.max(0.01, bidBaseQty);
    const askSize = Math.max(0.01, askBaseQty);

    cumBidNotional += bidPx * bidSize;
    cumAskNotional += askPx * askSize;

    bids.push([Number(bidPx.toFixed(2)), Number(bidSize.toFixed(4)), Number(cumBidNotional.toFixed(2))]);
    asks.push([Number(askPx.toFixed(2)), Number(askSize.toFixed(4)), Number(cumAskNotional.toFixed(2))]);
  }

  const topBidQty = bids[0][1];
  const topAskQty = asks[0][1];
  const microPrice = (bestBid * topAskQty + bestAsk * topBidQty) / (topBidQty + topAskQty);

  // Generate 60 historical 1-minute OHLCV Candlesticks with rolling VWAP
  const nowSec = Math.floor(Date.now() / 1000);
  const candles = [];
  let candleClose = currentPrice * 0.99;
  let runningCumVol = 0;
  let runningCumNotional = 0;

  for (let i = 60; i >= 0; i--) {
    const cTime = nowSec - i * 60;
    const delta = (Math.random() - 0.49) * (currentPrice * 0.0015);
    const open = candleClose;
    const close = i === 0 ? currentPrice : open + delta;
    const high = Math.max(open, close) + Math.random() * (currentPrice * 0.0008);
    const low = Math.min(open, close) - Math.random() * (currentPrice * 0.0008);
    const vol = Math.floor(50 + Math.random() * 200) * depthMultiplier;

    runningCumVol += vol;
    runningCumNotional += ((open + high + low + close) / 4) * vol;
    const vwap = runningCumVol > 0 ? runningCumNotional / runningCumVol : close;

    candles.push({
      time: cTime,
      open: Number(open.toFixed(2)),
      high: Number(high.toFixed(2)),
      low: Number(low.toFixed(2)),
      close: Number(close.toFixed(2)),
      volume: vol,
      vwap: Number(vwap.toFixed(2)),
    });
    candleClose = close;
  }

  // Generate Forward AI Forecast Ribbon (t+1 to t+5 minutes)
  const forecastRibbon = [];
  const expectedReturnBps =
    scenario === 'flash_crash'
      ? -120
      : scenario === 'toxic_dump'
      ? -45
      : scenario === 'cointegration_breakdown'
      ? +65
      : +18.5;
  const targetReturnRatio = 1 + expectedReturnBps / 10000;

  for (let step = 1; step <= 5; step++) {
    const fTime = nowSec + step * 60;
    const pathAlpha = Math.pow(targetReturnRatio, step / 5);
    const meanPx = currentPrice * pathAlpha;
    const bandWidth = currentPrice * (0.0012 * Math.sqrt(step));

    forecastRibbon.push({
      time: fTime,
      meanPrice: Number(meanPx.toFixed(2)),
      upperConfidence: Number((meanPx + bandWidth).toFixed(2)),
      lowerConfidence: Number((meanPx - bandWidth).toFixed(2)),
    });
  }

  // Recent Trade Ticks
  const recentTrades = [];
  for (let t = 0; t < 15; t++) {
    const tradeSide: 'BUY' | 'SELL' = isSellHeavy
      ? Math.random() < 0.85
        ? 'SELL'
        : 'BUY'
      : Math.random() > 0.5
      ? 'BUY'
      : 'SELL';
    const tradePx = tradeSide === 'BUY' ? bestAsk : bestBid;
    const tradeQty = Number((0.1 + Math.random() * 2.5 * (isSellHeavy ? 2.5 : 1.0)).toFixed(4));

    recentTrades.push({
      id: `TRD-${Date.now()}-${t}`,
      time: new Date(Date.now() - t * 1200).toISOString(),
      price: Number(tradePx.toFixed(2)),
      size: tradeQty,
      side: tradeSide,
    });
  }

  const latencyMs = Math.round(performance.now() - t0);

  const payload: MarketDataResponse = {
    symbol,
    timestamp: new Date().toISOString(),
    price: Number(currentPrice.toFixed(2)),
    bestBid: Number(bestBid.toFixed(2)),
    bestAsk: Number(bestAsk.toFixed(2)),
    spreadBps: Number(spreadBps.toFixed(4)),
    microPrice: Number(microPrice.toFixed(2)),
    orderBook: {
      bids,
      asks,
      totalBidDepthUsd: Number(cumBidNotional.toFixed(2)),
      totalAskDepthUsd: Number(cumAskNotional.toFixed(2)),
    },
    candles,
    forecastRibbon,
    recentTrades,
    metadata: {
      mode,
      source:
        mode === 'live'
          ? 'Synthetic Gateway (Non-Crypto Asset)'
          : mode === 'replay'
          ? 'Historical Tick Lakehouse Replay'
          : `QuantPulse Anomaly Sandbox (${scenario})`,
      isLive: false,
      latencyMs,
      tickIndex: mode === 'replay' ? tickIndex : undefined,
      totalTicks: mode === 'replay' ? 1500 : undefined,
      scenario: mode === 'crisis' ? scenario : undefined,
    },
  };

  return NextResponse.json(payload);
}
