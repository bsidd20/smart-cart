"""Tests for the ingestion pipeline, matching, the optimizer, and the API.

Uses the committed real-data fixture so tests run offline and deterministically.
Run with `pytest`.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import SETTINGS                            # noqa: E402
from app.data.store import Repository                      # noqa: E402
from app.ingestion import io, paths                        # noqa: E402
from app.ingestion.orchestration import pipeline           # noqa: E402
from app.matching.matcher import ProductMatcher            # noqa: E402
from app.models import UserCartItem                        # noqa: E402
from app.optimization import greedy                        # noqa: E402

CART = ["chicken breast", "rice", "eggs", "milk", "spinach"]


def test_pipeline_builds_and_quality_holds():
    pipeline.run_fixture()
    # Silver drops malformed rows, so it has fewer products than raw Bronze.
    assert len(io.read_delta(paths.SILVER_DIM_PRODUCT)) < len(io.read_delta(paths.BRONZE_RAW_PRODUCTS))
    assert len(io.read_delta(paths.GOLD_OFFERS)) > 0
    # every hard (error-severity) quality check passes; malformed records are caught.
    q = io.read_delta(paths.QUALITY_RESULTS)
    assert q[q["severity"] == "error"]["passed"].all()
    assert q.loc[q["check_name"] == "malformed_records", "failed_count"].iloc[0] >= 1


def test_matching_real_products():
    if not pipeline.is_built():
        pipeline.run_fixture()
    matcher = ProductMatcher(Repository.load())
    # "milk" must resolve to a dairy milk product, never almond/oat/soy milk
    avail = [m for m in matcher.match_across_stores("milk").values() if m.available]
    assert avail
    assert all("almond" not in m.product_name.lower() and "oat" not in m.product_name.lower()
               for m in avail)


def test_optimizer_coverage_and_soundness():
    if not pipeline.is_built():
        pipeline.run_fixture()
    repo = Repository.load()
    matcher = ProductMatcher(repo)
    cart = [UserCartItem(raw_text=i) for i in CART]
    res = greedy.optimize_cart(repo, matcher, cart, SETTINGS)
    single, multi = res["single_store"], res["multi_store"]
    assert single.coverage == 1.0 and multi.coverage == 1.0
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
        assert len(client.get("/price-stats").json()) > 0
        assert len(client.get("/ingestion/quality").json()) > 0


if __name__ == "__main__":
    test_pipeline_builds_and_quality_holds()
    test_matching_real_products()
    test_optimizer_coverage_and_soundness()
    test_api_endpoints()
    print("ok")
