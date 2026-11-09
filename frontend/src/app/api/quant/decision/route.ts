import { NextRequest, NextResponse } from 'next/server';

export interface DecisionPayload {
  symbol: string;
  price: number;
  scenario: string;
  mode?: 'live' | 'replay' | 'crisis';
  liveTelemetry?: {
    vpin?: number;
    ofi?: number;
    spreadBps?: number;
    microPrice?: number;
  };
  config: {
    maxSpreadBps: number;
    minDepthUsd: number;
    maxVpinThreshold: number;
    maxDailyDrawdownPct: number;
    maxNetDeltaUsd: number;
    softLossThrottlePct: number;
  };
  portfolioState: {
    totalEquity: number;
    realizedPnl: number;
    unrealizedPnl: number;
    currentDrawdownPct: number;
    marginMaintenanceRatio: number;
    netDeltaUsd: number;
  };
  customKillSwitchActive?: boolean;
}

export async function POST(request: NextRequest) {
  try {
    const body: DecisionPayload = await request.json();
    const { symbol, price, scenario, mode = 'live', liveTelemetry, config, portfolioState, customKillSwitchActive } = body;

    const t0 = performance.now();

    // 1. Determine Microstructure & Scenario Variables
    let vpin = liveTelemetry?.vpin ?? 0.38;
    let ofi = liveTelemetry?.ofi ?? +0.32;
    let depthDropPct = 0.05;
    let spreadBps = liveTelemetry?.spreadBps ?? 1.2;
    let realizedVol = 0.018;
    let statArbZ = -1.15;
    let statArbState = 'IDLE';
    let predictedReturnBps = +16.5;
    let modelConfidence = 0.78;

    if (scenario === 'toxic_dump') {
      vpin = 0.89;
      ofi = -0.84;
      depthDropPct = 0.40;
      spreadBps = 12.5;
      realizedVol = 0.045;
      predictedReturnBps = +25.0; // Naive Alpha tries to buy the dip
      modelConfidence = 0.84;
    } else if (scenario === 'liquidity_vacuum') {
      vpin = 0.65;
      ofi = -0.15;
      depthDropPct = 0.86; // 86% depth drop
      spreadBps = 28.5;
      realizedVol = 0.052;
      predictedReturnBps = +12.0;
      modelConfidence = 0.65;
    } else if (scenario === 'flash_crash') {
      vpin = 0.94;
      ofi = -0.96;
      depthDropPct = 0.93;
      spreadBps = 48.0;
      realizedVol = 0.115;
      predictedReturnBps = +45.0;
      modelConfidence = 0.90;
    } else if (scenario === 'cointegration_divergence') {
      statArbZ = +3.82;
      statArbState = 'CIRCUIT_BREAKER_STOP';
    }

    // 2. Candidate Signal Determination (Consensus)
    const reasons: string[] = [];
    let candidateAction: 'BUY' | 'SELL' | 'HOLD' = 'HOLD';
    let compositeConfidence = modelConfidence;

    if (predictedReturnBps > 3.0 && modelConfidence >= 0.55) {
      candidateAction = 'BUY';
      reasons.push(`Alpha Return Forecast: +${predictedReturnBps.toFixed(1)} bps (${(modelConfidence * 100).toFixed(0)}% confidence)`);
    } else if (predictedReturnBps < -3.0 && modelConfidence >= 0.55) {
      candidateAction = 'SELL';
      reasons.push(`Alpha Return Forecast: ${predictedReturnBps.toFixed(1)} bps (${(modelConfidence * 100).toFixed(0)}% confidence)`);
    }

    if (statArbState === 'LONG_SPREAD') {
      if (candidateAction === 'BUY') {
        compositeConfidence = Math.min(0.99, compositeConfidence + 0.15);
        reasons.push(`Alpha & Stat-Arb Consensus: High-conviction long alignment (+15% confidence boost)`);
      }
    } else if (statArbState === 'SHORT_SPREAD') {
      if (candidateAction === 'BUY') {
        candidateAction = 'HOLD';
        reasons.push(`Signal Conflict: Alpha predicts BUY but Stat-Arb indicates overvalued SELL -> Neutralized to HOLD`);
      }
    }

    if (ofi > 0.3) reasons.push(`OFI Strong Buy Pressure (+${ofi.toFixed(2)})`);
    if (ofi < -0.3) reasons.push(`OFI Strong Sell Pressure (${ofi.toFixed(2)})`);

    // 3. Evaluate 3-Tier Risk Safeguards
    const vetoReasons: string[] = [];
    const hedgeOrders: Array<{ action: string; symbol: string; quantity: number; reason: string }> = [];
    const emergencyOrders: Array<{ orderType: string; reason: string }> = [];
    let riskTier = 'TIER_0_NORMAL';
    let sizeMultiplier = 1.0;
    let killSwitchActive = customKillSwitchActive || false;
    let riskState = 'NORMAL';

    // Tier 3 Hard Kill Switch Checks
    const isDrawdownBreach = portfolioState.currentDrawdownPct >= config.maxDailyDrawdownPct;
    const isMarginCollapse = portfolioState.marginMaintenanceRatio < 1.10;
    const isFlashCrash = scenario === 'flash_crash' || depthDropPct >= 0.90;

    if (killSwitchActive || isDrawdownBreach || isMarginCollapse || isFlashCrash) {
      killSwitchActive = true;
      riskTier = 'TIER_3_KILL_SWITCH';
      riskState = 'EMERGENCY_HALT';
      sizeMultiplier = 0.0;

      let killReason = 'MANUAL_OPERATOR_OVERRIDE';
      if (isDrawdownBreach) {
        killReason = `MAX_DRAWDOWN_BREACH: Drawdown (${(portfolioState.currentDrawdownPct * 100).toFixed(2)}%) exceeded ${(config.maxDailyDrawdownPct * 100).toFixed(1)}% limit.`;
      } else if (isMarginCollapse) {
        killReason = `MARGIN_CALL_COLLAPSE: Margin maintenance ratio (${(portfolioState.marginMaintenanceRatio * 100).toFixed(1)}%) breached 110% floor.`;
      } else if (isFlashCrash) {
        killReason = `CRITICAL_FLASH_CRASH: Catastrophic book collapse and market failure.`;
      }

      vetoReasons.push(`TIER_3_KILL_SWITCH: ${killReason}`);
      emergencyOrders.push({ orderType: 'CANCEL_ALL_OPEN_ORDERS', reason: killReason });
      emergencyOrders.push({ orderType: 'LIQUIDATE_ALL_POSITIONS', reason: 'EMERGENCY_PORTFOLIO_FLATTEN' });
    } else {
      // Tier 2 Auto-Hedging & Cointegration Stops
      if (Math.abs(portfolioState.netDeltaUsd) > config.maxNetDeltaUsd) {
        riskTier = 'TIER_2_HEDGING_ACTIVE';
        const hedgeAction = portfolioState.netDeltaUsd > 0 ? 'SELL' : 'BUY';
        const hedgeQty = Math.abs(portfolioState.netDeltaUsd) / price;
        hedgeOrders.push({
          action: hedgeAction,
          symbol: 'BTC/USDT',
          quantity: Number(hedgeQty.toFixed(4)),
          reason: `PORTFOLIO_DELTA_BREACH: Net delta $${portfolioState.netDeltaUsd.toLocaleString()} exceeds $${config.maxNetDeltaUsd.toLocaleString()} cap.`,
        });
        reasons.push(`Tier 2 Auto-Hedge: Directional delta neutralized with ${hedgeAction} in benchmark`);
      }

      if (statArbState === 'CIRCUIT_BREAKER_STOP' || Math.abs(statArbZ) >= 3.5) {
        riskTier = 'TIER_2_HEDGING_ACTIVE';
        vetoReasons.push(`STAT_ARB_DIVERGENCE_STOP: Spread Z-score (${statArbZ.toFixed(2)}) exceeded 3.5 sigma.`);
        hedgeOrders.push({
          action: 'CLOSE_PAIR_POSITIONS',
          symbol,
          quantity: 1.0,
          reason: 'STRUCTURAL_COINTEGRATION_BREAKDOWN_STOP',
        });
      }

      // Microstructure Guardrail Vetoes
      if (vpin >= config.maxVpinThreshold) {
        vetoReasons.push(`TOXIC_ORDER_FLOW: VPIN (${vpin.toFixed(3)}) exceeds threshold (${config.maxVpinThreshold.toFixed(2)}). Adverse selection hazard.`);
      }
      if (depthDropPct >= 0.70) {
        vetoReasons.push(`LIQUIDITY_VACUUM: Order book depth dropped by ${(depthDropPct * 100).toFixed(1)}%. Slippage risk unacceptable.`);
      }
      if (spreadBps > config.maxSpreadBps) {
        vetoReasons.push(`SPREAD_BLOWOUT: Bid-Ask spread (${spreadBps.toFixed(1)} bps) exceeds limit (${config.maxSpreadBps.toFixed(1)} bps).`);
      }
      if (candidateAction === 'BUY' && ofi < -0.50) {
        vetoReasons.push(`ADVERSE_SELECTION: Informed selling pressure (OFI: ${ofi.toFixed(2)}). BUY signal vetoed.`);
      }

      // Tier 1 Soft Sizing Throttle
      if (riskTier === 'TIER_0_NORMAL' && vetoReasons.length === 0) {
        const isSoftLoss = portfolioState.realizedPnl < -25000;
        if (isSoftLoss) {
          riskTier = 'TIER_1_THROTTLED';
          sizeMultiplier = 0.50;
          reasons.push(`Tier 1 Throttle: Daily loss reached 50% of budget. Order size halved.`);
        } else {
          sizeMultiplier = Number((Math.max(0.2, 2 * (compositeConfidence - 0.5))).toFixed(2));
        }
      }
    }

    const tradePermitted = vetoReasons.length === 0 && !killSwitchActive;
    const finalAction: 'BUY' | 'SELL' | 'HOLD' = tradePermitted ? candidateAction : 'HOLD';

    if (!tradePermitted && candidateAction !== 'HOLD') {
      reasons.push(`Original signal [${candidateAction}] suppressed by Risk Arbiter`);
    }

    if (vetoReasons.length > 0 && riskState !== 'EMERGENCY_HALT') {
      riskState = 'ELEVATED_RISK';
    }

    const elapsedMs = performance.now() - t0;

    return NextResponse.json({
      timestamp: new Date().toISOString(),
      symbol,
      action: finalAction,
      candidateAction,
      confidence: Number(compositeConfidence.toFixed(4)),
      horizon: '5m',
      reasons,
      riskState,
      tradePermitted,
      vetoReasons,
      sizeMultiplier,
      riskTier,
      killSwitchActive,
      hedgeOrders,
      emergencyOrders,
      telemetry: {
        midPrice: price,
        spreadBps: Number(spreadBps.toFixed(2)),
        orderFlowImbalance: Number(ofi.toFixed(3)),
        vpin: Number(vpin.toFixed(3)),
        depthDropPct: Number((depthDropPct * 100).toFixed(1)),
        realizedVolatility: Number(realizedVol.toFixed(5)),
      },
      statArbTelemetry: {
        spreadZScore: Number(statArbZ.toFixed(2)),
        statArbState,
      },
      portfolioTelemetry: {
        ...portfolioState,
      },
      evaluationLatencyMs: Number(elapsedMs.toFixed(3)),
    });
  } catch (error) {
    return NextResponse.json({ error: String(error) }, { status: 500 });
  }
}
