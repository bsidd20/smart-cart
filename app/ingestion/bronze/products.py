"""Bronze: land raw product records exactly as received, append-only.

We add ingestion metadata (run id, timestamp, source system, schema version) but
do not clean or dedupe here. Bronze is the replay log; Silver derives current state.
"""

from __future__ import annotations

import pandas as pd

from app.ingestion import io, paths


def land(records: list[dict], run: dict) -> int:
    if not records:
        return 0
    df = pd.DataFrame(records)
    df["run_id"] = run["run_id"]
    df["ingested_at"] = run["started_at"]
    df["source_system"] = run["source"]
    df["schema_version"] = run.get("schema_version", "off_v2")
    # partition by category so per-category reads prune to one directory
    io.write_delta(df, paths.BRONZE_RAW_PRODUCTS, mode="append", partition_by=["taxonomy_key"])
    return len(df)
