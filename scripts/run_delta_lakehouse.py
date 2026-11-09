"""
QuantPulse: ACID Market Lakehouse CLI Runner (Delta Lake + DuckDB)
===================================================================
Executes and validates Phase 8 operations:
1. Atomic initialization from multi-asset cold-path Parquet ticks
2. Streaming micro-batch appends with strict version increments
3. Non-destructive schema evolution for derivatives microstructure signals
4. In-place compaction and multi-dimensional Z-ordering on (symbol, timestamp)
5. Zero-lookahead deterministic backtesting across historical snapshots
6. Transaction log auditing and snapshot comparison
"""

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Add project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from analysis.delta_tick_lakehouse import (
    DeltaTickLakehouseManager,
    get_delta_tick_lakehouse,
    DEFAULT_DELTA_PATH,
)
from analysis.backtest_engine import ZeroLookaheadBacktestEngine


# Ensure UTF-8 output encoding for Windows terminals
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

def print_banner(title: str):
    print("\n" + "=" * 78)
    print(f"  [QUANTPULSE] {title}")
    print("=" * 78)


def format_table(headers: List[str], rows: List[List[Any]]) -> str:
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(val)))

    header_line = " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    sep_line = "-+-".join("-" * col_widths[i] for i in range(len(headers)))
    row_lines = [
        " | ".join(str(val).ljust(col_widths[i]) for i, val in enumerate(row))
        for row in rows
    ]
    return f"{header_line}\n{sep_line}\n" + "\n".join(row_lines)


def run_init(mgr: DeltaTickLakehouseManager, max_records: Optional[int] = None) -> Dict[str, Any]:
    print_banner("INITIALIZING ACID DELTA LAKEHOUSE TABLE")
    res = mgr.initialize_from_parquet(max_records=max_records)
    print(f"Status:            {res['status']}")
    print(f"Table Path:        {res['table_path']}")
    print(f"Initial Version:   {res['version']}")
    print(f"Total Ticks:       {res['total_records']:,}")
    print(f"Partitions:        {res['partitions']}")
    print(f"Elapsed Time:      {res['elapsed_sec']}s")
    return res


def run_append(mgr: DeltaTickLakehouseManager, count: int = 10) -> Dict[str, Any]:
    print_banner("APPENDING STREAMING MICRO-BATCH")
    now = datetime.now(timezone.utc)
    import pandas as pd

    sample_ticks = []
    for i in range(count):
        sample_ticks.append({
            "trade_id": int(now.timestamp() * 1000) + i + 1,
            "symbol": "BTC/USDT",
            "exchange": "binance",
            "timestamp": now,
            "price": 83500.0 + (i * 2.5),
            "quantity": 0.5 + (i * 0.1),
            "side": "BUY" if i % 2 == 0 else "SELL",
            "is_buyer_maker": bool(i % 3 == 0),
            "liquidation": False,
            "notional_usd": (83500.0 + (i * 2.5)) * (0.5 + (i * 0.1)),
            "bid_1": 83499.0,
            "ask_1": 83501.0,
            "spread": 2.0,
            "mid_price": 83500.0,
            "micro_price": 83500.2,
            "order_flow_imbalance": 0.35,
            "asset_class": "crypto",
            "symbol_clean": "BTC-USDT",
            "year": now.year,
            "month": now.month,
            "day": now.day,
        })

    df = pd.DataFrame(sample_ticks)
    res = mgr.append_batch(df, schema_mode="merge")
    print(f"Status:            {res['status']}")
    print(f"Operation:         {res['operation']}")
    print(f"Records Appended:  {res['records_appended']}")
    print(f"New Version:       {res['new_version']}")
    print(f"Latency:           {res['elapsed_ms']} ms")
    return res


def run_schema_evolution(mgr: DeltaTickLakehouseManager) -> Dict[str, Any]:
    print_banner("SIMULATING NON-DESTRUCTIVE SCHEMA EVOLUTION")
    res = mgr.simulate_schema_evolution(batch_size=28)
    print(f"Status:            {res['status']}")
    print(f"Operation:         {res['operation']}")
    print(f"Evolved Columns:   {', '.join(res['new_columns_introduced'])}")
    print(f"Records Appended:  {res['records_appended']}")
    print(f"New Version:       {res['new_version']}")
    print(f"Latency:           {res['elapsed_ms']} ms")
    return res


def run_optimize(mgr: DeltaTickLakehouseManager) -> Dict[str, Any]:
    print_banner("EXECUTING COMPACTION & Z-ORDERING OPTIMIZATION")
    res = mgr.optimize_and_compact(z_order_columns=["symbol", "timestamp"])
    print(f"Status:            {res['status']}")
    print(f"Operation:         {res['operation']}")
    print(f"Target Dimensions: {res['z_order_columns']}")
    print(f"New Version:       {res['new_version']}")
    print(f"Elapsed Time:      {res['elapsed_sec']}s")
    if res.get("compact_metrics"):
        print(f"Compaction Stats:  {res['compact_metrics']}")
    if res.get("z_order_metrics"):
        print(f"Z-Order Stats:     {res['z_order_metrics']}")
    return res


def run_audit(mgr: DeltaTickLakehouseManager) -> None:
    print_banner("DELTA LAKE TRANSACTION LOG AUDIT HISTORY (_delta_log)")
    history = mgr.get_commit_history()
    headers = ["Version", "Operation", "Timestamp (UTC)", "Engine"]
    rows = []
    for h in history[:15]:
        rows.append([h["version"], h["operation"], h["timestamp"], h["engineInfo"]])
    print(format_table(headers, rows))

    if len(history) > 1:
        v_latest = history[0]["version"]
        diff = mgr.compare_snapshots(version_a=0, version_b=v_latest)
        print("\n--- Snapshot Differential (V0 -> V_Latest) ---")
        print(f"Row Delta:         +{diff['row_delta']:,} rows ({diff['rows_a']} -> {diff['rows_b']})")
        print(f"Schema Evolved:    {diff['schema_evolved']}")
        if diff["added_columns"]:
            print(f"New Columns Added: {', '.join(diff['added_columns'])}")


def run_backtest_cli(
    mgr: DeltaTickLakehouseManager,
    symbol: str = "BTC/USDT",
    strategy: str = "order_flow_momentum",
    version: Optional[int] = None,
) -> None:
    print_banner(f"ZERO-LOOKAHEAD BACKTEST: {symbol} [{strategy.upper()}]")
    engine = ZeroLookaheadBacktestEngine(mgr)
    metrics, trades = engine.run_backtest(
        symbol=symbol,
        strategy=strategy,
        version=version,
    )

    m = metrics.to_dict()
    print(f"Snapshot Version:  {m['version_queried']}")
    print(f"Ticks Scanned:     {m['total_ticks_scanned']:,}")
    print(f"Total Trades:      {m['total_trades']}")
    print(f"Win Rate:          {m['win_rate_pct']}% ({m['winning_trades']}W / {m['losing_trades']}L)")
    print(f"Initial Capital:   ${m['initial_capital']:,.2f}")
    print(f"Final Equity:      ${m['final_equity']:,.2f}")
    print(f"Total Net PnL:     ${m['total_net_pnl']:+,.2f} ({m['total_return_pct']:+.2f}%)")
    print(f"Sharpe Ratio:      {m['sharpe_ratio']:.4f}")
    print(f"Sortino Ratio:     {m['sortino_ratio']:.4f}")
    print(f"Max Drawdown:      {m['max_drawdown_pct']:.2f}%")
    print(f"Profit Factor:     {m['profit_factor']:.2f}")
    print(f"Fees Paid:         ${m['total_fees_paid']:,.2f}")
    print(f"Slippage Incurred: ${m['total_slippage_cost']:,.2f}")
    print(f"Execution Latency: {m['elapsed_ms']:.2f} ms")
    print(f"Zero Lookahead:    [OK] {m['lookahead_free']}")


def run_full_pipeline(mgr: DeltaTickLakehouseManager) -> None:
    print_banner("QUANT PULSE PHASE 8 COMPLETE BENCHMARK & VALIDATION PIPELINE")
    t0 = time.time()

    # 1. Initialize
    run_init(mgr, max_records=10000)

    # 2. Append Micro-batch
    run_append(mgr, count=10)

    # 3. Schema Evolution
    run_schema_evolution(mgr)

    # 4. Compaction & Z-Ordering
    run_optimize(mgr)

    # 5. Audit History
    run_audit(mgr)

    # 6. Backtest
    run_backtest_cli(mgr, symbol="BTC/USDT", strategy="order_flow_momentum", version=0)

    # 7. Mathematical Invariant Proof
    print_banner("MATHEMATICAL PROOF: ZERO LOOKAHEAD BIAS INVARIANT")
    engine = ZeroLookaheadBacktestEngine(mgr)
    inv = engine.verify_zero_lookahead_invariant(symbol="BTC/USDT", base_version=0)
    print(f"Base Version Queried:        {inv['base_version']}")
    print(f"Latest Active Table Version: {inv['latest_table_version']}")
    print(f"Trade Count Match:           {inv['trades_count_v1']} == {inv['trades_count_v2']}")
    print(f"Net PnL Delta:               ${inv['pnl_diff']:.8f}")
    print(f"Sharpe Delta:                {abs(inv['sharpe_v1'] - inv['sharpe_v2']):.8f}")
    print(f"Invariant Preserved:         {'[OK] TRUE (Zero Lookahead Proven)' if inv['invariant_preserved'] else '[FAIL] FALSE'}")

    # 8. Lakehouse Stats
    stats = mgr.get_lakehouse_stats()
    print_banner("DELTA LAKEHOUSE SYSTEM HEALTH & METRICS")
    print(f"Table Version:     {stats['version']}")
    print(f"Active Files:      {stats['active_files']}")
    print(f"Total Size:        {stats['total_size_mb']} MB")
    print(f"Total Commits:     {stats['total_commits']}")
    print(f"Pipeline Runtime:  {round(time.time() - t0, 2)}s")


def main():
    parser = argparse.ArgumentParser(description="QuantPulse ACID Delta Lakehouse Runner (Phase 8)")
    parser.add_argument("--init", action="store_true", help="Initialize Delta Lake table from Parquet")
    parser.add_argument("--append", action="store_true", help="Append streaming micro-batch")
    parser.add_argument("--evolve", action="store_true", help="Simulate non-destructive schema evolution")
    parser.add_argument("--optimize", action="store_true", help="Run compaction and Z-ordering on (symbol, timestamp)")
    parser.add_argument("--audit", action="store_true", help="Print commit log audit history")
    parser.add_argument("--backtest", action="store_true", help="Execute deterministic backtest on snapshot")
    parser.add_argument("--symbol", type=str, default="BTC/USDT", help="Trading symbol for backtest")
    parser.add_argument("--strategy", type=str, default="order_flow_momentum", help="Strategy name")
    parser.add_argument("--version", type=int, default=None, help="Snapshot version to query")
    parser.add_argument("--all", action="store_true", help="Run complete end-to-end pipeline & benchmarks")

    args = parser.parse_args()
    mgr = get_delta_tick_lakehouse()

    if args.all or not any([args.init, args.append, args.evolve, args.optimize, args.audit, args.backtest]):
        run_full_pipeline(mgr)
    else:
        if args.init:
            run_init(mgr)
        if args.append:
            run_append(mgr)
        if args.evolve:
            run_schema_evolution(mgr)
        if args.optimize:
            run_optimize(mgr)
        if args.audit:
            run_audit(mgr)
        if args.backtest:
            run_backtest_cli(mgr, symbol=args.symbol, strategy=args.strategy, version=args.version)


if __name__ == "__main__":
    main()
