"""Table maintenance: compact small files and Z-order hot tables.

Streaming and incremental loads create many small files; this runs after ingestion
(the Airflow DAG's optimize task) to keep file counts and query latency in check.

    python -m app.ingestion.maintenance
"""

from __future__ import annotations

from app.ingestion import io, paths

# (table, z-order columns or None)
TARGETS = [
    (paths.BRONZE_RAW_PRODUCTS, None),
    (paths.BRONZE_RAW_PRICE_EVENTS, None),
    (paths.GOLD_OFFERS, ["store_id"]),
]


def run() -> None:
    for path, zcols in TARGETS:
        if not paths.exists(path):
            continue
        before = io.file_count(path)
        io.compact(path)
        if zcols:
            io.zorder(path, zcols)
        print(f"optimized {path.name}: {before} -> {io.file_count(path)} files")


if __name__ == "__main__":
    run()
