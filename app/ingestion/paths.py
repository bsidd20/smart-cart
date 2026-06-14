"""Delta table locations for the ingestion platform.

Layers: bronze (raw), silver (clean), gold (serving), plus meta (run tracking,
watermarks, metrics) and quality (check results).
"""

from app.config import DATA_DIR

LAKE = DATA_DIR / "lake"
BRONZE = LAKE / "bronze"
SILVER = LAKE / "silver"
GOLD = LAKE / "gold"
META = LAKE / "meta"
QUALITY = LAKE / "quality"

# bronze: raw, as received
BRONZE_RAW_PRODUCTS = BRONZE / "raw_products"
BRONZE_RAW_STORES = BRONZE / "raw_stores"
BRONZE_RAW_PRICE_EVENTS = BRONZE / "raw_price_events"

# silver: clean, typed, deduplicated
SILVER_DIM_PRODUCT = SILVER / "dim_product"
SILVER_DIM_STORE = SILVER / "dim_store"
SILVER_FACT_INVENTORY = SILVER / "fact_inventory"

# gold: serving + analytics
GOLD_PRODUCT_CATALOG = GOLD / "product_catalog"
GOLD_OFFERS = GOLD / "store_product_offers"
GOLD_CATEGORY_PRICE_STATS = GOLD / "category_price_stats"
GOLD_CHEAPEST_PRODUCTS = GOLD / "cheapest_products"
GOLD_PRODUCT_SEARCH_INDEX = GOLD / "product_search_index"

# meta: observability + incremental state
META_RUNS = META / "ingestion_runs"
META_WATERMARKS = META / "watermarks"
META_METRICS = META / "ingestion_metrics"
META_SCHEMA_DRIFT = META / "schema_drift"

# quality
QUALITY_RESULTS = QUALITY / "quality_results"
QUALITY_QUARANTINE = QUALITY / "quarantine"


def exists(table_path) -> bool:
    return (table_path / "_delta_log").is_dir()
