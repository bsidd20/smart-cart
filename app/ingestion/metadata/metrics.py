"""Observability metrics: row counts per table and data freshness, captured per
run into the ingestion_metrics table for dashboards / monitoring."""
from __future__ import annotations

import time
from datetime import datetime, timezone

import pandas as pd

from app.ingestion import io, paths

_TABLES = {
    "bronze.raw_products": paths.BRONZE_RAW_PRODUCTS,
    "bronze.raw_price_events": paths.BRONZE_RAW_PRICE_EVENTS,
    "silver.dim_product": paths.SILVER_DIM_PRODUCT,
    "silver.fact_inventory": paths.SILVER_FACT_INVENTORY,
    "gold.store_product_offers": paths.GOLD_OFFERS,
}


def capture(run_id: str) -> pd.DataFrame:
    now = datetime.now(timezone.utc)
    rows = []
    for name, path in _TABLES.items():
        if paths.exists(path):
            rows.append({"run_id": run_id, "metric": "row_count", "target": name,
                         "value": float(len(io.read_delta(path))),
                         "captured_at": now.isoformat()})

    # data freshness: hours since the newest product modification we hold
    prod = io.read_delta(paths.SILVER_DIM_PRODUCT)
    if len(prod):
        newest = int(prod["last_modified_t"].max())
        age_h = round((time.time() - newest) / 3600.0, 1)
        rows.append({"run_id": run_id, "metric": "freshness_hours",
                     "target": "silver.dim_product", "value": float(age_h),
                     "captured_at": now.isoformat()})

    df = pd.DataFrame(rows)
    io.write_delta(df, paths.META_METRICS, mode="append")
    return df
