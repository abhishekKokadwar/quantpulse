"""
QuantPulse: Partitioned Parquet Market Lakehouse Exporter
=========================================================
Exports high-frequency tick and order book datasets into a Snappy-compressed,
columnar Data Lakehouse layout partitioned by:
data/lake/raw_ticks/asset_class=<class>/symbol=<symbol>/year=<YYYY>/month=<MM>/day=<DD>/

Also supports flat CSV baseline persistence and lake health metadata auditing.
"""

import csv
import glob
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def sanitize_symbol_for_path(symbol: str) -> str:
    """Converts symbols with slashes (e.g. 'BTC/USDT') to safe path tokens ('BTC-USDT')."""
    return symbol.replace("/", "-")


class TickLakeExporter:
    """
    Exports market tick and order book data into partitioned Parquet lakehouse structures.
    """

    def __init__(self, lake_root: Optional[str] = None):
        self.lake_root = lake_root or os.path.join(PROJECT_ROOT, "data", "lake", "raw_ticks")
        os.makedirs(self.lake_root, exist_ok=True)

    def export_to_parquet(
        self,
        records: List[Dict[str, Any]],
        partition_cols: Optional[List[str]] = None,
        compression: str = "snappy",
    ) -> str:
        """
        Exports a list of trade tick dictionaries into the partitioned Parquet lakehouse.
        Applies Hive-style directory partitioning:
        `asset_class=<class>/symbol=<clean_symbol>/year=<YYYY>/month=<MM>/day=<DD>/`
        """
        if not records:
            return self.lake_root

        df = pd.DataFrame(records)

        # Ensure datetime parsing for year, month, day extraction
        if "timestamp" in df.columns:
            df["dt"] = pd.to_datetime(df["timestamp"])
            df["year"] = df["dt"].dt.year.astype(str)
            df["month"] = df["dt"].dt.month.map(lambda m: f"{m:02d}")
            df["day"] = df["dt"].dt.day.map(lambda d: f"{d:02d}")
            df.drop(columns=["dt"], inplace=True)
        else:
            now = datetime.now(timezone.utc)
            df["year"] = str(now.year)
            df["month"] = f"{now.month:02d}"
            df["day"] = f"{now.day:02d}"

        # Sanitize symbol for directory creation (e.g. BTC/USDT -> BTC-USDT)
        if "symbol" in df.columns:
            df["symbol_clean"] = df["symbol"].apply(sanitize_symbol_for_path)
        else:
            df["symbol_clean"] = "UNKNOWN"

        if partition_cols is None:
            partition_cols = ["asset_class", "symbol_clean", "year", "month", "day"]

        # Convert to PyArrow table
        table = pa.Table.from_pandas(df, preserve_index=False)

        # Write partitioned dataset
        pq.write_to_dataset(
            table,
            root_path=self.lake_root,
            partition_cols=partition_cols,
            compression=compression,
            use_dictionary=True,
        )

        return self.lake_root

    def export_to_csv(self, records: List[Dict[str, Any]], output_path: str, overwrite: bool = True) -> str:
        """Exports ticks to a flat CSV file."""
        if not records:
            return output_path

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        mode = "w" if overwrite else "a"

        headers = list(records[0].keys())
        # Filter out complex nested lists like 10-level order book if present in dict
        scalar_headers = [h for h in headers if not isinstance(records[0][h], (list, dict))]

        write_header = overwrite or not os.path.exists(output_path)
        with open(output_path, mode, newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=scalar_headers, extrasaction="ignore")
            if write_header:
                writer.writeheader()
            writer.writerows(records)

        return output_path

    def get_lake_metadata(self) -> Dict[str, Any]:
        """
        Inspects the partitioned lakehouse and returns storage KPIs.
        """
        if not os.path.exists(self.lake_root):
            return {"exists": False, "partitions": 0, "parquet_files": 0, "total_size_bytes": 0}

        parquet_files = glob.glob(os.path.join(self.lake_root, "**", "*.parquet"), recursive=True)
        total_size = sum(os.path.getsize(f) for f in parquet_files)

        # Extract discovered symbols and partition counts
        partitions = set(os.path.dirname(f) for f in parquet_files)
        symbols = set()
        for p in partitions:
            parts = p.replace("\\", "/").split("/")
            for part in parts:
                if part.startswith("symbol_clean="):
                    symbols.add(part.split("=")[1])

        return {
            "exists": True,
            "lake_root": self.lake_root,
            "total_parquet_files": len(parquet_files),
            "partition_count": len(partitions),
            "symbols_discovered": sorted(list(symbols)),
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024.0 * 1024.0), 3),
        }


if __name__ == "__main__":
    from simulator.market_simulator import MarketSimulator
    sim = MarketSimulator()
    print("Generating sample 100-tick batch across 3 symbols...")
    dataset = sim.generate_historical_dataset(days=1, ticks_per_symbol=50, symbols=["BTC/USDT", "AAPL", "EUR/USD"])

    exporter = TickLakeExporter()
    lake_dir = exporter.export_to_parquet(dataset)
    print(f"Parquet export complete to: {lake_dir}")
    meta = exporter.get_lake_metadata()
    print("Lake Metadata:", meta)
