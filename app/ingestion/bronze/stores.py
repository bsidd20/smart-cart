"""Modeled store + price layer over the real product master.

Open Food Facts has product data but no prices, so prices here are MODELED: each
chain has a base multiplier plus per-group multipliers (a cheap butcher, an organic
produce market, etc.) applied to a product's base price. This is the one synthetic
seam; swap it for a real price feed and the rest of the pipeline is unchanged.

Stores and price events land in Bronze like any other raw source.
"""

from __future__ import annotations

import random

import pandas as pd

from app.config import DEFAULT_USER_LAT, DEFAULT_USER_LON
from app.ingestion import io, paths

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
            "bakery": 0.85,
            "breakfast": 0.80,
            "beverages": 0.82,
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
        "cat_mult": {"produce": 0.72, "dairy": 0.90},
        "cat_coverage": {"produce": 0.95, "dairy": 0.90},
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


def _scatter(rng, lat, lon, r):
    return lat + rng.uniform(-r, r), lon + rng.uniform(-r, r)


def model(
    seed: int = 42, n_stores: int = 8, n_days: int = 2, max_products_per_store: int = 120
) -> None:
    rng = random.Random(seed)
    products = io.read_delta(paths.SILVER_DIM_PRODUCT)[["barcode", "product_group", "base_price"]]
    products = products.sample(frac=1.0, random_state=seed).reset_index(drop=True)

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
                "ingested_at": "2024-01-01T06:00:00",
                "source_system": "modeled_pricing",
            }
        )
        kept = 0
        for row in products.itertuples(index=False):
            cov = chain["cat_coverage"].get(row.product_group, chain["default_coverage"])
            if rng.random() <= cov and kept < max_products_per_store:
                carries[(sid, row.barcode)] = (chain, float(row.base_price), row.product_group)
                kept += 1
    io.write_delta(pd.DataFrame(stores), paths.BRONZE_RAW_STORES, mode="overwrite")

    events, eid = [], 0
    for d in range(n_days):
        observed = f"2024-01-{d + 1:02d}T08:00:00"
        for (sid, bc), (chain, base, grp) in carries.items():
            price = base * chain["base_mult"] * chain["cat_mult"].get(grp, 1.0)
            price *= rng.uniform(0.95, 1.06) * rng.uniform(0.97, 1.03)
            events.append(
                {
                    "event_id": f"e{eid:07d}",
                    "store_id": sid,
                    "barcode": bc,
                    "price": round(price, 2),
                    "in_stock": rng.random() < chain["stock_p"],
                    "observed_at": observed,
                    "source_system": "modeled_pricing",
                }
            )
            eid += 1
    for i in range(n_days):
        day = f"2024-01-{i + 1:02d}"
        batch = [e for e in events if e["observed_at"].startswith(day)]
        io.write_delta(
            pd.DataFrame(batch),
            paths.BRONZE_RAW_PRICE_EVENTS,
            mode="overwrite" if i == 0 else "append",
        )
