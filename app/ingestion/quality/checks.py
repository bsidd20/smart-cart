"""Data quality checks. Each check appends a row to the quality_results table so
failures are auditable per run. Checks run after the transforms.

A check records: how many rows failed, out of how many, and a severity. "error"
means the layer's contract is broken (e.g. duplicate keys in a deduped table);
"warn" means real-world noise we tolerate but want visibility into.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from app.ingestion import io, paths


def _valid_gtin(code: str) -> bool:
    """GTIN-8/12/13/14 check-digit validation (UPC-A and EAN-13 included)."""
    digits = "".join(ch for ch in str(code) if ch.isdigit())
    if len(digits) not in (8, 12, 13, 14):
        return False
    nums = [int(c) for c in digits]
    body = nums[:-1][::-1]
    total = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(body))
    return (10 - total % 10) % 10 == nums[-1]


def _result(run_id, check, layer, table, severity, failed, total, detail):
    return {"run_id": run_id, "check_name": check, "layer": layer, "table": table,
            "severity": severity, "failed_count": int(failed), "total_count": int(total),
            "passed": bool(failed == 0), "detail": detail,
            "checked_at": datetime.now(timezone.utc).isoformat()}


def run_checks(run_id: str) -> pd.DataFrame:
    bronze = io.read_delta(paths.BRONZE_RAW_PRODUCTS)
    silver = io.read_delta(paths.SILVER_DIM_PRODUCT)
    offers = io.read_delta(paths.GOLD_OFFERS)
    rows = []

    # 1) malformed raw records: missing barcode or name (expected: some)
    bad = ((bronze["barcode"].str.len() == 0) | (bronze["product_name"].str.len() == 0)).sum()
    rows.append(_result(run_id, "malformed_records", "bronze", "raw_products",
                        "warn", bad, len(bronze), "empty barcode or product_name"))

    # 2) duplicate products in the deduped dimension (expected: 0)
    dups = int(silver["barcode"].duplicated().sum())
    rows.append(_result(run_id, "duplicate_products", "silver", "dim_product",
                        "error", dups, len(silver), "barcode must be unique"))

    # 3) missing categories in the serving catalog (expected: 0)
    miss = int(silver["category"].isna().sum() + (silver["category"].astype(str).str.len() == 0).sum())
    rows.append(_result(run_id, "missing_categories", "silver", "dim_product",
                        "error", miss, len(silver), "category must be set"))

    # 4) invalid UPCs / barcodes (real-world noise; warn)
    invalid = int((~silver["barcode"].map(_valid_gtin)).sum())
    rows.append(_result(run_id, "invalid_upcs", "silver", "dim_product",
                        "warn", invalid, len(silver), "GTIN check-digit failed"))

    # 5) invalid prices in the serving table (expected: 0)
    badp = int(((offers["price"].isna()) | (offers["price"] <= 0) | (offers["price"] > 1000)).sum())
    rows.append(_result(run_id, "invalid_prices", "gold", "store_product_offers",
                        "error", badp, len(offers), "price must be in (0, 1000]"))

    df = pd.DataFrame(rows)
    io.write_delta(df, paths.QUALITY_RESULTS, mode="append")
    return df
