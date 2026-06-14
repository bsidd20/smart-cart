"""Demonstrates partition pruning and small-file compaction with before/after numbers.

    python scripts/benchmark.py

Data volumes here are tiny, so wall-clock times are not the point; the file-skip
ratios and file-count reductions are what hold as the data grows.
"""

import shutil
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402
from deltalake import DeltaTable  # noqa: E402

from app.ingestion import io, paths  # noqa: E402
from app.ingestion.orchestration import pipeline  # noqa: E402


def files_by_partition(path) -> tuple[int, Counter]:
    uris = DeltaTable(str(path)).file_uris()
    counts: Counter = Counter()
    for uri in uris:
        segs = [s for s in uri.split("/") if "=" in s]
        counts[segs[-1] if segs else "(unpartitioned)"] += 1
    return len(uris), counts


def rule(c="=", n=70):
    print(c * n)


def main():
    shutil.rmtree(paths.LAKE, ignore_errors=True)
    pipeline.run_fixture()

    rule()
    print("PARTITION PRUNING (gold.store_product_offers, partitioned by category)")
    rule()
    total, parts = files_by_partition(paths.GOLD_OFFERS)
    milk = parts.get("category=milk", 0)
    print(f"  {total} data files across {len(parts)} category partitions")
    if total and milk:
        skipped = 100 * (1 - milk / total)
        print(
            f"  a query WHERE category='milk' opens {milk}/{total} files "
            f"({skipped:.0f}% skipped before reading any data)"
        )
        print(
            "  this skip ratio is scale-invariant: at billions of rows it is the same "
            "fraction of I/O, scan cost, and warehouse compute avoided."
        )
    # (wall-clock is omitted: at 11 tiny files it is dominated by fixed overhead and a
    #  count(*) is answered from Delta metadata, so timing here would only mislead.)

    print()
    rule()
    print("SMALL-FILE COMPACTION (bronze.raw_products)")
    rule()
    before = io.file_count(paths.BRONZE_RAW_PRODUCTS)
    micro = pd.read_json(paths.LAKE.parent.parent / "tests/fixtures/off_products_sample.json")
    micro = (
        micro[micro["product_name"].str.len() > 0]
        .head(6)
        .assign(
            run_id="benchmark",
            ingested_at="2024-01-03T00:00:00",
            source_system="openfoodfacts",
            schema_version="off_v2",
        )
    )
    for _ in range(8):  # simulate 8 small incremental loads
        io.write_delta(
            micro, paths.BRONZE_RAW_PRODUCTS, mode="append", partition_by=["taxonomy_key"]
        )
    pressured = io.file_count(paths.BRONZE_RAW_PRODUCTS)
    metrics = io.compact(paths.BRONZE_RAW_PRODUCTS)
    after = io.file_count(paths.BRONZE_RAW_PRODUCTS)
    removed, added = metrics.get("numFilesRemoved"), metrics.get("numFilesAdded")
    print(f"  files: {before} -> {pressured} (8 micro-batch appends) -> {after} (compacted)")
    print(f"  compaction removed {removed} small files, wrote {added}")

    print()
    rule()
    print("Z-ORDER (gold.store_product_offers by store_id)")
    rule()
    zm = io.zorder(paths.GOLD_OFFERS, ["store_id"])
    print(
        f"  rewrote {zm.get('numFilesAdded')} file(s); co-locates rows for store-filtered queries"
    )


if __name__ == "__main__":
    main()
