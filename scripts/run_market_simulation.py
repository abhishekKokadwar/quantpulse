"""
QuantPulse: Command-Line Market Simulation Runner
=================================================
Runs high-speed multi-asset market simulation across 42 instruments,
exports partitioned Parquet and flat CSV tick stores, and outputs
statistical distribution and microstructure benchmarks.

Usage Examples:
python scripts/run_market_simulation.py --ticks-per-symbol 500 --export-parquet --stats
python scripts/run_market_simulation.py --symbols BTC/USDT,ETH/USDT,AAPL,SPY,EUR/USD --ticks-per-symbol 1000 --export-csv
python scripts/run_market_simulation.py --benchmark
"""

import argparse
import os
import sys
import time

# Ensure UTF-8 output encoding on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pandas as pd
from analysis.quant_analytics import compute_microstructure_kpis
from simulator.market_simulator import INSTRUMENT_REGISTRY, MarketSimulator
from simulator.tick_lake_exporter import TickLakeExporter


def run_simulation(args):
    symbols = args.symbols.split(",") if args.symbols else list(INSTRUMENT_REGISTRY.keys())
    print("=" * 70)
    print(f"[QuantPulse] Market Simulator: Simulating {len(symbols)} Instruments")
    print(f"Target Universe: {len(symbols)} symbols | Ticks per symbol: {args.ticks_per_symbol}")
    print("=" * 70)

    sim = MarketSimulator(seed=args.seed)

    start_time = time.perf_counter()
    records = sim.generate_historical_dataset(
        days=args.days,
        ticks_per_symbol=args.ticks_per_symbol,
        symbols=symbols,
    )
    elapsed = time.perf_counter() - start_time
    total_ticks = len(records)
    throughput = total_ticks / max(0.0001, elapsed)

    print(f"\n[OK] Simulation Complete: Generated {total_ticks:,} ticks across {len(symbols)} symbols in {elapsed:.3f}s")
    print(f"[Speed] Peak Simulation Throughput: {throughput:,.1f} ticks/second\n")

    exporter = TickLakeExporter()

    if args.export_parquet:
        lake_path = exporter.export_to_parquet(records)
        print(f"[Parquet] Lakehouse partition sink: {lake_path}")
        meta = exporter.get_lake_metadata()
        print(f"   * Total Files: {meta['total_parquet_files']} | Partitions: {meta['partition_count']} | Size: {meta['total_size_mb']} MB")

    if args.export_csv:
        csv_path = args.output_csv or os.path.join(PROJECT_ROOT, "data", "raw", "market_ticks.csv")
        exporter.export_to_csv(records, csv_path, overwrite=True)
        print(f"[CSV] Flat CSV Raw Tick store: {csv_path} ({len(records):,} rows)")

    if args.stats:
        df = pd.DataFrame(records)
        print("\n[Stats] Quantitative Microstructure & Moment Diagnostics:")
        print("-" * 70)
        sample_symbols = ["BTC/USDT", "AAPL", "SPY", "EUR/USD", "WTI/USD"]
        for sym in sample_symbols:
            if sym in symbols:
                sym_df = df[df["symbol"] == sym]
                kpis = compute_microstructure_kpis(sym_df)
                spread_bps = kpis.get("avg_spread_bps", "N/A")
                kurtosis = kpis.get("kurtosis", "N/A")
                is_lepto = kpis.get("is_leptokurtic", False)
                print(f"  * {sym:10s} | Trades: {len(sym_df):4d} | Spread: {spread_bps} bps | Kurtosis: {kurtosis} | Heavy-Tails: {is_lepto}")
        print("=" * 70)


def run_benchmark():
    print("=" * 70)
    print("[Benchmark] Running QuantPulse High-Throughput Simulation Benchmark...")
    print("=" * 70)
    sim = MarketSimulator(seed=123)
    symbols = list(INSTRUMENT_REGISTRY.keys())
    ticks_per_sym = 1000

    start = time.perf_counter()
    records = sim.generate_historical_dataset(days=1, ticks_per_symbol=ticks_per_sym, symbols=symbols)
    elapsed = time.perf_counter() - start

    rate = len(records) / max(0.0001, elapsed)
    print(f"Generated {len(records):,} ticks in {elapsed:.3f} seconds.")
    print(f"Benchmark Result: {rate:,.1f} ticks/sec")
    assert rate > 8000, f"Benchmark throughput too low: {rate}"
    print("[OK] Benchmark Passed! System comfortably exceeds high-frequency simulation targets.")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="QuantPulse High-Frequency Market Simulation Runner")
    parser.add_argument("--symbols", type=str, default=None, help="Comma-separated symbols list")
    parser.add_argument("--ticks-per-symbol", type=int, default=200, help="Ticks to generate per symbol")
    parser.add_argument("--days", type=int, default=1, help="Historical time span in days")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    parser.add_argument("--export-parquet", action="store_true", help="Export to partitioned Parquet lakehouse")
    parser.add_argument("--export-csv", action="store_true", help="Export to raw flat CSV")
    parser.add_argument("--output-csv", type=str, default=None, help="Path for flat CSV export")
    parser.add_argument("--stats", action="store_true", help="Display microstructure & distribution stats")
    parser.add_argument("--benchmark", action="store_true", help="Run performance benchmark only")

    args = parser.parse_args()

    if args.benchmark:
        run_benchmark()
    else:
        run_simulation(args)


if __name__ == "__main__":
    main()
