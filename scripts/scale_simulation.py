"""Scale simulation: generate millions of price events and benchmark partition
pruning and compaction at a size where wall-clock actually means something.

    python scripts/scale_simulation.py [rows] [days] [batches]
    python scripts/scale_simulation.py 2000000 30 40

Runs fully locally on delta-rs + DuckDB (no Spark/JVM needed). The same partitioning
and compaction concepts are what Spark/Photon and Snowflake apply at cluster scale;
see docs/SCALE.md.
"""

import shutil
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import duckdb
import numpy as np
import pyarrow as pa
from deltalake import DeltaTable, write_deltalake

TABLE = Path("data/lake/scale/price_events")


def generate(n_rows: int, n_days: int, seed: int = 7) -> pa.Table:
    rng = np.random.default_rng(seed)
    dates = [(date(2024, 1, 1) + timedelta(days=i)).isoformat() for i in range(n_days)]
    day_idx = rng.integers(0, n_days, n_rows)
    event_date = np.array(dates, dtype=object)[day_idx]
    return pa.table(
        {
            "event_id": np.arange(n_rows, dtype=np.int64),
            "store_id": rng.integers(0, 50, n_rows).astype(np.int32),
            "product_id": rng.integers(0, 5000, n_rows).astype(np.int32),
            "price": rng.uniform(0.5, 20.0, n_rows).round(2),
            "in_stock": rng.random(n_rows) < 0.95,
            "event_date": pa.array(event_date, type=pa.string()),
        }
    )


def file_count() -> int:
    return len(DeltaTable(str(TABLE)).file_uris())


def main():
    rows = int(sys.argv[1]) if len(sys.argv) > 1 else 2_000_000
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    batches = int(sys.argv[3]) if len(sys.argv) > 3 else 40

    print(f"generating {rows:,} price events over {days} days in {batches} micro-batches...")
    tbl = generate(rows, days)
    shutil.rmtree(TABLE, ignore_errors=True)
    TABLE.parent.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    for i, chunk in enumerate(np.array_split(np.arange(rows), batches)):
        write_deltalake(
            str(TABLE),
            tbl.take(pa.array(chunk)),
            mode="overwrite" if i == 0 else "append",
            partition_by=["event_date"],
            schema_mode="overwrite" if i == 0 else None,
        )
    print(f"wrote {rows:,} rows partitioned by event_date in {time.perf_counter() - t0:.1f}s")

    con = duckdb.connect()
    con.execute("INSTALL delta")
    con.execute("LOAD delta")
    p = str(TABLE)

    def timed(sql, n=5):
        best = float("inf")
        for _ in range(n):
            t = time.perf_counter()
            con.execute(sql).fetchall()
            best = min(best, (time.perf_counter() - t) * 1000)
        return best

    one_day = (date(2024, 1, 1) + timedelta(days=days // 2)).isoformat()
    full_q = f"select count(*), avg(price) from delta_scan('{p}')"
    pruned_q = f"select count(*), avg(price) from delta_scan('{p}') where event_date = '{one_day}'"

    print("\n=== PARTITION PRUNING (small files) ===")
    small_files = file_count()
    full_small = timed(full_q)
    pruned_small = timed(pruned_q)
    print(
        f"  files: {small_files} | full scan {full_small:.0f} ms | "
        f"one-day pruned {pruned_small:.0f} ms ({full_small / pruned_small:.1f}x faster)"
    )

    print("\n=== COMPACTION ===")
    t = time.perf_counter()
    metrics = DeltaTable(str(TABLE)).optimize.compact()
    big_files = file_count()
    print(
        f"  compacted {small_files} -> {big_files} files in {time.perf_counter() - t:.1f}s "
        f"(removed {metrics.get('numFilesRemoved')})"
    )
    full_big = timed(full_q)
    pruned_big = timed(pruned_q)
    print(
        f"  after compaction: full scan {full_big:.0f} ms ({full_small / full_big:.1f}x faster) | "
        f"one-day pruned {pruned_big:.0f} ms"
    )

    print(
        "\nsummary: partitioning skips ~{:.0f}% of data per-day; compaction cut files "
        "{:.0f}x and sped full scans {:.1f}x.".format(
            100 * (1 - 1 / days), small_files / max(big_files, 1), full_small / full_big
        )
    )


if __name__ == "__main__":
    main()
