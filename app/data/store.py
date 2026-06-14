"""Repository over the Gold serving table.

Reads gold.store_product_offers (one row per store/product with price + product
metadata) and exposes stores, in-stock candidates per store, and distances. The
matcher and optimizer only see this interface, not the lakehouse underneath.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.config import SETTINGS
from app.ingestion import io, paths
from app.models import Product, Store

EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


@dataclass
class Candidate:
    product: Product
    price: float
    in_stock: bool


class Repository:
    def __init__(self):
        self._stores: dict[str, Store] = {}
        self._products: dict[str, Product] = {}
        self._candidates: dict[str, list[Candidate]] = {}

    @classmethod
    def load(cls) -> "Repository":
        repo = cls()
        offers = io.read_delta(paths.GOLD_OFFERS)
        for row in offers.itertuples(index=False):
            if row.store_id not in repo._stores:
                repo._stores[row.store_id] = Store(
                    store_id=row.store_id,
                    name=row.store_name,
                    chain=row.chain,
                    lat=float(row.lat),
                    lon=float(row.lon),
                )
            if row.product_id not in repo._products:
                terms = [t for t in str(row.search_terms).split("|") if t]
                repo._products[row.product_id] = Product(
                    product_id=row.product_id,
                    name=row.product_name,
                    category=row.category,
                    unit=row.unit,
                    search_terms=terms,
                )
            if bool(row.in_stock):
                repo._candidates.setdefault(row.store_id, []).append(
                    Candidate(
                        product=repo._products[row.product_id],
                        price=float(row.price),
                        in_stock=True,
                    )
                )
        return repo

    def stores(self, user_lat: float | None = None, user_lon: float | None = None) -> list[Store]:
        ulat = user_lat if user_lat is not None else SETTINGS.user_lat
        ulon = user_lon if user_lon is not None else SETTINGS.user_lon
        out = []
        for s in self._stores.values():
            s = s.model_copy()
            s.distance_km = round(haversine_km(ulat, ulon, s.lat, s.lon), 3)
            out.append(s)
        return sorted(out, key=lambda x: x.distance_km)

    def store(self, store_id: str) -> Store:
        return self._stores[store_id]

    def candidates(self, store_id: str) -> list[Candidate]:
        return self._candidates.get(store_id, [])

    def all_store_ids(self) -> list[str]:
        return list(self._stores.keys())

    def distance_km(self, store_id: str, user_lat: float, user_lon: float) -> float:
        s = self._stores[store_id]
        return haversine_km(user_lat, user_lon, s.lat, s.lon)
