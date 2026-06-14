"""Generates raw source data for the lakehouse.

Produces three feeds, deliberately a bit messy so the Silver layer has real work:
  - stores: a store directory (with a few re-ingested duplicate rows)
  - products: a supplier catalog (duplicates + stray whitespace)
  - price_events: timestamped price observations over several days, many per
    (store, product) pair, so Silver has to pick the latest

Seeded, so the data is identical every run. Replace this module with a scraper or a
real feed to use live data; the rest of the pipeline doesn't change.
"""

from __future__ import annotations

import random

from app.config import DEFAULT_USER_LAT, DEFAULT_USER_LON

# (name, category, base price, unit, [synonyms])
PRODUCT_UNIVERSE: list[tuple[str, str, float, str, list[str]]] = [
    ("Chicken Breast Fillets", "meat", 7.50, "kg", ["chicken breast", "chicken fillet", "chicken"]),
    (
        "White Basmati Rice 1kg",
        "grains",
        3.20,
        "kg",
        ["rice", "white rice", "basmati rice", "basmati"],
    ),
    ("Large Eggs (dozen)", "dairy", 3.00, "dozen", ["eggs", "egg", "large eggs", "dozen eggs"]),
    ("Whole Milk 1L", "dairy", 1.20, "L", ["milk", "whole milk", "dairy milk", "full fat milk"]),
    (
        "Baby Spinach 200g",
        "produce",
        2.20,
        "pack",
        ["spinach", "baby spinach", "fresh spinach", "leaf spinach"],
    ),
    # near-duplicates the matcher should NOT pick for the queries above
    ("Chicken Thighs", "meat", 5.50, "kg", ["chicken thighs", "chicken thigh"]),
    ("Brown Rice 1kg", "grains", 3.80, "kg", ["brown rice", "wholegrain rice"]),
    ("Rice Vinegar 250ml", "condiments", 2.40, "bottle", ["rice vinegar"]),
    ("Almond Milk 1L", "dairy-alt", 2.10, "L", ["almond milk", "plant milk", "nut milk"]),
    ("Frozen Spinach 450g", "frozen", 1.80, "pack", ["frozen spinach"]),
    # general staples
    ("Bananas", "produce", 1.40, "kg", ["bananas", "banana"]),
    ("Tomatoes", "produce", 2.30, "kg", ["tomatoes", "tomato"]),
    ("Yellow Onions", "produce", 1.10, "kg", ["onions", "onion"]),
    ("Potatoes", "produce", 1.50, "kg", ["potatoes", "potato"]),
    ("Whole Wheat Bread", "bakery", 1.90, "loaf", ["bread", "wheat bread", "whole wheat bread"]),
    ("Salted Butter 250g", "dairy", 2.60, "pack", ["butter", "salted butter"]),
    ("Cheddar Cheese 200g", "dairy", 3.40, "pack", ["cheddar", "cheese", "cheddar cheese"]),
    ("Greek Yogurt 500g", "dairy", 2.80, "tub", ["greek yogurt", "yogurt", "yoghurt"]),
    ("Olive Oil 500ml", "condiments", 4.90, "bottle", ["olive oil", "oil"]),
    ("Spaghetti 500g", "grains", 1.30, "pack", ["pasta", "spaghetti"]),
    ("Ground Beef 500g", "meat", 6.20, "pack", ["ground beef", "minced beef", "beef mince"]),
    ("Salmon Fillet", "meat", 9.80, "kg", ["salmon", "salmon fillet"]),
    ("Apples", "produce", 2.10, "kg", ["apples", "apple"]),
    ("Carrots", "produce", 1.00, "kg", ["carrots", "carrot"]),
    ("Bell Peppers", "produce", 3.10, "kg", ["bell pepper", "peppers", "capsicum"]),
    ("Garlic", "produce", 0.80, "pack", ["garlic"]),
    ("Breakfast Cereal 500g", "breakfast", 3.60, "box", ["cereal", "breakfast cereal"]),
    ("Orange Juice 1L", "beverages", 2.40, "carton", ["orange juice", "oj", "juice"]),
    ("Ground Coffee 250g", "beverages", 5.40, "pack", ["coffee", "ground coffee"]),
    ("White Sugar 1kg", "baking", 1.20, "kg", ["sugar", "white sugar"]),
]

CHAINS: list[dict] = [
    {
        "name": "ValueMart",
        "base_mult": 0.95,
        "stock_p": 0.95,
        "default_coverage": 0.90,
        "cat_mult": {},
        "cat_coverage": {},
    },
    {
        "name": "MegaSaver",
        "base_mult": 0.92,
        "stock_p": 0.94,
        "default_coverage": 0.88,
        "cat_mult": {
            "grains": 0.78,
            "baking": 0.78,
            "beverages": 0.80,
            "breakfast": 0.80,
            "condiments": 0.82,
            "frozen": 0.82,
            "dairy": 0.95,
            "meat": 1.12,
            "produce": 1.10,
        },
        "cat_coverage": {"meat": 0.5, "produce": 0.5},
    },
    {
        "name": "FreshFields",
        "base_mult": 1.16,
        "stock_p": 0.98,
        "default_coverage": 0.97,
        "cat_mult": {"produce": 0.98},
        "cat_coverage": {},
    },
    {
        "name": "GreenBasket",
        "base_mult": 1.10,
        "stock_p": 0.95,
        "default_coverage": 0.35,
        "cat_mult": {"produce": 0.72, "dairy": 0.90, "dairy-alt": 0.85},
        "cat_coverage": {"produce": 0.95, "dairy": 0.90, "dairy-alt": 0.90},
    },
    {
        "name": "ButcherBlock",
        "base_mult": 1.00,
        "stock_p": 0.97,
        "default_coverage": 0.08,
        "cat_mult": {"meat": 0.72},
        "cat_coverage": {"meat": 0.97},
    },
    {
        "name": "QuickStop",
        "base_mult": 1.30,
        "stock_p": 0.90,
        "default_coverage": 0.55,
        "cat_mult": {},
        "cat_coverage": {},
    },
]


def _scatter(rng, lat, lon, radius_deg):
    return (lat + rng.uniform(-radius_deg, radius_deg), lon + rng.uniform(-radius_deg, radius_deg))


def generate_raw(seed: int = 42, n_stores: int = 8, n_days: int = 3) -> dict:
    rng = random.Random(seed)
    base_ts = "2024-01-01T06:00:00"

    # --- product feed (with a couple of re-ingested duplicates) ---
    products = []
    for idx, (name, cat, _b, unit, terms) in enumerate(PRODUCT_UNIVERSE):
        products.append(
            {
                "product_id": f"p{idx:03d}",
                "raw_name": name,
                "category": cat,
                "unit": unit,
                "search_terms": "|".join(terms),
                "ingested_at": base_ts,
                "source": "supplier_feed",
            }
        )
    base_price = {f"p{idx:03d}": b for idx, (_n, _c, b, _u, _t) in enumerate(PRODUCT_UNIVERSE)}
    product_cat = {f"p{idx:03d}": c for idx, (_n, c, _b, _u, _t) in enumerate(PRODUCT_UNIVERSE)}
    # re-ingest two products later, one with stray whitespace -> Silver must dedupe/clean
    products.append(
        {**products[3], "raw_name": "  Whole Milk 1L ", "ingested_at": "2024-01-02T06:00:00"}
    )
    products.append({**products[0], "ingested_at": "2024-01-02T06:00:00"})

    # --- store feed (with a couple of duplicate rows) ---
    stores, carries = [], {}
    for s in range(n_stores):
        chain = CHAINS[s % len(CHAINS)]
        lat, lon = _scatter(rng, DEFAULT_USER_LAT, DEFAULT_USER_LON, 0.022)
        sid = f"s{s:02d}"
        stores.append(
            {
                "store_id": sid,
                "name": f"{chain['name']} #{s + 1}",
                "chain": chain["name"],
                "lat": round(lat, 6),
                "lon": round(lon, 6),
                "ingested_at": base_ts,
                "source": "store_feed",
            }
        )
        # decide which products this store carries (fixed across days)
        for pid in base_price:
            cat = product_cat[pid]
            cov = chain["cat_coverage"].get(cat, chain["default_coverage"])
            if rng.random() <= cov:
                carries[(sid, pid)] = chain
    stores.append({**stores[0], "ingested_at": "2024-01-02T06:00:00"})  # duplicate re-ingest

    # --- price events: one per (store, product, day), with daily drift ---
    events = []
    eid = 0
    for d in range(n_days):
        observed = f"2024-01-{d + 1:02d}T08:00:00"
        for (sid, pid), chain in carries.items():
            cat = product_cat[pid]
            store_noise = rng.uniform(0.95, 1.06)
            day_drift = rng.uniform(0.97, 1.03)
            price = base_price[pid] * chain["base_mult"] * chain["cat_mult"].get(cat, 1.0)
            price = round(price * store_noise * day_drift, 2)
            events.append(
                {
                    "event_id": f"e{eid:06d}",
                    "store_id": sid,
                    "product_id": pid,
                    "price": price,
                    "in_stock": rng.random() < chain["stock_p"],
                    "observed_at": observed,
                    "source": "price_scrape",
                }
            )
            eid += 1

    return {"stores": stores, "products": products, "price_events": events}
