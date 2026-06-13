"""Silver: clean, typed, deduplicated tables built from Bronze with DuckDB SQL.

dim_store / dim_product keep one row per key (latest ingested), trimmed and validated.
fact_inventory keeps the latest price event per (store, product) - the current state
derived from the event stream.
"""
from __future__ import annotations

from app.lakehouse import io, paths


def build() -> None:
    dim_store = io.sql(
        """
        WITH ranked AS (
            SELECT *, row_number() OVER (
                PARTITION BY store_id ORDER BY ingested_at DESC) AS rn
            FROM bronze
        )
        SELECT store_id, trim(name) AS name, trim(chain) AS chain,
               CAST(lat AS DOUBLE) AS lat, CAST(lon AS DOUBLE) AS lon
        FROM ranked
        WHERE rn = 1 AND lat IS NOT NULL AND lon IS NOT NULL
        """,
        bronze=paths.BRONZE_STORES,
    )
    io.write_delta(dim_store, paths.SILVER_DIM_STORE)

    dim_product = io.sql(
        """
        WITH ranked AS (
            SELECT *, row_number() OVER (
                PARTITION BY product_id ORDER BY ingested_at DESC) AS rn
            FROM bronze
        )
        SELECT product_id, trim(raw_name) AS name, category, unit, search_terms
        FROM ranked
        WHERE rn = 1
        """,
        bronze=paths.BRONZE_PRODUCTS,
    )
    io.write_delta(dim_product, paths.SILVER_DIM_PRODUCT)

    fact_inventory = io.sql(
        """
        WITH ranked AS (
            SELECT *, row_number() OVER (
                PARTITION BY store_id, product_id ORDER BY observed_at DESC) AS rn
            FROM bronze
        )
        SELECT store_id, product_id, CAST(price AS DOUBLE) AS price,
               in_stock, observed_at
        FROM ranked
        WHERE rn = 1
        """,
        bronze=paths.BRONZE_PRICE_EVENTS,
    )
    io.write_delta(fact_inventory, paths.SILVER_FACT_INVENTORY)
