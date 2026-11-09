"""
QuantPulse: Relational Market Store, Financial Star Schema & Timescale/Postgres OLTP
===================================================================================
High-performance relational database manager for financial time-series facts:
1. instruments: Dimension table for all 42 multi-asset symbols.
2. exchanges: Dimension table for 8 trading exchange venues.
3. trades_fact: High-frequency Level-1 execution ticks.
4. orderbook_l2_snapshots: Level-2 order book depth ladders and spread metrics.
5. portfolio_positions: Live real-time position state, weighted entry price & PnL.
6. risk_events: Pre-trade and post-trade risk audit trail and circuit breakers.

Supports both PostgreSQL (Neon/Timescale) via connection pooling and zero-config
local SQLite file / in-memory modes for testing.
"""

import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
    create_engine,
    text,
)
from sqlalchemy.engine import Engine

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

load_dotenv()

# Default database URLs: PostgreSQL if configured, otherwise local SQLite
DEFAULT_SQLITE_PATH = os.path.join(PROJECT_ROOT, "data", "market_oltp.db")
DEFAULT_DB_URL = os.getenv(
    "MARKET_DATABASE_URL",
    os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_SQLITE_PATH.replace(os.sep, '/')}"),
)

metadata = MetaData()

# =============================================================================
# 1. SQLAlchemy Relational Tables (Portable DDL for Postgres & SQLite)
# =============================================================================

instruments_table = Table(
    "instruments",
    metadata,
    Column("symbol", String(32), primary_key=True),
    Column("asset_class", String(32), nullable=False),
    Column("base_currency", String(16), nullable=False),
    Column("quote_currency", String(16), nullable=False),
    Column("ref_price", Float, nullable=False),
    Column("tick_size", Float, nullable=False),
    Column("lot_size", Float, nullable=False),
    Column("annual_vol", Float, nullable=False),
    Column("base_spread_bps", Float, nullable=False),
    Column("exchange_primary", String(32), nullable=False),
    Column("status", String(16), default="ACTIVE"),
    Column("created_at", DateTime, default=datetime.utcnow),
)

exchanges_table = Table(
    "exchanges",
    metadata,
    Column("exchange_id", String(32), primary_key=True),
    Column("exchange_name", String(128), nullable=False),
    Column("asset_classes", String(128), nullable=False),
    Column("latency_tier", String(32), default="TIER_1_COLOCATED"),
    Column("created_at", DateTime, default=datetime.utcnow),
)

trades_fact_table = Table(
    "trades_fact",
    metadata,
    Column("trade_id", Integer, primary_key=True, autoincrement=True),
    Column("symbol", String(32), ForeignKey("instruments.symbol", ondelete="CASCADE"), nullable=False),
    Column("exchange", String(32), nullable=False),
    Column("timestamp", DateTime, nullable=False),
    Column("price", Float, nullable=False),
    Column("quantity", Float, nullable=False),
    Column("side", String(4), nullable=False),
    Column("is_buyer_maker", Boolean, default=False),
    Column("liquidation", Boolean, default=False),
    Column("notional_usd", Float, nullable=False),
    Column("created_at", DateTime, default=datetime.utcnow),
    Index("idx_trades_symbol_timestamp", "symbol", "timestamp"),
    Index("idx_trades_timestamp", "timestamp"),
)

orderbook_l2_table = Table(
    "orderbook_l2_snapshots",
    metadata,
    Column("snapshot_id", Integer, primary_key=True, autoincrement=True),
    Column("symbol", String(32), ForeignKey("instruments.symbol", ondelete="CASCADE"), nullable=False),
    Column("exchange", String(32), nullable=False),
    Column("timestamp", DateTime, nullable=False),
    Column("bid_price_1", Float, nullable=False),
    Column("bid_size_1", Float, nullable=False),
    Column("ask_price_1", Float, nullable=False),
    Column("ask_size_1", Float, nullable=False),
    Column("spread", Float, nullable=False),
    Column("spread_bps", Float, nullable=False),
    Column("mid_price", Float, nullable=False),
    Column("micro_price", Float, nullable=False),
    Column("order_flow_imbalance", Float, nullable=False),
    Column("depth_json", Text, nullable=True),
    Column("created_at", DateTime, default=datetime.utcnow),
    Index("idx_orderbook_symbol_timestamp", "symbol", "timestamp"),
)

portfolio_positions_table = Table(
    "portfolio_positions",
    metadata,
    Column("symbol", String(32), ForeignKey("instruments.symbol", ondelete="CASCADE"), primary_key=True),
    Column("net_quantity", Float, default=0.0),
    Column("avg_entry_price", Float, default=0.0),
    Column("current_mark_price", Float, default=0.0),
    Column("unrealized_pnl", Float, default=0.0),
    Column("realized_pnl", Float, default=0.0),
    Column("total_notional", Float, default=0.0),
    Column("updated_at", DateTime, default=datetime.utcnow),
)

risk_events_table = Table(
    "risk_events",
    metadata,
    Column("event_id", Integer, primary_key=True, autoincrement=True),
    Column("timestamp", DateTime, nullable=False),
    Column("symbol", String(32), ForeignKey("instruments.symbol", ondelete="CASCADE"), nullable=False),
    Column("risk_rule", String(64), nullable=False),
    Column("severity", String(32), nullable=False),
    Column("metric_value", Float, nullable=False),
    Column("threshold_value", Float, nullable=False),
    Column("description", Text, nullable=True),
    Column("details", Text, nullable=True),
    Column("created_at", DateTime, default=datetime.utcnow),
    Index("idx_risk_timestamp", "timestamp"),
    Index("idx_risk_symbol", "symbol"),
)

quant_aggregates_table = Table(
    "realtime_quant_aggregates",
    metadata,
    Column("aggregate_id", Integer, primary_key=True, autoincrement=True),
    Column("window_start", DateTime, nullable=False),
    Column("window_end", DateTime, nullable=False),
    Column("symbol", String(32), ForeignKey("instruments.symbol", ondelete="CASCADE"), nullable=False),
    Column("horizon", String(16), nullable=False),  # e.g. "10s", "5m"
    Column("vwap", Float, nullable=False),
    Column("order_flow_imbalance", Float, nullable=False),
    Column("micro_price", Float, nullable=False),
    Column("realized_volatility", Float, nullable=False),
    Column("cumulative_volume_delta", Float, nullable=False),
    Column("trade_count", Integer, nullable=False),
    Column("total_volume", Float, nullable=False),
    Column("created_at", DateTime, default=datetime.utcnow),
    Index("idx_quant_agg_symbol_window", "symbol", "window_start", "horizon"),
    Index("idx_quant_agg_window_end", "window_end"),
)


# =============================================================================
# 2. Market Database Manager Class
# =============================================================================

PRIMARY_EXCHANGES = [
    {"exchange_id": "BINANCE", "exchange_name": "Binance Global (Spot & Futures)", "asset_classes": "crypto", "latency_tier": "TIER_1_COLOCATED"},
    {"exchange_id": "NASDAQ", "exchange_name": "Nasdaq Stock Market", "asset_classes": "equities,etfs", "latency_tier": "TIER_1_COLOCATED"},
    {"exchange_id": "NYSE", "exchange_name": "New York Stock Exchange", "asset_classes": "equities", "latency_tier": "TIER_1_COLOCATED"},
    {"exchange_id": "ARCA", "exchange_name": "NYSE Arca", "asset_classes": "etfs,equities", "latency_tier": "TIER_1_COLOCATED"},
    {"exchange_id": "FXCM", "exchange_name": "FXCM / Interbank ECN", "asset_classes": "forex", "latency_tier": "TIER_2_CROSS_CONNECT"},
    {"exchange_id": "NYMEX", "exchange_name": "New York Mercantile Exchange", "asset_classes": "commodities", "latency_tier": "TIER_1_COLOCATED"},
    {"exchange_id": "ICE", "exchange_name": "Intercontinental Exchange", "asset_classes": "commodities", "latency_tier": "TIER_1_COLOCATED"},
    {"exchange_id": "COMEX", "exchange_name": "Commodity Exchange", "asset_classes": "commodities", "latency_tier": "TIER_1_COLOCATED"},
]


class MarketDatabaseManager:
    """
    Manages the relational financial storage engine, seeding, bulk ingestion,
    portfolio position state, and SQL pushdown analytical aggregations.
    """

    def __init__(self, db_url: Optional[str] = None):
        self.db_url = db_url or DEFAULT_DB_URL
        # Ensure sqlite directory exists if local file
        if self.db_url.startswith("sqlite:///") and ":memory:" not in self.db_url:
            path = self.db_url.replace("sqlite:///", "")
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

        is_sqlite = "sqlite" in self.db_url
        if is_sqlite:
            self.engine: Engine = create_engine(self.db_url, connect_args={"check_same_thread": False})
        else:
            self.engine: Engine = create_engine(
                self.db_url,
                pool_size=5,
                max_overflow=10,
                pool_pre_ping=True,
            )

    def init_db(self) -> None:
        """Creates all 6 normalized tables and associated indexes."""
        metadata.create_all(self.engine)

    def seed_dimensions(self, registry: Optional[Dict[str, Any]] = None) -> Tuple[int, int]:
        """
        Seeds the 42 instruments from INSTRUMENT_REGISTRY and 8 primary exchanges.
        Returns: (instruments_seeded, exchanges_seeded)
        """
        from simulator.market_simulator import INSTRUMENT_REGISTRY
        reg = registry or INSTRUMENT_REGISTRY
        self.init_db()

        with self.engine.begin() as conn:
            # 1. Seed Exchanges
            for ex in PRIMARY_EXCHANGES:
                conn.execute(
                    text("""
                    INSERT INTO exchanges (exchange_id, exchange_name, asset_classes, latency_tier, created_at)
                    VALUES (:exchange_id, :exchange_name, :asset_classes, :latency_tier, :created_at)
                    ON CONFLICT(exchange_id) DO UPDATE SET 
                        exchange_name=EXCLUDED.exchange_name,
                        asset_classes=EXCLUDED.asset_classes;
                    """),
                    {**ex, "created_at": datetime.now(timezone.utc)},
                )

            # 2. Seed Instruments
            for sym, cfg in reg.items():
                conn.execute(
                    text("""
                    INSERT INTO instruments (
                        symbol, asset_class, base_currency, quote_currency, ref_price,
                        tick_size, lot_size, annual_vol, base_spread_bps, exchange_primary, status, created_at
                    ) VALUES (
                        :symbol, :asset_class, :base_currency, :quote_currency, :ref_price,
                        :tick_size, :lot_size, :annual_vol, :base_spread_bps, :exchange_primary, :status, :created_at
                    )
                    ON CONFLICT(symbol) DO UPDATE SET 
                        ref_price=EXCLUDED.ref_price,
                        annual_vol=EXCLUDED.annual_vol,
                        base_spread_bps=EXCLUDED.base_spread_bps;
                    """),
                    {
                        "symbol": sym,
                        "asset_class": cfg.asset_class,
                        "base_currency": cfg.base_currency,
                        "quote_currency": cfg.quote_currency,
                        "ref_price": cfg.ref_price,
                        "tick_size": cfg.tick_size,
                        "lot_size": cfg.lot_size,
                        "annual_vol": cfg.annual_vol,
                        "base_spread_bps": cfg.base_spread_bps,
                        "exchange_primary": cfg.exchange_primary,
                        "status": "ACTIVE",
                        "created_at": datetime.now(timezone.utc),
                    },
                )

        return len(reg), len(PRIMARY_EXCHANGES)

    def insert_trade_ticks(self, ticks: List[Dict[str, Any]]) -> int:
        """
        High-throughput bulk insert of Level-1 execution trade ticks.
        """
        if not ticks:
            return 0

        parsed_ticks = []
        for t in ticks:
            ts = t.get("timestamp")
            if isinstance(ts, str):
                try:
                    ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except Exception:
                    ts = datetime.now(timezone.utc)
            elif not isinstance(ts, datetime):
                ts = datetime.now(timezone.utc)

            parsed_ticks.append({
                "symbol": t["symbol"],
                "exchange": t.get("exchange", "UNKNOWN"),
                "timestamp": ts,
                "price": float(t["price"]),
                "quantity": float(t["quantity"]),
                "side": str(t.get("side", "BUY")).upper(),
                "is_buyer_maker": bool(t.get("is_buyer_maker", False)),
                "liquidation": bool(t.get("liquidation", False)),
                "notional_usd": float(t.get("notional_usd", round(t["price"] * t["quantity"], 2))),
                "created_at": datetime.now(timezone.utc),
            })

        with self.engine.begin() as conn:
            conn.execute(trades_fact_table.insert(), parsed_ticks)

        return len(parsed_ticks)

    def insert_orderbook_snapshots(self, snapshots: List[Dict[str, Any]]) -> int:
        """
        High-throughput bulk insert of Level-2 order book snapshots.
        """
        if not snapshots:
            return 0

        parsed = []
        for s in snapshots:
            ts = s.get("timestamp")
            if isinstance(ts, str):
                try:
                    ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except Exception:
                    ts = datetime.now(timezone.utc)
            elif not isinstance(ts, datetime):
                ts = datetime.now(timezone.utc)

            depth_data = s.get("depth_json")
            if depth_data is None:
                depth_dict = {"bids": s.get("bids", []), "asks": s.get("asks", [])}
                depth_data = json.dumps(depth_dict)
            elif isinstance(depth_data, dict):
                depth_data = json.dumps(depth_data)

            parsed.append({
                "symbol": s["symbol"],
                "exchange": s.get("exchange", "UNKNOWN"),
                "timestamp": ts,
                "bid_price_1": float(s["bid_price_1"]),
                "bid_size_1": float(s["bid_size_1"]),
                "ask_price_1": float(s["ask_price_1"]),
                "ask_size_1": float(s["ask_size_1"]),
                "spread": float(s["spread"]),
                "spread_bps": float(s.get("spread_bps", 0.0)),
                "mid_price": float(s["mid_price"]),
                "micro_price": float(s["micro_price"]),
                "order_flow_imbalance": float(s.get("order_flow_imbalance", 0.0)),
                "depth_json": depth_data,
                "created_at": datetime.now(timezone.utc),
            })

        with self.engine.begin() as conn:
            conn.execute(orderbook_l2_table.insert(), parsed)

        return len(parsed)

    def update_portfolio_fill(
        self,
        symbol: str,
        side: str,
        fill_price: float,
        fill_qty: float,
        current_mark_price: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Updates live portfolio position upon trade execution.
        Computes weighted average entry price, realized PnL on position unwinds,
        and marks unrealized PnL against current_mark_price.
        """
        side = side.upper()
        sign = 1.0 if side == "BUY" else -1.0
        delta_qty = sign * fill_qty
        mark = current_mark_price or fill_price

        with self.engine.begin() as conn:
            row = conn.execute(
                text("SELECT net_quantity, avg_entry_price, realized_pnl FROM portfolio_positions WHERE symbol = :sym"),
                {"sym": symbol},
            ).fetchone()

            if row is None:
                # First trade for this symbol
                new_net_qty = delta_qty
                new_avg_entry = fill_price
                realized_pnl = 0.0
            else:
                curr_net_qty, curr_avg_entry, curr_realized = float(row[0]), float(row[1]), float(row[2])
                realized_pnl = curr_realized

                # Case 1: Increasing existing position (or opening new)
                if (curr_net_qty >= 0 and side == "BUY") or (curr_net_qty <= 0 and side == "SELL"):
                    new_net_qty = curr_net_qty + delta_qty
                    if abs(new_net_qty) > 1e-8:
                        new_avg_entry = (abs(curr_net_qty) * curr_avg_entry + fill_qty * fill_price) / abs(new_net_qty)
                    else:
                        new_avg_entry = 0.0

                # Case 2: Reducing existing position (partial or full close)
                else:
                    closed_qty = min(abs(curr_net_qty), fill_qty)
                    # Realized PnL: closed_qty * (exit_price - entry_price) for Longs; entry - exit for Shorts
                    if curr_net_qty > 0:
                        pnl_delta = closed_qty * (fill_price - curr_avg_entry)
                    else:
                        pnl_delta = closed_qty * (curr_avg_entry - fill_price)

                    realized_pnl += pnl_delta
                    new_net_qty = curr_net_qty + delta_qty

                    # If flipped from long to short or vice versa:
                    if (curr_net_qty > 0 and new_net_qty < 0) or (curr_net_qty < 0 and new_net_qty > 0):
                        new_avg_entry = fill_price
                    elif abs(new_net_qty) < 1e-8:
                        new_avg_entry = 0.0
                        new_net_qty = 0.0
                    else:
                        new_avg_entry = curr_avg_entry

            # Unrealized PnL = net_qty * (mark - avg_entry)
            unrealized_pnl = new_net_qty * (mark - new_avg_entry) if abs(new_net_qty) > 1e-8 else 0.0
            total_notional = round(abs(new_net_qty) * mark, 2)

            conn.execute(
                text("""
                INSERT INTO portfolio_positions (
                    symbol, net_quantity, avg_entry_price, current_mark_price,
                    unrealized_pnl, realized_pnl, total_notional, updated_at
                ) VALUES (
                    :sym, :net_qty, :avg_entry, :mark, :unrealized, :realized, :notional, :now
                )
                ON CONFLICT(symbol) DO UPDATE SET 
                    net_quantity = EXCLUDED.net_quantity,
                    avg_entry_price = EXCLUDED.avg_entry_price,
                    current_mark_price = EXCLUDED.current_mark_price,
                    unrealized_pnl = EXCLUDED.unrealized_pnl,
                    realized_pnl = EXCLUDED.realized_pnl,
                    total_notional = EXCLUDED.total_notional,
                    updated_at = EXCLUDED.updated_at;
                """),
                {
                    "sym": symbol,
                    "net_qty": round(new_net_qty, 6),
                    "avg_entry": round(new_avg_entry, 6),
                    "mark": round(mark, 6),
                    "unrealized": round(unrealized_pnl, 2),
                    "realized": round(realized_pnl, 2),
                    "notional": total_notional,
                    "now": datetime.now(timezone.utc),
                },
            )

        return {
            "symbol": symbol,
            "net_quantity": round(new_net_qty, 6),
            "avg_entry_price": round(new_avg_entry, 6),
            "current_mark_price": round(mark, 6),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "realized_pnl": round(realized_pnl, 2),
            "total_notional": total_notional,
        }

    def log_risk_event(
        self,
        symbol: str,
        risk_rule: str,
        severity: str,
        metric_value: float,
        threshold_value: float,
        description: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Logs a pre-trade or post-trade risk rule alert or circuit breaker."""
        now = datetime.now(timezone.utc)
        details_str = json.dumps(details or {})

        with self.engine.begin() as conn:
            res = conn.execute(
                risk_events_table.insert().values(
                    symbol=symbol,
                    risk_rule=risk_rule,
                    severity=severity.upper(),
                    metric_value=float(metric_value),
                    threshold_value=float(threshold_value),
                    description=description,
                    details=details_str,
                    timestamp=now,
                    created_at=now,
                )
            )
            # return inserted id if available
            return res.inserted_primary_key[0] if res.inserted_primary_key else 1

    def query_ohlcv_pushdown(
        self,
        symbol: str,
        bucket_minutes: int = 1,
        limit: int = 500,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """
        Executes an SQL pushdown query computing time-bucketed OHLCV candles
        and VWAP directly inside the database engine.
        Works across both SQLite (using strftime) and PostgreSQL.
        """
        is_sqlite = "sqlite" in self.db_url

        conditions = ["symbol = :symbol"]
        params: Dict[str, Any] = {"symbol": symbol, "limit": limit}

        if start_time:
            conditions.append("timestamp >= :start_time")
            params["start_time"] = start_time
        if end_time:
            conditions.append("timestamp <= :end_time")
            params["end_time"] = end_time

        where_clause = "WHERE " + " AND ".join(conditions)

        if is_sqlite:
            # SQLite time bucket: group by formatted minute interval
            # Interval grouping: strftime with minute rounding
            query = f"""
            SELECT 
                strftime('%Y-%m-%dT%H:%M:00', timestamp) AS bucket_time,
                (SELECT price FROM trades_fact t2 
                 WHERE t2.symbol = t.symbol AND strftime('%Y-%m-%dT%H:%M:00', t2.timestamp) = strftime('%Y-%m-%dT%H:%M:00', t.timestamp) 
                 ORDER BY t2.timestamp ASC, t2.trade_id ASC LIMIT 1) AS open,
                MAX(price) AS high,
                MIN(price) AS low,
                (SELECT price FROM trades_fact t3 
                 WHERE t3.symbol = t.symbol AND strftime('%Y-%m-%dT%H:%M:00', t3.timestamp) = strftime('%Y-%m-%dT%H:%M:00', t.timestamp) 
                 ORDER BY t3.timestamp DESC, t3.trade_id DESC LIMIT 1) AS close,
                SUM(quantity) AS volume,
                COUNT(*) AS trade_count,
                ROUND(SUM(price * quantity) / NULLIF(SUM(quantity), 0), 4) AS vwap
            FROM trades_fact t
            {where_clause}
            GROUP BY strftime('%Y-%m-%dT%H:%M:00', timestamp)
            ORDER BY bucket_time ASC
            LIMIT :limit;
            """
        else:
            # PostgreSQL time bucket using date_bin or date_trunc
            interval_str = f"{bucket_minutes} minutes"
            query = f"""
            SELECT 
                date_bin(INTERVAL '{interval_str}', timestamp, TIMESTAMPTZ '2026-01-01 00:00:00Z') AS bucket_time,
                (array_agg(price ORDER BY timestamp ASC, trade_id ASC))[1] AS open,
                MAX(price) AS high,
                MIN(price) AS low,
                (array_agg(price ORDER BY timestamp DESC, trade_id DESC))[1] AS close,
                SUM(quantity) AS volume,
                COUNT(*) AS trade_count,
                ROUND(SUM(price * quantity) / NULLIF(SUM(quantity), 0), 4) AS vwap
            FROM trades_fact
            {where_clause}
            GROUP BY 1
            ORDER BY 1 ASC
            LIMIT :limit;
            """

        with self.engine.connect() as conn:
            df = pd.read_sql(text(query), conn, params=params)

        return df

    def query_recent_trades(self, symbol: Optional[str] = None, limit: int = 100) -> pd.DataFrame:
        """Fetches latest execution ticks."""
        where = "WHERE symbol = :sym" if symbol else ""
        query = f"""
        SELECT trade_id, symbol, exchange, timestamp, price, quantity, side, is_buyer_maker, liquidation, notional_usd
        FROM trades_fact
        {where}
        ORDER BY timestamp DESC, trade_id DESC
        LIMIT :limit;
        """
        with self.engine.connect() as conn:
            return pd.read_sql(text(query), conn, params={"sym": symbol, "limit": limit})

    def query_latest_orderbook(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Fetches current L2 order book snapshot for an instrument."""
        query = """
        SELECT snapshot_id, symbol, exchange, timestamp, bid_price_1, bid_size_1, ask_price_1, ask_size_1,
               spread, spread_bps, mid_price, micro_price, order_flow_imbalance, depth_json
        FROM orderbook_l2_snapshots
        WHERE symbol = :sym
        ORDER BY timestamp DESC, snapshot_id DESC
        LIMIT 1;
        """
        with self.engine.connect() as conn:
            row = conn.execute(text(query), {"sym": symbol}).fetchone()
            if row:
                return {
                    "snapshot_id": row[0],
                    "symbol": row[1],
                    "exchange": row[2],
                    "timestamp": str(row[3]),
                    "bid_price_1": row[4],
                    "bid_size_1": row[5],
                    "ask_price_1": row[6],
                    "ask_size_1": row[7],
                    "spread": row[8],
                    "spread_bps": row[9],
                    "mid_price": row[10],
                    "micro_price": row[11],
                    "order_flow_imbalance": row[12],
                    "depth_json": json.loads(row[13]) if row[13] else {},
                }
        return None

    def bulk_insert_quant_aggregates(self, aggregates: List[Dict[str, Any]]) -> int:
        """
        Bulk inserts quantitative sliding-window aggregates computed by Spark/stream processor.
        """
        if not aggregates:
            return 0
        cleaned = []
        for a in aggregates:
            ws = a.get("window_start")
            we = a.get("window_end")
            if isinstance(ws, str):
                ws = datetime.fromisoformat(ws.replace("Z", "+00:00"))
            if isinstance(we, str):
                we = datetime.fromisoformat(we.replace("Z", "+00:00"))
            cleaned.append({
                "window_start": ws,
                "window_end": we,
                "symbol": a["symbol"],
                "horizon": str(a.get("horizon", "10s")),
                "vwap": float(a.get("vwap", 0.0)),
                "order_flow_imbalance": float(a.get("order_flow_imbalance", 0.0)),
                "micro_price": float(a.get("micro_price", 0.0)),
                "realized_volatility": float(a.get("realized_volatility", 0.0)),
                "cumulative_volume_delta": float(a.get("cumulative_volume_delta", 0.0)),
                "trade_count": int(a.get("trade_count", 0)),
                "total_volume": float(a.get("total_volume", 0.0)),
                "created_at": datetime.utcnow(),
            })
        with self.engine.begin() as conn:
            conn.execute(quant_aggregates_table.insert(), cleaned)
        return len(cleaned)

    def get_latest_quant_aggregates(
        self, symbol: str, horizon: str = "10s", limit: int = 50
    ) -> pd.DataFrame:
        """
        Retrieves the most recent quantitative sliding-window aggregates for a given symbol.
        """
        query = """
        SELECT aggregate_id, window_start, window_end, symbol, horizon,
               vwap, order_flow_imbalance, micro_price, realized_volatility,
               cumulative_volume_delta, trade_count, total_volume, created_at
        FROM realtime_quant_aggregates
        WHERE symbol = :sym AND horizon = :hor
        ORDER BY window_end DESC, aggregate_id DESC
        LIMIT :lim;
        """
        with self.engine.connect() as conn:
            df = pd.read_sql(
                text(query),
                conn,
                params={"sym": symbol, "hor": horizon, "lim": limit},
            )
        return df

    def get_market_db_stats(self) -> Dict[str, Any]:
        """Returns metadata summary of the financial database."""
        stats = {}
        with self.engine.connect() as conn:
            stats["instruments_count"] = conn.execute(text("SELECT COUNT(*) FROM instruments")).scalar() or 0
            stats["exchanges_count"] = conn.execute(text("SELECT COUNT(*) FROM exchanges")).scalar() or 0
            stats["trades_count"] = conn.execute(text("SELECT COUNT(*) FROM trades_fact")).scalar() or 0
            stats["snapshots_count"] = conn.execute(text("SELECT COUNT(*) FROM orderbook_l2_snapshots")).scalar() or 0
            stats["positions_count"] = conn.execute(text("SELECT COUNT(*) FROM portfolio_positions")).scalar() or 0
            stats["risk_events_count"] = conn.execute(text("SELECT COUNT(*) FROM risk_events")).scalar() or 0
            stats["quant_aggregates_count"] = conn.execute(text("SELECT COUNT(*) FROM realtime_quant_aggregates")).scalar() or 0

            time_res = conn.execute(
                text("SELECT MIN(timestamp), MAX(timestamp) FROM trades_fact")
            ).fetchone()
            stats["earliest_trade"] = str(time_res[0]) if time_res and time_res[0] else "N/A"
            stats["latest_trade"] = str(time_res[1]) if time_res and time_res[1] else "N/A"

        return stats


if __name__ == "__main__":
    db = MarketDatabaseManager()
    db.init_db()
    n_inst, n_exch = db.seed_dimensions()
    print(f"[Market DB] Seeded {n_inst} instruments and {n_exch} exchanges.")
    stats = db.get_market_db_stats()
    print(f"[Market DB Stats] {stats}")
