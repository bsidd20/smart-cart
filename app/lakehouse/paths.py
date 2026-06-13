"""Table locations for the Bronze/Silver/Gold lakehouse.

Each table is a Delta Lake directory (data + a _delta_log transaction log).
"""
from app.config import DATA_DIR

LAKE = DATA_DIR / "lake"
BRONZE = LAKE / "bronze"
SILVER = LAKE / "silver"
GOLD = LAKE / "gold"

# bronze: raw, as-ingested
BRONZE_STORES = BRONZE / "stores"
BRONZE_PRODUCTS = BRONZE / "products"
BRONZE_PRICE_EVENTS = BRONZE / "price_events"

# silver: cleaned, typed, deduplicated
SILVER_DIM_STORE = SILVER / "dim_store"
SILVER_DIM_PRODUCT = SILVER / "dim_product"
SILVER_FACT_INVENTORY = SILVER / "fact_inventory"

# gold: serving + analytics
GOLD_OFFERS = GOLD / "store_product_offers"
GOLD_PRICE_STATS = GOLD / "product_price_stats"
GOLD_STORE_INDEX = GOLD / "store_price_index"


def exists(table_path) -> bool:
    return (table_path / "_delta_log").is_dir()
