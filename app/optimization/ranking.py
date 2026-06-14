"""The objective function used to score and compare plans.

One number per plan (lower is better), so "one pricey convenient store" and "three
cheap scattered stores" can be compared directly:

    objective = price * basket_price
              + distance * round_trip_km
              + substitution * sum(1 - match_score)
              + store_visit * num_stores
              + coverage * num_missing_items

Weights live in config.py. coverage is kept large so items are never dropped to save
a little; raising distance/store_visit pushes toward one store, lowering them lets
plans fan out to cheaper stores.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import Weights


@dataclass
class Line:
    item: str
    qty: int
    store_id: str
    unit_price: float
    score: float


def objective(
    lines: list[Line], num_missing: int, oneway_km_by_store: dict[str, float], w: Weights
) -> dict:
    basket_price = sum(l.qty * l.unit_price for l in lines)
    sub_gap = sum(1.0 - l.score for l in lines)
    stores_used = sorted({l.store_id for l in lines})
    total_km = sum(2.0 * oneway_km_by_store[s] for s in stores_used)  # out and back

    total = (
        w.price_weight * basket_price
        + w.distance_weight * total_km
        + w.substitution_penalty * sub_gap
        + w.store_visit_penalty * len(stores_used)
        + w.coverage_penalty * num_missing
    )

    return {
        "objective": round(total, 3),
        "basket_price": round(basket_price, 2),
        "total_distance_km": round(total_km, 3),
        "num_stores": len(stores_used),
        "stores_used": stores_used,
        "num_missing": num_missing,
        "substitution_gap": round(sub_gap, 3),
    }
