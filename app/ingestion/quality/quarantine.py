"""Quarantine bad records instead of silently dropping them.

Malformed Bronze records (missing barcode or product name) are written to a
quarantine table with a reason and the run id, so they can be inspected, reported,
and replayed once fixed. Silver then only consumes clean records.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.ingestion import io, paths


def quarantine_bad_products(run_id: str) -> int:
    bronze = io.read_delta(paths.BRONZE_RAW_PRODUCTS)
    bad = bronze[
        (bronze["barcode"].str.len() == 0) | (bronze["product_name"].str.len() == 0)
    ].copy()
    if bad.empty:
        return 0
    bad["quarantine_reason"] = "empty barcode or product_name"
    bad["quarantined_at"] = datetime.now(timezone.utc).isoformat()
    bad["run_id"] = run_id
    keep = [
        "run_id",
        "barcode",
        "product_name",
        "taxonomy_key",
        "quarantine_reason",
        "quarantined_at",
    ]
    io.write_delta(bad[keep], paths.QUALITY_QUARANTINE, mode="append")
    return len(bad)
