"""Repository over the local JSON files.

Loads stores/products/inventory, joins inventory to products so each store exposes
a list of in-stock candidates, and computes store distance from the user. Keeping
this behind one class means swapping JSON for a database later only touches here.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass

from app import config
from app.models import InventoryItem, Product, Store

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
        self._candidates: dict[str, list[Candidate]] = {}   # store_id -> in-stock items

    @classmethod
    def load(cls) -> "Repository":
        repo = cls()
        stores = json.loads(config.STORES_FILE.read_text())
        products = json.loads(config.PRODUCTS_FILE.read_text())
        inventory = json.loads(config.INVENTORY_FILE.read_text())

        repo._stores = {s["store_id"]: Store(**s) for s in stores}
        repo._products = {p["product_id"]: Product(**p) for p in products}

        for inv in inventory:
            item = InventoryItem(**inv)
            if not item.in_stock:
                continue
            product = repo._products.get(item.product_id)
            if product is None:
                continue
            repo._candidates.setdefault(item.store_id, []).append(
                Candidate(product=product, price=item.price, in_stock=item.in_stock)
            )
        return repo

    def stores(self, user_lat: float | None = None, user_lon: float | None = None) -> list[Store]:
        ulat = user_lat if user_lat is not None else config.SETTINGS.user_lat
        ulon = user_lon if user_lon is not None else config.SETTINGS.user_lon
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
