"""Tests for the lakehouse, matching, the optimizer, and the API. Run with `pytest`."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import SETTINGS                            # noqa: E402
from app.data.store import Repository                      # noqa: E402
from app.lakehouse import io, paths, pipeline              # noqa: E402
from app.matching.matcher import ProductMatcher            # noqa: E402
from app.models import UserCartItem                        # noqa: E402
from app.optimization import greedy                        # noqa: E402

CART = ["chicken breast", "rice", "eggs", "milk", "spinach"]


def _setup():
    if not pipeline.is_built():
        pipeline.build()
    repo = Repository.load()
    return repo, ProductMatcher(repo)


def test_lakehouse_dedupes_and_builds_gold():
    pipeline.build()
    # Silver collapses the re-ingested duplicate rows back to one per key.
    raw_stores = len(io.read_delta(paths.BRONZE_STORES))
    dim_stores = len(io.read_delta(paths.SILVER_DIM_STORE))
    assert dim_stores < raw_stores
    # fact_inventory keeps the latest event per (store, product), far fewer than raw.
    assert len(io.read_delta(paths.SILVER_FACT_INVENTORY)) < len(io.read_delta(paths.BRONZE_PRICE_EVENTS))
    # price events were ingested over multiple days, so the table has versions.
    assert io.table_version(paths.BRONZE_PRICE_EVENTS) >= 1
    # gold serving table is populated.
    assert len(io.read_delta(paths.GOLD_OFFERS)) > 0


def test_matching_picks_canonical_products():
    repo, matcher = _setup()
    # "rice" should resolve to white rice, not brown rice or rice vinegar
    avail = [m for m in matcher.match_across_stores("rice").values() if m.available]
    assert avail, "rice should match somewhere"
    assert all("Rice" in m.product_name and "Brown" not in m.product_name
               and "Vinegar" not in m.product_name for m in avail)
    # "milk" should never resolve to almond milk
    avail = [m for m in matcher.match_across_stores("milk").values() if m.available]
    assert all("Almond" not in m.product_name for m in avail)


def test_optimizer_full_coverage_and_soundness():
    repo, matcher = _setup()
    cart = [UserCartItem(raw_text=i) for i in CART]
    res = greedy.optimize_cart(repo, matcher, cart, SETTINGS)
    single, multi = res["single_store"], res["multi_store"]
    assert single.coverage == 1.0 and multi.coverage == 1.0
    # multi-store should never be worse than single-store
    assert multi.objective <= single.objective + 1e-6
    assert multi.num_stores <= SETTINGS.max_stores


def test_api_endpoints():
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as client:
        assert len(client.get("/stores").json()) == 8
        m = client.post("/match-items", json={"items": ["milk", "spinach"]}).json()
        assert m["results"][0]["matched"] is not None
        o = client.post("/optimize-cart", json={"items": CART}).json()
        assert o["single_store"]["coverage"] == 1.0
        assert o["recommended"] in ("single_store", "multi_store")
        assert len(client.get("/price-stats").json()) > 0


if __name__ == "__main__":
    test_lakehouse_dedupes_and_builds_gold()
    test_matching_picks_canonical_products()
    test_optimizer_full_coverage_and_soundness()
    test_api_endpoints()
    print("ok")
