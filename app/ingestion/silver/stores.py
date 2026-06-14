"""Silver store dimension: dedupe by store_id, trim, validate coordinates."""

from __future__ import annotations

from app.ingestion import io, paths


def build() -> int:
    dim = io.sql(
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
        bronze=paths.BRONZE_RAW_STORES,
    )
    io.upsert_delta(dim, paths.SILVER_DIM_STORE, key="store_id")
    return len(dim)
