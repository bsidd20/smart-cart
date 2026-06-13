"""Runs the lakehouse end to end: raw feeds -> bronze -> silver -> gold."""
from __future__ import annotations

import shutil

from app.data import simulator
from app.lakehouse import bronze, gold, io, paths, silver


def build(seed: int = 42, clean: bool = True, verbose: bool = False) -> None:
    if clean and paths.LAKE.exists():
        shutil.rmtree(paths.LAKE)

    raw = simulator.generate_raw(seed=seed)
    bronze.ingest(raw)
    silver.build()
    gold.build()

    if verbose:
        for label, p in [("bronze.stores", paths.BRONZE_STORES),
                         ("bronze.products", paths.BRONZE_PRODUCTS),
                         ("bronze.price_events", paths.BRONZE_PRICE_EVENTS),
                         ("silver.dim_store", paths.SILVER_DIM_STORE),
                         ("silver.dim_product", paths.SILVER_DIM_PRODUCT),
                         ("silver.fact_inventory", paths.SILVER_FACT_INVENTORY),
                         ("gold.store_product_offers", paths.GOLD_OFFERS),
                         ("gold.product_price_stats", paths.GOLD_PRICE_STATS),
                         ("gold.store_price_index", paths.GOLD_STORE_INDEX)]:
            rows = len(io.read_delta(p))
            print(f"  {label:<28} v{io.table_version(p)}  {rows:>5} rows")


def is_built() -> bool:
    return paths.exists(paths.GOLD_OFFERS)
