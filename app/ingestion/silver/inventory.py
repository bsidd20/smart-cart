"""Silver fact_inventory: the current price per (store, product).

Takes the latest price event per (store_id, barcode) from the event stream and
upserts it, so a newer price event for an existing pair updates the row (this is
the realistic incremental case - prices change far more often than products).
"""

from __future__ import annotations

from app.ingestion import io, paths


def build() -> int:
    latest = io.sql(
        """
        WITH ranked AS (
            SELECT *, row_number() OVER (
                PARTITION BY store_id, barcode ORDER BY observed_at DESC) AS rn
            FROM bronze
        )
        SELECT store_id || '|' || barcode AS inv_key,
               store_id, barcode, CAST(price AS DOUBLE) AS price,
               in_stock, observed_at
        FROM ranked WHERE rn = 1
        """,
        bronze=paths.BRONZE_RAW_PRICE_EVENTS,
    )
    io.upsert_delta(latest, paths.SILVER_FACT_INVENTORY, key="inv_key")
    return len(latest)
