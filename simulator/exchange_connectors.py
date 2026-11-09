"""
QuantPulse: Multi-Exchange Ingestion & Normalization Protocol
=============================================================
Provides unified normalization adapters converting heterogeneous raw WebSocket
and REST market data streams from Binance, Coinbase Advanced, and Alpaca into
standardized QuantPulse `TradeTick` and `OrderBookSnapshot` objects.

Also includes an offline MockExchangeGateway for zero-dependency local simulation.
"""

import json
import os
import sys
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from simulator.market_simulator import MarketSimulator, OrderBookSnapshot, TradeTick


class BaseExchangeConnector(ABC):
    """Abstract interface for exchange payload normalization."""

    @abstractmethod
    def normalize_trade(self, raw_msg: Dict[str, Any]) -> TradeTick:
        """Converts raw exchange trade JSON into a standard TradeTick."""
        pass

    @abstractmethod
    def normalize_orderbook(self, raw_msg: Dict[str, Any]) -> OrderBookSnapshot:
        """Converts raw exchange order book JSON into a standard OrderBookSnapshot."""
        pass


class BinanceConnector(BaseExchangeConnector):
    """
    Normalizes Binance Spot and USDT-M Futures WebSocket streams:
    - Trade stream: `<symbol>@trade`
    - Depth stream: `<symbol>@depth10@100ms`
    """

    def __init__(self, default_asset_class: str = "crypto"):
        self.asset_class = default_asset_class

    def _clean_symbol(self, sym: str) -> str:
        """Converts Binance format (e.g. 'BTCUSDT') to standard 'BTC/USDT'."""
        sym_upper = sym.upper()
        if sym_upper.endswith("USDT"):
            base = sym_upper[:-4]
            return f"{base}/USDT"
        if sym_upper.endswith("USD"):
            base = sym_upper[:-3]
            return f"{base}/USD"
        return sym_upper

    def normalize_trade(self, raw_msg: Dict[str, Any]) -> TradeTick:
        # Binance trade message structure:
        # {'e': 'trade', 'E': 1672531200000, 's': 'BTCUSDT', 't': 123456, 'p': '64250.50', 'q': '0.1500', 'b': 88, 'a': 99, 'T': 1672531200000, 'm': True}
        raw_sym = raw_msg.get("s", "BTCUSDT")
        clean_sym = self._clean_symbol(raw_sym)
        price = float(raw_msg.get("p", 0.0))
        quantity = float(raw_msg.get("q", 0.0))
        is_buyer_maker = bool(raw_msg.get("m", False))
        side = "SELL" if is_buyer_maker else "BUY"  # If buyer is maker, seller is aggressor (market sell)

        ts_epoch_ms = raw_msg.get("T", raw_msg.get("E", int(datetime.now(timezone.utc).timestamp() * 1000)))
        ts_dt = datetime.fromtimestamp(ts_epoch_ms / 1000.0, tz=timezone.utc)

        trade_id = int(raw_msg.get("t", raw_msg.get("trade_id", 1)))
        notional_usd = round(price * quantity, 2)

        return TradeTick(
            trade_id=trade_id,
            symbol=clean_sym,
            asset_class=self.asset_class,
            exchange="BINANCE",
            timestamp=ts_dt.isoformat(),
            price=price,
            quantity=quantity,
            side=side,
            is_buyer_maker=is_buyer_maker,
            liquidation=bool(raw_msg.get("liquidation", False)),
            notional_usd=notional_usd,
        )

    def normalize_orderbook(self, raw_msg: Dict[str, Any]) -> OrderBookSnapshot:
        # Binance depth message structure:
        # {'lastUpdateId': 1000, 'bids': [['64250.00', '1.2'], ...], 'asks': [['64250.50', '0.8'], ...]}
        raw_sym = raw_msg.get("s", "BTCUSDT")
        clean_sym = self._clean_symbol(raw_sym)
        ts = raw_msg.get("timestamp", datetime.now(timezone.utc).isoformat())

        raw_bids = raw_msg.get("bids", [])
        raw_asks = raw_msg.get("asks", [])

        bids: List[Tuple[float, float]] = [(float(p), float(q)) for p, q in raw_bids[:10]]
        asks: List[Tuple[float, float]] = [(float(p), float(q)) for p, q in raw_asks[:10]]

        if not bids:
            bids = [(100.0, 1.0)]
        if not asks:
            asks = [(100.1, 1.0)]

        bid_p1, bid_q1 = bids[0]
        ask_p1, ask_q1 = asks[0]
        spread = round(ask_p1 - bid_p1, 8)
        mid_p = round((bid_p1 + ask_p1) / 2.0, 8)
        spread_bps = round((spread / mid_p) * 10000.0, 2) if mid_p > 0 else 0.0
        micro_p = round((bid_p1 * ask_q1 + ask_p1 * bid_q1) / (bid_q1 + ask_q1), 8)
        ofi = round((bid_q1 - ask_q1) / (bid_q1 + ask_q1), 4)

        return OrderBookSnapshot(
            snapshot_id=int(raw_msg.get("lastUpdateId", raw_msg.get("snapshot_id", 1))),
            symbol=clean_sym,
            asset_class=self.asset_class,
            exchange="BINANCE",
            timestamp=ts,
            bid_price_1=bid_p1,
            bid_size_1=bid_q1,
            ask_price_1=ask_p1,
            ask_size_1=ask_q1,
            spread=spread,
            spread_bps=spread_bps,
            mid_price=mid_p,
            micro_price=micro_p,
            order_flow_imbalance=ofi,
            bids=bids,
            asks=asks,
        )


class CoinbaseConnector(BaseExchangeConnector):
    """
    Normalizes Coinbase Advanced Trade WebSocket feed:
    - Channel: `market_trades`
    - Channel: `level2`
    """

    def __init__(self, default_asset_class: str = "crypto"):
        self.asset_class = default_asset_class

    def _clean_symbol(self, prod_id: str) -> str:
        """Converts Coinbase product_id (e.g. 'BTC-USD') to 'BTC/USD'."""
        return prod_id.replace("-", "/")

    def normalize_trade(self, raw_msg: Dict[str, Any]) -> TradeTick:
        # Coinbase market_trades structure:
        # {'type': 'match', 'trade_id': 12345, 'product_id': 'BTC-USD', 'price': '64250.50', 'size': '0.1500', 'side': 'buy', 'time': '2026-09-12T10:00:00.123Z'}
        prod_id = raw_msg.get("product_id", "BTC-USD")
        clean_sym = self._clean_symbol(prod_id)
        price = float(raw_msg.get("price", 0.0))
        quantity = float(raw_msg.get("size", raw_msg.get("quantity", 0.0)))
        side = str(raw_msg.get("side", "BUY")).upper()
        is_buyer_maker = (side == "SELL")

        ts_str = raw_msg.get("time", raw_msg.get("timestamp", datetime.now(timezone.utc).isoformat()))

        return TradeTick(
            trade_id=int(raw_msg.get("trade_id", 1)),
            symbol=clean_sym,
            asset_class=self.asset_class,
            exchange="COINBASE",
            timestamp=ts_str,
            price=price,
            quantity=quantity,
            side=side,
            is_buyer_maker=is_buyer_maker,
            liquidation=False,
            notional_usd=round(price * quantity, 2),
        )

    def normalize_orderbook(self, raw_msg: Dict[str, Any]) -> OrderBookSnapshot:
        prod_id = raw_msg.get("product_id", "BTC-USD")
        clean_sym = self._clean_symbol(prod_id)
        ts_str = raw_msg.get("time", datetime.now(timezone.utc).isoformat())

        raw_bids = raw_msg.get("bids", [])
        raw_asks = raw_msg.get("asks", [])
        bids: List[Tuple[float, float]] = [(float(p), float(q)) for p, q in raw_bids[:10]]
        asks: List[Tuple[float, float]] = [(float(p), float(q)) for p, q in raw_asks[:10]]

        if not bids:
            bids = [(100.0, 1.0)]
        if not asks:
            asks = [(100.1, 1.0)]

        bid_p1, bid_q1 = bids[0]
        ask_p1, ask_q1 = asks[0]
        spread = round(ask_p1 - bid_p1, 8)
        mid_p = round((bid_p1 + ask_p1) / 2.0, 8)
        spread_bps = round((spread / mid_p) * 10000.0, 2) if mid_p > 0 else 0.0
        micro_p = round((bid_p1 * ask_q1 + ask_p1 * bid_q1) / (bid_q1 + ask_q1), 8)
        ofi = round((bid_q1 - ask_q1) / (bid_q1 + ask_q1), 4)

        return OrderBookSnapshot(
            snapshot_id=int(raw_msg.get("sequence", 1)),
            symbol=clean_sym,
            asset_class=self.asset_class,
            exchange="COINBASE",
            timestamp=ts_str,
            bid_price_1=bid_p1,
            bid_size_1=bid_q1,
            ask_price_1=ask_p1,
            ask_size_1=ask_q1,
            spread=spread,
            spread_bps=spread_bps,
            mid_price=mid_p,
            micro_price=micro_p,
            order_flow_imbalance=ofi,
            bids=bids,
            asks=asks,
        )


class AlpacaConnector(BaseExchangeConnector):
    """
    Normalizes Alpaca Equities SIP market data feed:
    - Tape feed: `trades` (T: 't')
    - Quote feed: `quotes` (T: 'q')
    """

    def __init__(self, default_asset_class: str = "equities"):
        self.asset_class = default_asset_class

    def normalize_trade(self, raw_msg: Dict[str, Any]) -> TradeTick:
        # Alpaca Trade Message structure:
        # {'T': 't', 'S': 'AAPL', 'i': 9876, 'x': 'V', 'p': 220.50, 's': 100, 't': '2026-09-12T14:30:00.123456Z', 'c': ['@']}
        symbol = raw_msg.get("S", raw_msg.get("symbol", "AAPL"))
        price = float(raw_msg.get("p", raw_msg.get("price", 0.0)))
        size = float(raw_msg.get("s", raw_msg.get("quantity", 0.0)))
        exchange = raw_msg.get("x", "NASDAQ")
        trade_id = int(raw_msg.get("i", raw_msg.get("trade_id", 1)))
        ts_str = raw_msg.get("t", raw_msg.get("timestamp", datetime.now(timezone.utc).isoformat()))

        # Alpaca SIP feeds don't explicitly declare buyer vs seller maker; default side inference
        side = raw_msg.get("side", "BUY")

        return TradeTick(
            trade_id=trade_id,
            symbol=symbol,
            asset_class=self.asset_class,
            exchange=exchange,
            timestamp=ts_str,
            price=price,
            quantity=size,
            side=side,
            is_buyer_maker=False,
            liquidation=False,
            notional_usd=round(price * size, 2),
        )

    def normalize_orderbook(self, raw_msg: Dict[str, Any]) -> OrderBookSnapshot:
        # Alpaca Quote Message structure:
        # {'T': 'q', 'S': 'AAPL', 'bx': 'V', 'bp': 220.45, 'bs': 200, 'ax': 'V', 'ap': 220.55, 'as': 300, 't': '...'}
        symbol = raw_msg.get("S", raw_msg.get("symbol", "AAPL"))
        bid_p1 = float(raw_msg.get("bp", raw_msg.get("bid_price_1", 100.0)))
        bid_q1 = float(raw_msg.get("bs", raw_msg.get("bid_size_1", 100.0)))
        ask_p1 = float(raw_msg.get("ap", raw_msg.get("ask_price_1", 100.1)))
        ask_q1 = float(raw_msg.get("as", raw_msg.get("ask_size_1", 100.0)))
        ts_str = raw_msg.get("t", datetime.now(timezone.utc).isoformat())

        spread = round(ask_p1 - bid_p1, 4)
        mid_p = round((bid_p1 + ask_p1) / 2.0, 4)
        spread_bps = round((spread / mid_p) * 10000.0, 2) if mid_p > 0 else 0.0
        micro_p = round((bid_p1 * ask_q1 + ask_p1 * bid_q1) / (bid_q1 + ask_q1), 4)
        ofi = round((bid_q1 - ask_q1) / (bid_q1 + ask_q1), 4)

        return OrderBookSnapshot(
            snapshot_id=int(raw_msg.get("snapshot_id", 1)),
            symbol=symbol,
            asset_class=self.asset_class,
            exchange=raw_msg.get("bx", "NASDAQ"),
            timestamp=ts_str,
            bid_price_1=bid_p1,
            bid_size_1=bid_q1,
            ask_price_1=ask_p1,
            ask_size_1=ask_q1,
            spread=spread,
            spread_bps=spread_bps,
            mid_price=mid_p,
            micro_price=micro_p,
            order_flow_imbalance=ofi,
            bids=[(bid_p1, bid_q1)],
            asks=[(ask_p1, ask_q1)],
        )


class MockExchangeGateway:
    """
    Offline synthetic exchange gateway wrapping MarketSimulator to produce
    realistic multi-exchange streams without external socket dependencies.
    """

    def __init__(self, simulator: Optional[MarketSimulator] = None):
        self.sim = simulator or MarketSimulator()
        self.binance = BinanceConnector()
        self.coinbase = CoinbaseConnector()
        self.alpaca = AlpacaConnector()

    def generate_simulated_exchange_event(self, symbol: str) -> Dict[str, Any]:
        """Generates a raw exchange payload using the simulator."""
        cfg = self.sim.registry[symbol]
        book = self.sim.generate_order_book(symbol)
        trade = self.sim.generate_trade(symbol, book=book)

        if cfg.asset_class == "crypto":
            # Simulate Binance JSON format
            raw_trade = {
                "e": "trade",
                "E": int(datetime.now(timezone.utc).timestamp() * 1000),
                "s": symbol.replace("/", ""),
                "t": trade.trade_id,
                "p": str(trade.price),
                "q": str(trade.quantity),
                "m": trade.is_buyer_maker,
                "T": int(datetime.now(timezone.utc).timestamp() * 1000),
            }
            normalized = self.binance.normalize_trade(raw_trade)
        elif cfg.asset_class in ("equities", "etfs"):
            # Simulate Alpaca JSON format
            raw_trade = {
                "T": "t",
                "S": symbol,
                "i": trade.trade_id,
                "x": cfg.exchange_primary,
                "p": trade.price,
                "s": trade.quantity,
                "t": trade.timestamp,
                "side": trade.side,
            }
            normalized = self.alpaca.normalize_trade(raw_trade)
        else:
            normalized = trade

        return {
            "symbol": symbol,
            "normalized_trade": normalized,
            "normalized_book": book,
        }


if __name__ == "__main__":
    gw = MockExchangeGateway()
    event_crypto = gw.generate_simulated_exchange_event("BTC/USDT")
    event_stock = gw.generate_simulated_exchange_event("AAPL")
    print(f"[Gateway Test] Crypto Trade: {event_crypto['normalized_trade'].symbol} @ ${event_crypto['normalized_trade'].price}")
    print(f"[Gateway Test] Equity Trade: {event_stock['normalized_trade'].symbol} @ ${event_stock['normalized_trade'].price}")
