"""
QuantPulse: Multi-Asset Synthetic Market Simulator
=================================================
High-frequency financial market simulator generating microsecond-precision Level-1
trade ticks and Level-2 order books across 42 multi-asset instruments.

Mathematical foundations:
1. Merton Poisson Jump Diffusion for underlying asset spot price:
   dS_t / S_t = (mu - lambda * k) dt + sigma * dW_t + J_t * dN_t
2. Mean-reverting Ornstein-Uhlenbeck spread dynamics:
   ds_t = theta * (bar_s - s_t) dt + sigma_s * dW_t^s  (clamped to tick_size)
3. 10-level Level-2 order book depth with exponential queue decay:
   V(l) = V_0 * exp(-alpha * l) * xi
4. Intraday U-shaped volume & volatility curves (session opens / market close smiles).
5. Lee-Ready order aggressor classification and crypto liquidation cascades.
"""

import math
import os
import random
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Generator, List, Optional, Tuple

import numpy as np

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# =============================================================================
# 1. 42-Instrument Multi-Asset Universe Registry
# =============================================================================

@dataclass(frozen=True)
class InstrumentConfig:
    symbol: str
    asset_class: str
    base_currency: str
    quote_currency: str
    ref_price: float
    tick_size: float
    lot_size: float
    annual_vol: float
    jump_intensity: float       # Poisson arrivals per trading day
    jump_mean: float            # Mean jump return mu_J
    jump_std: float             # Jump return volatility sigma_J
    base_spread_bps: float      # Base bid-ask spread in basis points (1 bp = 0.01%)
    ou_mean_reversion: float    # Theta in OU process
    ou_spread_vol: float        # Volatility of spread
    depth_decay_alpha: float    # Alpha in exponential queue decay
    exchange_primary: str


INSTRUMENT_REGISTRY: Dict[str, InstrumentConfig] = {
    # -------------------------------------------------------------------------
    # Tier-1 Crypto Assets (10 instruments) - 24/7 continuous trading
    # -------------------------------------------------------------------------
    "BTC/USDT": InstrumentConfig(
        symbol="BTC/USDT", asset_class="crypto", base_currency="BTC", quote_currency="USDT",
        ref_price=64250.0, tick_size=0.01, lot_size=0.0001, annual_vol=0.65,
        jump_intensity=0.08, jump_mean=-0.002, jump_std=0.015, base_spread_bps=1.2,
        ou_mean_reversion=8.0, ou_spread_vol=0.5, depth_decay_alpha=0.25, exchange_primary="BINANCE"
    ),
    "ETH/USDT": InstrumentConfig(
        symbol="ETH/USDT", asset_class="crypto", base_currency="ETH", quote_currency="USDT",
        ref_price=3420.0, tick_size=0.01, lot_size=0.001, annual_vol=0.72,
        jump_intensity=0.09, jump_mean=-0.003, jump_std=0.018, base_spread_bps=1.5,
        ou_mean_reversion=8.0, ou_spread_vol=0.6, depth_decay_alpha=0.28, exchange_primary="BINANCE"
    ),
    "SOL/USDT": InstrumentConfig(
        symbol="SOL/USDT", asset_class="crypto", base_currency="SOL", quote_currency="USDT",
        ref_price=145.50, tick_size=0.01, lot_size=0.01, annual_vol=0.85,
        jump_intensity=0.12, jump_mean=-0.004, jump_std=0.022, base_spread_bps=2.0,
        ou_mean_reversion=7.0, ou_spread_vol=0.8, depth_decay_alpha=0.30, exchange_primary="BINANCE"
    ),
    "BNB/USDT": InstrumentConfig(
        symbol="BNB/USDT", asset_class="crypto", base_currency="BNB", quote_currency="USDT",
        ref_price=580.0, tick_size=0.01, lot_size=0.005, annual_vol=0.60,
        jump_intensity=0.07, jump_mean=-0.002, jump_std=0.014, base_spread_bps=1.8,
        ou_mean_reversion=8.5, ou_spread_vol=0.5, depth_decay_alpha=0.27, exchange_primary="BINANCE"
    ),
    "XRP/USDT": InstrumentConfig(
        symbol="XRP/USDT", asset_class="crypto", base_currency="XRP", quote_currency="USDT",
        ref_price=0.5620, tick_size=0.0001, lot_size=1.0, annual_vol=0.80,
        jump_intensity=0.11, jump_mean=-0.003, jump_std=0.020, base_spread_bps=2.5,
        ou_mean_reversion=6.5, ou_spread_vol=0.7, depth_decay_alpha=0.32, exchange_primary="BINANCE"
    ),
    "ADA/USDT": InstrumentConfig(
        symbol="ADA/USDT", asset_class="crypto", base_currency="ADA", quote_currency="USDT",
        ref_price=0.3840, tick_size=0.0001, lot_size=1.0, annual_vol=0.82,
        jump_intensity=0.10, jump_mean=-0.003, jump_std=0.020, base_spread_bps=2.8,
        ou_mean_reversion=6.5, ou_spread_vol=0.7, depth_decay_alpha=0.32, exchange_primary="BINANCE"
    ),
    "AVAX/USDT": InstrumentConfig(
        symbol="AVAX/USDT", asset_class="crypto", base_currency="AVAX", quote_currency="USDT",
        ref_price=26.40, tick_size=0.01, lot_size=0.1, annual_vol=0.88,
        jump_intensity=0.12, jump_mean=-0.004, jump_std=0.024, base_spread_bps=2.4,
        ou_mean_reversion=7.0, ou_spread_vol=0.8, depth_decay_alpha=0.31, exchange_primary="BINANCE"
    ),
    "LINK/USDT": InstrumentConfig(
        symbol="LINK/USDT", asset_class="crypto", base_currency="LINK", quote_currency="USDT",
        ref_price=12.80, tick_size=0.001, lot_size=0.1, annual_vol=0.75,
        jump_intensity=0.09, jump_mean=-0.002, jump_std=0.018, base_spread_bps=2.2,
        ou_mean_reversion=7.5, ou_spread_vol=0.6, depth_decay_alpha=0.29, exchange_primary="BINANCE"
    ),
    "DOGE/USDT": InstrumentConfig(
        symbol="DOGE/USDT", asset_class="crypto", base_currency="DOGE", quote_currency="USDT",
        ref_price=0.10850, tick_size=0.00001, lot_size=10.0, annual_vol=0.95,
        jump_intensity=0.15, jump_mean=-0.005, jump_std=0.028, base_spread_bps=3.5,
        ou_mean_reversion=5.5, ou_spread_vol=1.0, depth_decay_alpha=0.35, exchange_primary="BINANCE"
    ),
    "DOT/USDT": InstrumentConfig(
        symbol="DOT/USDT", asset_class="crypto", base_currency="DOT", quote_currency="USDT",
        ref_price=4.650, tick_size=0.001, lot_size=0.5, annual_vol=0.78,
        jump_intensity=0.09, jump_mean=-0.003, jump_std=0.019, base_spread_bps=2.6,
        ou_mean_reversion=7.0, ou_spread_vol=0.7, depth_decay_alpha=0.30, exchange_primary="BINANCE"
    ),

    # -------------------------------------------------------------------------
    # Mega-Cap US Equities (14 instruments) - NASDAQ / NYSE
    # -------------------------------------------------------------------------
    "AAPL": InstrumentConfig(
        symbol="AAPL", asset_class="equities", base_currency="AAPL", quote_currency="USD",
        ref_price=224.20, tick_size=0.01, lot_size=1.0, annual_vol=0.24,
        jump_intensity=0.02, jump_mean=-0.001, jump_std=0.008, base_spread_bps=1.0,
        ou_mean_reversion=12.0, ou_spread_vol=0.3, depth_decay_alpha=0.20, exchange_primary="NASDAQ"
    ),
    "MSFT": InstrumentConfig(
        symbol="MSFT", asset_class="equities", base_currency="MSFT", quote_currency="USD",
        ref_price=428.50, tick_size=0.01, lot_size=1.0, annual_vol=0.23,
        jump_intensity=0.02, jump_mean=-0.001, jump_std=0.008, base_spread_bps=1.0,
        ou_mean_reversion=12.0, ou_spread_vol=0.3, depth_decay_alpha=0.20, exchange_primary="NASDAQ"
    ),
    "NVDA": InstrumentConfig(
        symbol="NVDA", asset_class="equities", base_currency="NVDA", quote_currency="USD",
        ref_price=118.40, tick_size=0.01, lot_size=1.0, annual_vol=0.48,
        jump_intensity=0.05, jump_mean=-0.002, jump_std=0.014, base_spread_bps=1.2,
        ou_mean_reversion=10.0, ou_spread_vol=0.4, depth_decay_alpha=0.22, exchange_primary="NASDAQ"
    ),
    "AMZN": InstrumentConfig(
        symbol="AMZN", asset_class="equities", base_currency="AMZN", quote_currency="USD",
        ref_price=186.20, tick_size=0.01, lot_size=1.0, annual_vol=0.30,
        jump_intensity=0.03, jump_mean=-0.001, jump_std=0.010, base_spread_bps=1.1,
        ou_mean_reversion=11.0, ou_spread_vol=0.35, depth_decay_alpha=0.21, exchange_primary="NASDAQ"
    ),
    "GOOGL": InstrumentConfig(
        symbol="GOOGL", asset_class="equities", base_currency="GOOGL", quote_currency="USD",
        ref_price=162.80, tick_size=0.01, lot_size=1.0, annual_vol=0.28,
        jump_intensity=0.03, jump_mean=-0.001, jump_std=0.009, base_spread_bps=1.1,
        ou_mean_reversion=11.0, ou_spread_vol=0.35, depth_decay_alpha=0.21, exchange_primary="NASDAQ"
    ),
    "META": InstrumentConfig(
        symbol="META", asset_class="equities", base_currency="META", quote_currency="USD",
        ref_price=512.00, tick_size=0.01, lot_size=1.0, annual_vol=0.36,
        jump_intensity=0.04, jump_mean=-0.002, jump_std=0.012, base_spread_bps=1.3,
        ou_mean_reversion=10.5, ou_spread_vol=0.4, depth_decay_alpha=0.22, exchange_primary="NASDAQ"
    ),
    "TSLA": InstrumentConfig(
        symbol="TSLA", asset_class="equities", base_currency="TSLA", quote_currency="USD",
        ref_price=218.60, tick_size=0.01, lot_size=1.0, annual_vol=0.55,
        jump_intensity=0.06, jump_mean=-0.003, jump_std=0.018, base_spread_bps=1.5,
        ou_mean_reversion=9.0, ou_spread_vol=0.5, depth_decay_alpha=0.24, exchange_primary="NASDAQ"
    ),
    "AMD": InstrumentConfig(
        symbol="AMD", asset_class="equities", base_currency="AMD", quote_currency="USD",
        ref_price=142.30, tick_size=0.01, lot_size=1.0, annual_vol=0.44,
        jump_intensity=0.04, jump_mean=-0.002, jump_std=0.013, base_spread_bps=1.4,
        ou_mean_reversion=10.0, ou_spread_vol=0.45, depth_decay_alpha=0.23, exchange_primary="NASDAQ"
    ),
    "INTC": InstrumentConfig(
        symbol="INTC", asset_class="equities", base_currency="INTC", quote_currency="USD",
        ref_price=20.50, tick_size=0.01, lot_size=1.0, annual_vol=0.42,
        jump_intensity=0.04, jump_mean=-0.002, jump_std=0.012, base_spread_bps=1.5,
        ou_mean_reversion=10.0, ou_spread_vol=0.45, depth_decay_alpha=0.24, exchange_primary="NASDAQ"
    ),
    "QCOM": InstrumentConfig(
        symbol="QCOM", asset_class="equities", base_currency="QCOM", quote_currency="USD",
        ref_price=168.40, tick_size=0.01, lot_size=1.0, annual_vol=0.34,
        jump_intensity=0.03, jump_mean=-0.001, jump_std=0.011, base_spread_bps=1.3,
        ou_mean_reversion=10.5, ou_spread_vol=0.4, depth_decay_alpha=0.22, exchange_primary="NASDAQ"
    ),
    "JPM": InstrumentConfig(
        symbol="JPM", asset_class="equities", base_currency="JPM", quote_currency="USD",
        ref_price=214.50, tick_size=0.01, lot_size=1.0, annual_vol=0.20,
        jump_intensity=0.015, jump_mean=-0.001, jump_std=0.007, base_spread_bps=1.0,
        ou_mean_reversion=13.0, ou_spread_vol=0.25, depth_decay_alpha=0.19, exchange_primary="NYSE"
    ),
    "GS": InstrumentConfig(
        symbol="GS", asset_class="equities", base_currency="GS", quote_currency="USD",
        ref_price=486.20, tick_size=0.01, lot_size=1.0, annual_vol=0.22,
        jump_intensity=0.02, jump_mean=-0.001, jump_std=0.008, base_spread_bps=1.2,
        ou_mean_reversion=12.0, ou_spread_vol=0.3, depth_decay_alpha=0.20, exchange_primary="NYSE"
    ),
    "V": InstrumentConfig(
        symbol="V", asset_class="equities", base_currency="V", quote_currency="USD",
        ref_price=274.00, tick_size=0.01, lot_size=1.0, annual_vol=0.18,
        jump_intensity=0.01, jump_mean=-0.0008, jump_std=0.006, base_spread_bps=0.9,
        ou_mean_reversion=14.0, ou_spread_vol=0.2, depth_decay_alpha=0.18, exchange_primary="NYSE"
    ),
    "MA": InstrumentConfig(
        symbol="MA", asset_class="equities", base_currency="MA", quote_currency="USD",
        ref_price=468.80, tick_size=0.01, lot_size=1.0, annual_vol=0.19,
        jump_intensity=0.01, jump_mean=-0.0008, jump_std=0.006, base_spread_bps=1.0,
        ou_mean_reversion=13.5, ou_spread_vol=0.25, depth_decay_alpha=0.19, exchange_primary="NYSE"
    ),

    # -------------------------------------------------------------------------
    # Broad Market ETFs (6 instruments) - ARCA / NASDAQ
    # -------------------------------------------------------------------------
    "SPY": InstrumentConfig(
        symbol="SPY", asset_class="etfs", base_currency="SPY", quote_currency="USD",
        ref_price=558.00, tick_size=0.01, lot_size=1.0, annual_vol=0.14,
        jump_intensity=0.01, jump_mean=-0.0005, jump_std=0.005, base_spread_bps=0.5,
        ou_mean_reversion=16.0, ou_spread_vol=0.15, depth_decay_alpha=0.15, exchange_primary="ARCA"
    ),
    "QQQ": InstrumentConfig(
        symbol="QQQ", asset_class="etfs", base_currency="QQQ", quote_currency="USD",
        ref_price=482.50, tick_size=0.01, lot_size=1.0, annual_vol=0.18,
        jump_intensity=0.015, jump_mean=-0.0008, jump_std=0.006, base_spread_bps=0.6,
        ou_mean_reversion=15.0, ou_spread_vol=0.2, depth_decay_alpha=0.16, exchange_primary="NASDAQ"
    ),
    "IWM": InstrumentConfig(
        symbol="IWM", asset_class="etfs", base_currency="IWM", quote_currency="USD",
        ref_price=218.00, tick_size=0.01, lot_size=1.0, annual_vol=0.22,
        jump_intensity=0.02, jump_mean=-0.001, jump_std=0.007, base_spread_bps=0.8,
        ou_mean_reversion=13.0, ou_spread_vol=0.25, depth_decay_alpha=0.18, exchange_primary="ARCA"
    ),
    "XLF": InstrumentConfig(
        symbol="XLF", asset_class="etfs", base_currency="XLF", quote_currency="USD",
        ref_price=45.20, tick_size=0.01, lot_size=1.0, annual_vol=0.16,
        jump_intensity=0.01, jump_mean=-0.0006, jump_std=0.005, base_spread_bps=0.7,
        ou_mean_reversion=15.0, ou_spread_vol=0.2, depth_decay_alpha=0.17, exchange_primary="ARCA"
    ),
    "XLK": InstrumentConfig(
        symbol="XLK", asset_class="etfs", base_currency="XLK", quote_currency="USD",
        ref_price=218.40, tick_size=0.01, lot_size=1.0, annual_vol=0.21,
        jump_intensity=0.015, jump_mean=-0.0008, jump_std=0.006, base_spread_bps=0.7,
        ou_mean_reversion=14.0, ou_spread_vol=0.22, depth_decay_alpha=0.17, exchange_primary="ARCA"
    ),
    "GLD": InstrumentConfig(
        symbol="GLD", asset_class="etfs", base_currency="GLD", quote_currency="USD",
        ref_price=232.00, tick_size=0.01, lot_size=1.0, annual_vol=0.15,
        jump_intensity=0.01, jump_mean=-0.0005, jump_std=0.005, base_spread_bps=0.8,
        ou_mean_reversion=14.5, ou_spread_vol=0.2, depth_decay_alpha=0.18, exchange_primary="ARCA"
    ),

    # -------------------------------------------------------------------------
    # Forex Majors & Crosses (8 instruments) - Continuous Interbank Market
    # -------------------------------------------------------------------------
    "EUR/USD": InstrumentConfig(
        symbol="EUR/USD", asset_class="forex", base_currency="EUR", quote_currency="USD",
        ref_price=1.09200, tick_size=0.00001, lot_size=1000.0, annual_vol=0.08,
        jump_intensity=0.01, jump_mean=-0.0004, jump_std=0.003, base_spread_bps=0.6,
        ou_mean_reversion=15.0, ou_spread_vol=0.15, depth_decay_alpha=0.16, exchange_primary="FXCM"
    ),
    "GBP/USD": InstrumentConfig(
        symbol="GBP/USD", asset_class="forex", base_currency="GBP", quote_currency="USD",
        ref_price=1.31400, tick_size=0.00001, lot_size=1000.0, annual_vol=0.09,
        jump_intensity=0.01, jump_mean=-0.0004, jump_std=0.0035, base_spread_bps=0.8,
        ou_mean_reversion=14.0, ou_spread_vol=0.2, depth_decay_alpha=0.18, exchange_primary="FXCM"
    ),
    "USD/JPY": InstrumentConfig(
        symbol="USD/JPY", asset_class="forex", base_currency="USD", quote_currency="JPY",
        ref_price=142.600, tick_size=0.001, lot_size=1000.0, annual_vol=0.10,
        jump_intensity=0.015, jump_mean=-0.0005, jump_std=0.004, base_spread_bps=0.7,
        ou_mean_reversion=13.5, ou_spread_vol=0.2, depth_decay_alpha=0.17, exchange_primary="FXCM"
    ),
    "AUD/USD": InstrumentConfig(
        symbol="AUD/USD", asset_class="forex", base_currency="AUD", quote_currency="USD",
        ref_price=0.67150, tick_size=0.00001, lot_size=1000.0, annual_vol=0.11,
        jump_intensity=0.01, jump_mean=-0.0004, jump_std=0.0035, base_spread_bps=0.9,
        ou_mean_reversion=13.0, ou_spread_vol=0.25, depth_decay_alpha=0.19, exchange_primary="FXCM"
    ),
    "USD/CAD": InstrumentConfig(
        symbol="USD/CAD", asset_class="forex", base_currency="USD", quote_currency="CAD",
        ref_price=1.35650, tick_size=0.00001, lot_size=1000.0, annual_vol=0.08,
        jump_intensity=0.01, jump_mean=-0.0003, jump_std=0.003, base_spread_bps=0.8,
        ou_mean_reversion=14.0, ou_spread_vol=0.2, depth_decay_alpha=0.18, exchange_primary="FXCM"
    ),
    "USD/CHF": InstrumentConfig(
        symbol="USD/CHF", asset_class="forex", base_currency="USD", quote_currency="CHF",
        ref_price=0.84900, tick_size=0.00001, lot_size=1000.0, annual_vol=0.08,
        jump_intensity=0.01, jump_mean=-0.0003, jump_std=0.003, base_spread_bps=0.9,
        ou_mean_reversion=13.5, ou_spread_vol=0.22, depth_decay_alpha=0.19, exchange_primary="FXCM"
    ),
    "EUR/GBP": InstrumentConfig(
        symbol="EUR/GBP", asset_class="forex", base_currency="EUR", quote_currency="GBP",
        ref_price=0.84350, tick_size=0.00001, lot_size=1000.0, annual_vol=0.07,
        jump_intensity=0.01, jump_mean=-0.0003, jump_std=0.0028, base_spread_bps=0.9,
        ou_mean_reversion=14.5, ou_spread_vol=0.2, depth_decay_alpha=0.18, exchange_primary="FXCM"
    ),
    "EUR/JPY": InstrumentConfig(
        symbol="EUR/JPY", asset_class="forex", base_currency="EUR", quote_currency="JPY",
        ref_price=155.800, tick_size=0.001, lot_size=1000.0, annual_vol=0.11,
        jump_intensity=0.015, jump_mean=-0.0005, jump_std=0.004, base_spread_bps=0.8,
        ou_mean_reversion=13.0, ou_spread_vol=0.22, depth_decay_alpha=0.18, exchange_primary="FXCM"
    ),

    # -------------------------------------------------------------------------
    # Commodities & Energy Futures (4 instruments) - NYMEX / CME
    # -------------------------------------------------------------------------
    "WTI/USD": InstrumentConfig(
        symbol="WTI/USD", asset_class="commodities", base_currency="WTI", quote_currency="USD",
        ref_price=69.40, tick_size=0.01, lot_size=10.0, annual_vol=0.32,
        jump_intensity=0.03, jump_mean=-0.0015, jump_std=0.012, base_spread_bps=1.5,
        ou_mean_reversion=10.0, ou_spread_vol=0.4, depth_decay_alpha=0.22, exchange_primary="NYMEX"
    ),
    "BRENT/USD": InstrumentConfig(
        symbol="BRENT/USD", asset_class="commodities", base_currency="BRENT", quote_currency="USD",
        ref_price=72.80, tick_size=0.01, lot_size=10.0, annual_vol=0.30,
        jump_intensity=0.03, jump_mean=-0.0015, jump_std=0.011, base_spread_bps=1.4,
        ou_mean_reversion=10.5, ou_spread_vol=0.38, depth_decay_alpha=0.21, exchange_primary="ICE"
    ),
    "NATGAS/USD": InstrumentConfig(
        symbol="NATGAS/USD", asset_class="commodities", base_currency="NATGAS", quote_currency="USD",
        ref_price=2.350, tick_size=0.001, lot_size=100.0, annual_vol=0.55,
        jump_intensity=0.06, jump_mean=-0.003, jump_std=0.018, base_spread_bps=2.5,
        ou_mean_reversion=8.0, ou_spread_vol=0.6, depth_decay_alpha=0.28, exchange_primary="NYMEX"
    ),
    "XAU/USD": InstrumentConfig(
        symbol="XAU/USD", asset_class="commodities", base_currency="XAU", quote_currency="USD",
        ref_price=2512.00, tick_size=0.01, lot_size=1.0, annual_vol=0.16,
        jump_intensity=0.02, jump_mean=-0.0008, jump_std=0.006, base_spread_bps=0.8,
        ou_mean_reversion=13.0, ou_spread_vol=0.25, depth_decay_alpha=0.18, exchange_primary="COMEX"
    ),
}


# =============================================================================
# 2. Level-1 Trade and Level-2 Order Book Data Structures
# =============================================================================

@dataclass
class TradeTick:
    trade_id: int
    symbol: str
    asset_class: str
    exchange: str
    timestamp: str          # ISO8601 UTC with microsecond precision
    price: float
    quantity: float
    side: str               # 'BUY' (Buyer Maker / Aggressor Buy) or 'SELL'
    is_buyer_maker: bool    # True if buyer placed resting limit order hit by seller
    liquidation: bool       # True for liquidation cascade / forced margin sell
    notional_usd: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "asset_class": self.asset_class,
            "exchange": self.exchange,
            "timestamp": self.timestamp,
            "price": self.price,
            "quantity": self.quantity,
            "side": self.side,
            "is_buyer_maker": self.is_buyer_maker,
            "liquidation": self.liquidation,
            "notional_usd": self.notional_usd,
        }


@dataclass
class OrderBookSnapshot:
    snapshot_id: int
    symbol: str
    asset_class: str
    exchange: str
    timestamp: str
    bid_price_1: float
    bid_size_1: float
    ask_price_1: float
    ask_size_1: float
    spread: float
    spread_bps: float
    mid_price: float
    micro_price: float
    order_flow_imbalance: float
    bids: List[Tuple[float, float]]     # 10 levels: [(price, size), ...]
    asks: List[Tuple[float, float]]     # 10 levels: [(price, size), ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "symbol": self.symbol,
            "asset_class": self.asset_class,
            "exchange": self.exchange,
            "timestamp": self.timestamp,
            "bid_price_1": self.bid_price_1,
            "bid_size_1": self.bid_size_1,
            "ask_price_1": self.ask_price_1,
            "ask_size_1": self.ask_size_1,
            "spread": self.spread,
            "spread_bps": self.spread_bps,
            "mid_price": self.mid_price,
            "micro_price": self.micro_price,
            "order_flow_imbalance": self.order_flow_imbalance,
            "bids": self.bids,
            "asks": self.asks,
        }


# =============================================================================
# 3. Market Simulator Engine (Merton Jump Diffusion + OU Spreads)
# =============================================================================

class MarketSimulator:
    """
    High-frequency multi-asset market simulator implementing Merton Poisson Jump Diffusion,
    Ornstein-Uhlenbeck spread dynamics, and Level-2 order book ladders.
    """

    def __init__(self, registry: Optional[Dict[str, InstrumentConfig]] = None, seed: Optional[int] = 42):
        self.registry = registry or INSTRUMENT_REGISTRY
        if seed is not None:
            np.random.seed(seed)
            random.seed(seed)

        # State tracking per instrument: current spot price and current spread
        self.spot_prices: Dict[str, float] = {
            sym: cfg.ref_price for sym, cfg in self.registry.items()
        }
        self.spreads: Dict[str, float] = {
            sym: max(cfg.tick_size, cfg.ref_price * (cfg.base_spread_bps / 10000.0))
            for sym, cfg in self.registry.items()
        }
        self.trade_counter: int = 1
        self.snapshot_counter: int = 1
        self.last_trade_prices: Dict[str, float] = {
            sym: cfg.ref_price for sym, cfg in self.registry.items()
        }

    def _get_intraday_volatility_multiplier(self, dt: datetime, asset_class: str) -> float:
        """
        Computes intraday U-shaped volatility multiplier for equity/commodity market hours:
        High at open (09:30), dipping at midday (12:30), surging towards close (16:00).
        Crypto and Forex trade continuously with dampened diurnal swings.
        """
        if asset_class == "crypto":
            # 24/7 continuous market: mild global session variation
            hour = dt.hour + dt.minute / 60.0
            return 1.0 + 0.15 * math.sin((hour - 8.0) / 24.0 * 2.0 * math.pi)

        if asset_class == "forex":
            # London / NY overlap surge (12:00 - 16:00 UTC)
            hour = dt.hour + dt.minute / 60.0
            if 12.0 <= hour <= 16.0:
                return 1.35
            return 0.90

        # Equities and ETFs: NYSE/NASDAQ Hours (09:30 - 16:00 EST)
        hour = dt.hour + dt.minute / 60.0
        if hour < 9.5 or hour > 16.0:
            return 0.35  # After-hours / pre-market quietness
        # U-curve: normalized between 9.5 and 16.0 (length 6.5 hours)
        t_norm = (hour - 9.5) / 6.5
        u_curve = 1.0 + 0.65 * (4.0 * (t_norm - 0.5) ** 2)
        return float(u_curve)

    def step_price(self, symbol: str, dt_seconds: float = 1.0, current_dt: Optional[datetime] = None) -> float:
        """
        Advances the spot price by dt_seconds using Merton Jump Diffusion:
        S_{t+dt} = S_t * exp( (mu - 0.5*sigma^2 - lambda*k)*dt + sigma*sqrt(dt)*Z + sum(Y_i) )
        """
        cfg = self.registry[symbol]
        curr_price = self.spot_prices[symbol]
        dt_years = dt_seconds / (365.25 * 24.0 * 3600.0)

        # Volatility adjusted by intraday calendar multiplier
        now = current_dt or datetime.now(timezone.utc)
        vol_mult = self._get_intraday_volatility_multiplier(now, cfg.asset_class)
        instantaneous_vol = cfg.annual_vol * vol_mult

        # Poisson jump process
        dt_trading_days = dt_seconds / 86400.0
        expected_jumps = cfg.jump_intensity * dt_trading_days
        num_jumps = np.random.poisson(expected_jumps)
        jump_sum = 0.0
        if num_jumps > 0:
            jump_returns = np.random.normal(cfg.jump_mean, cfg.jump_std, size=num_jumps)
            jump_sum = float(np.sum(jump_returns))

        # Drift adjustment k = E[e^Y - 1]
        k = math.exp(cfg.jump_mean + 0.5 * (cfg.jump_std ** 2)) - 1.0
        mu = 0.05  # Slight positive expected long-term drift
        drift = (mu - 0.5 * (instantaneous_vol ** 2) - cfg.jump_intensity * k) * dt_years

        # Standard Brownian shock
        diffusion = instantaneous_vol * math.sqrt(max(1e-10, dt_years)) * np.random.normal(0, 1)

        # Next price calculation
        log_return = drift + diffusion + jump_sum
        next_price = curr_price * math.exp(log_return)

        # Enforce positive price boundary
        next_price = max(cfg.tick_size * 5.0, next_price)
        self.spot_prices[symbol] = next_price
        return next_price

    def step_spread(self, symbol: str, dt_seconds: float = 1.0) -> float:
        """
        Updates the bid-ask spread using Ornstein-Uhlenbeck mean reversion:
        ds_t = theta * (bar_s - s_t) * dt + sigma_s * sqrt(dt) * Z_t
        Clamped strictly to minimum tick_size.
        """
        cfg = self.registry[symbol]
        curr_spread = self.spreads[symbol]
        dt_normalized = dt_seconds / 60.0  # OU parameters calibrated to minutes

        target_spread = max(cfg.tick_size, self.spot_prices[symbol] * (cfg.base_spread_bps / 10000.0))
        drift = cfg.ou_mean_reversion * (target_spread - curr_spread) * dt_normalized
        diffusion = cfg.ou_spread_vol * target_spread * math.sqrt(dt_normalized) * np.random.normal(0, 1)

        next_spread = curr_spread + drift + diffusion
        # Clamp: spread must be at least tick_size and no wider than 2.5% of spot
        next_spread = max(cfg.tick_size, min(self.spot_prices[symbol] * 0.025, next_spread))
        self.spreads[symbol] = next_spread
        return next_spread

    def generate_order_book(self, symbol: str, dt: Optional[datetime] = None) -> OrderBookSnapshot:
        """
        Constructs a realistic 10-level Level-2 bid/ask order book.
        Enforces strict arbitrage boundaries:
        - Ask_1 > Bid_1
        - Monotonic bid ladder (Bid_1 > Bid_2 > ... > Bid_10)
        - Monotonic ask ladder (Ask_1 < Ask_2 < ... < Ask_10)
        - Micro-price strictly within [Bid_1, Ask_1]
        """
        cfg = self.registry[symbol]
        spot = self.spot_prices[symbol]
        spread = self.spreads[symbol]
        now_iso = (dt or datetime.now(timezone.utc)).isoformat()

        # Top of book prices rounded to tick_size
        half_spread = spread / 2.0
        bid_1 = math.floor((spot - half_spread) / cfg.tick_size) * cfg.tick_size
        ask_1 = math.ceil((spot + half_spread) / cfg.tick_size) * cfg.tick_size

        # Invariant: Ask_1 must strictly exceed Bid_1
        if ask_1 <= bid_1:
            ask_1 = bid_1 + cfg.tick_size

        actual_spread = round(ask_1 - bid_1, 8)
        mid_price = round((bid_1 + ask_1) / 2.0, 8)
        spread_bps = round((actual_spread / mid_price) * 10000.0, 2) if mid_price > 0 else 0.0

        # Base queue volume at top of book
        base_notional = 25000.0  # ~$25k at best bid/ask
        base_size = max(cfg.lot_size, round(base_notional / max(1.0, spot), 4))

        # Generate 10 levels with exponential volume decay
        bids: List[Tuple[float, float]] = [(bid_1, base_size)]
        asks: List[Tuple[float, float]] = [(ask_1, base_size)]

        curr_bid_p = bid_1
        curr_ask_p = ask_1
        tick_sz = cfg.tick_size
        decay_alpha = cfg.depth_decay_alpha
        min_lot = cfg.lot_size

        for level in range(2, 11):
            curr_bid_p = round(curr_bid_p - tick_sz, 8)
            curr_ask_p = round(curr_ask_p + tick_sz, 8)
            decay = math.exp(decay_alpha * (level - 1))
            vol_bid = round(max(min_lot, base_size * decay), 4)
            vol_ask = round(max(min_lot, base_size * decay), 4)
            bids.append((curr_bid_p, vol_bid))
            asks.append((curr_ask_p, vol_ask))

        bid_size_1 = base_size
        ask_size_1 = base_size

        # Micro-price: P_micro = (P_bid * Q_ask + P_ask * Q_bid) / (Q_bid + Q_ask)
        micro_price = round((bid_1 * ask_size_1 + ask_1 * bid_size_1) / (bid_size_1 + ask_size_1), 8)
        # Bounded invariant
        micro_price = max(bid_1, min(ask_1, micro_price))

        # Order Flow Imbalance (OFI) at top of book: (Q_b - Q_a) / (Q_b + Q_a)
        ofi = round((bid_size_1 - ask_size_1) / (bid_size_1 + ask_size_1), 4)

        snapshot = OrderBookSnapshot(
            snapshot_id=self.snapshot_counter,
            symbol=symbol,
            asset_class=cfg.asset_class,
            exchange=cfg.exchange_primary,
            timestamp=now_iso,
            bid_price_1=round(bid_1, 8),
            bid_size_1=bid_size_1,
            ask_price_1=round(ask_1, 8),
            ask_size_1=ask_size_1,
            spread=actual_spread,
            spread_bps=spread_bps,
            mid_price=mid_price,
            micro_price=micro_price,
            order_flow_imbalance=ofi,
            bids=bids,
            asks=asks,
        )
        self.snapshot_counter += 1
        return snapshot

    def generate_trade(
        self,
        symbol: str,
        book: Optional[OrderBookSnapshot] = None,
        dt: Optional[datetime] = None,
        force_liquidation: bool = False,
    ) -> TradeTick:
        """
        Generates a realistic Level-1 execution trade tick.
        Trades occur at the best bid (seller aggressor) or best ask (buyer aggressor).
        Classifies buyer vs seller using Lee-Ready logic.
        """
        cfg = self.registry[symbol]
        if book is None:
            book = self.generate_order_book(symbol, dt)

        now_iso = (dt or datetime.now(timezone.utc)).isoformat()

        # Buyer vs Seller aggression probability weighted by OFI
        prob_buyer = 0.5 + 0.3 * book.order_flow_imbalance
        prob_buyer = max(0.15, min(0.85, prob_buyer))

        is_buyer_aggressor = random.random() < prob_buyer
        if is_buyer_aggressor:
            side = "BUY"
            price = book.ask_price_1
            is_buyer_maker = False
            available_size = book.ask_size_1
        else:
            side = "SELL"
            price = book.bid_price_1
            is_buyer_maker = True
            available_size = book.bid_size_1

        # Trade size: fraction of top of book depth or occasionally block trade
        is_block_trade = random.random() < 0.02
        if is_block_trade:
            size_multiplier = random.uniform(2.5, 6.0)
        else:
            size_multiplier = random.uniform(0.1, 0.95)

        trade_size = max(cfg.lot_size, round(available_size * size_multiplier, 4))

        # Crypto liquidation event simulation
        liquidation = False
        if cfg.asset_class == "crypto" and (force_liquidation or random.random() < 0.008):
            liquidation = True
            side = "SELL"  # Long liquidation forced selling
            price = book.bid_price_1
            is_buyer_maker = True
            trade_size = round(available_size * random.uniform(3.0, 8.0), 4)

        notional_usd = round(price * trade_size, 2)
        self.last_trade_prices[symbol] = price

        tick = TradeTick(
            trade_id=self.trade_counter,
            symbol=symbol,
            asset_class=cfg.asset_class,
            exchange=cfg.exchange_primary,
            timestamp=now_iso,
            price=price,
            quantity=trade_size,
            side=side,
            is_buyer_maker=is_buyer_maker,
            liquidation=liquidation,
            notional_usd=notional_usd,
        )
        self.trade_counter += 1
        return tick

    def generate_tick_stream(
        self,
        symbols: Optional[List[str]] = None,
        duration_seconds: int = 60,
        ticks_per_second: int = 5,
        start_time: Optional[datetime] = None,
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Yields an interleaved, chronological generator of market ticks and order books
        across requested symbols for duration_seconds.
        """
        target_symbols = symbols or list(self.registry.keys())
        current_time = start_time or datetime.now(timezone.utc)
        dt_step = timedelta(microseconds=int(1_000_000 / max(1, ticks_per_second)))

        total_steps = duration_seconds * ticks_per_second

        for _ in range(total_steps):
            for sym in target_symbols:
                self.step_price(sym, dt_seconds=dt_step.total_seconds(), current_dt=current_time)
                self.step_spread(sym, dt_seconds=dt_step.total_seconds())

                book = self.generate_order_book(sym, dt=current_time)
                trade = self.generate_trade(sym, book=book, dt=current_time)

                yield {
                    "type": "TRADE",
                    "trade": trade.to_dict(),
                    "book": book.to_dict(),
                    "timestamp": current_time.isoformat(),
                }

            current_time += dt_step

    def generate_historical_dataset(
        self,
        days: int = 1,
        ticks_per_symbol: int = 500,
        symbols: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Generates a multi-symbol historical batch dataset for backtesting and lake export.
        """
        target_symbols = symbols or list(self.registry.keys())
        readings: List[Dict[str, Any]] = []

        start_time = datetime.now(timezone.utc) - timedelta(days=days)
        interval_seconds = max(0.1, (days * 86400.0) / max(1, ticks_per_symbol))
        dt_step = timedelta(seconds=interval_seconds)

        for sym in target_symbols:
            curr_dt = start_time
            for _ in range(ticks_per_symbol):
                self.step_price(sym, dt_seconds=interval_seconds, current_dt=curr_dt)
                self.step_spread(sym, dt_seconds=interval_seconds)

                book = self.generate_order_book(sym, dt=curr_dt)
                trade = self.generate_trade(sym, book=book, dt=curr_dt)

                record = trade.to_dict()
                record["bid_1"] = book.bid_price_1
                record["ask_1"] = book.ask_price_1
                record["spread"] = book.spread
                record["mid_price"] = book.mid_price
                record["micro_price"] = book.micro_price
                record["order_flow_imbalance"] = book.order_flow_imbalance

                readings.append(record)
                curr_dt += dt_step

        return readings


if __name__ == "__main__":
    sim = MarketSimulator()
    print(f"QuantPulse Market Simulator Initialized with {len(sim.registry)} instruments.")
    sample_sym = "BTC/USDT"
    sim.step_price(sample_sym, dt_seconds=1.0)
    book = sim.generate_order_book(sample_sym)
    trade = sim.generate_trade(sample_sym, book=book)
    print(f"Sample Book for {sample_sym}: Mid={book.mid_price}, Spread={book.spread_bps} bps, OFI={book.order_flow_imbalance}")
    print(f"Sample Trade: Side={trade.side}, Price={trade.price}, Qty={trade.quantity}, Notional=${trade.notional_usd}")
