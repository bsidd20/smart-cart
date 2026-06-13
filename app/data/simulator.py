"""Generates a synthetic store catalog.

Real grocery prices aren't freely available, so we build our own: a fixed product
list (with synonyms and some near-duplicates the matcher has to tell apart) and a
set of stores whose chains have different price profiles and coverage. Output is
seeded, so the catalog is identical on every run. To use real data, replace this
module with a scraper or feed; nothing else changes.
"""
from __future__ import annotations

import json
import random

from app import config
from app.config import DEFAULT_USER_LAT, DEFAULT_USER_LON

# (name, category, base price, unit, [synonyms])
PRODUCT_UNIVERSE: list[tuple[str, str, float, str, list[str]]] = [
    ("Chicken Breast Fillets", "meat", 7.50, "kg", ["chicken breast", "chicken fillet", "chicken"]),
    ("White Basmati Rice 1kg", "grains", 3.20, "kg", ["rice", "white rice", "basmati rice", "basmati"]),
    ("Large Eggs (dozen)", "dairy", 3.00, "dozen", ["eggs", "egg", "large eggs", "dozen eggs"]),
    ("Whole Milk 1L", "dairy", 1.20, "L", ["milk", "whole milk", "dairy milk", "full fat milk"]),
    ("Baby Spinach 200g", "produce", 2.20, "pack", ["spinach", "baby spinach", "fresh spinach", "leaf spinach"]),
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

# Each chain has a base price multiplier, an in-stock probability, a default
# coverage, and per-category overrides for price and coverage. The specialization
# (a cheap butcher, an organic market) is what creates the price/coverage tradeoffs
# the optimizer has to weigh.
CHAINS: list[dict] = [
    {   # generalist: carries almost everything at a middling price
        "name": "ValueMart", "base_mult": 0.95, "stock_p": 0.95,
        "default_coverage": 0.90, "cat_mult": {}, "cat_coverage": {},
    },
    {   # cheap pantry/dairy, pricier and patchier on fresh
        "name": "MegaSaver", "base_mult": 0.92, "stock_p": 0.94,
        "default_coverage": 0.88,
        "cat_mult": {"grains": 0.78, "baking": 0.78, "beverages": 0.80,
                     "breakfast": 0.80, "condiments": 0.82, "frozen": 0.82,
                     "dairy": 0.95, "meat": 1.12, "produce": 1.10},
        "cat_coverage": {"meat": 0.5, "produce": 0.5},
    },
    {   # premium full-range
        "name": "FreshFields", "base_mult": 1.16, "stock_p": 0.98,
        "default_coverage": 0.97, "cat_mult": {"produce": 0.98}, "cat_coverage": {},
    },
    {   # organic: cheapest produce and plant dairy, weak on pantry
        "name": "GreenBasket", "base_mult": 1.10, "stock_p": 0.95,
        "default_coverage": 0.35,
        "cat_mult": {"produce": 0.72, "dairy": 0.90, "dairy-alt": 0.85},
        "cat_coverage": {"produce": 0.95, "dairy": 0.90, "dairy-alt": 0.90},
    },
    {   # butcher: cheapest meat, little else
        "name": "ButcherBlock", "base_mult": 1.00, "stock_p": 0.97,
        "default_coverage": 0.08,
        "cat_mult": {"meat": 0.72}, "cat_coverage": {"meat": 0.97},
    },
    {   # convenience: dear and limited
        "name": "QuickStop", "base_mult": 1.30, "stock_p": 0.90,
        "default_coverage": 0.55, "cat_mult": {}, "cat_coverage": {},
    },
]


def _scatter(rng: random.Random, lat: float, lon: float, radius_deg: float):
    return (lat + rng.uniform(-radius_deg, radius_deg),
            lon + rng.uniform(-radius_deg, radius_deg))


def generate(seed: int = 42, n_stores: int = 7) -> dict:
    rng = random.Random(seed)

    products = [
        {"product_id": f"p{idx:03d}", "name": name, "category": cat,
         "brand": None, "unit": unit, "search_terms": terms}
        for idx, (name, cat, _base, unit, terms) in enumerate(PRODUCT_UNIVERSE)
    ]
    base_price = {f"p{idx:03d}": base
                  for idx, (_n, _c, base, _u, _t) in enumerate(PRODUCT_UNIVERSE)}
    product_cat = {f"p{idx:03d}": cat
                   for idx, (_n, cat, _b, _u, _t) in enumerate(PRODUCT_UNIVERSE)}

    stores, inventory = [], []
    for s in range(n_stores):
        chain = CHAINS[s % len(CHAINS)]
        # ~2.5 km radius so multi-store trips stay plausible
        lat, lon = _scatter(rng, DEFAULT_USER_LAT, DEFAULT_USER_LON, 0.022)
        store_id = f"s{s:02d}"
        stores.append({
            "store_id": store_id,
            "name": f"{chain['name']} #{s+1}",
            "chain": chain["name"],
            "lat": round(lat, 6), "lon": round(lon, 6),
        })
        for prod in products:
            cat = product_cat[prod["product_id"]]
            coverage = chain["cat_coverage"].get(cat, chain["default_coverage"])
            if rng.random() > coverage:
                continue  # store doesn't carry this product
            cat_mult = chain["cat_mult"].get(cat, 1.0)
            noise = rng.uniform(0.95, 1.06)
            price = base_price[prod["product_id"]] * chain["base_mult"] * cat_mult * noise
            inventory.append({
                "store_id": store_id,
                "product_id": prod["product_id"],
                "price": round(price, 2),
                "in_stock": rng.random() < chain["stock_p"],
            })
    return {"stores": stores, "products": products, "inventory": inventory}


def write_dataset(seed: int = 42, n_stores: int = 7) -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    data = generate(seed=seed, n_stores=n_stores)
    config.STORES_FILE.write_text(json.dumps(data["stores"], indent=2))
    config.PRODUCTS_FILE.write_text(json.dumps(data["products"], indent=2))
    config.INVENTORY_FILE.write_text(json.dumps(data["inventory"], indent=2))
    print(f"Wrote {len(data['stores'])} stores, {len(data['products'])} products, "
          f"{len(data['inventory'])} inventory rows to {config.DATA_DIR}")


if __name__ == "__main__":
    write_dataset()
