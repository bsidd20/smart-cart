"""Tests for matching, the optimizer, and the API. Run with `pytest`."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config                                  # noqa: E402
from app.config import SETTINGS                          # noqa: E402
from app.data import simulator                           # noqa: E402
from app.data.store import Repository                    # noqa: E402
from app.matching.matcher import ProductMatcher          # noqa: E402
from app.models import UserCartItem                      # noqa: E402
from app.optimization import greedy                      # noqa: E402

CART = ["chicken breast", "rice", "eggs", "milk", "spinach"]


def _setup():
    if not config.STORES_FILE.exists():
        simulator.write_dataset()
    repo = Repository.load()
    return repo, ProductMatcher(repo)


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


if __name__ == "__main__":
    test_matching_picks_canonical_products()
    test_optimizer_full_coverage_and_soundness()
    test_api_endpoints()
    print("ok")
