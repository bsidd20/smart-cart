"""FastAPI app. Loads data once at startup and exposes three endpoints:

    GET  /stores         stores near the user
    POST /match-items    best product match per query
    POST /optimize-cart  single-store + multi-store plans with reasons

Run: uvicorn app.main:app --reload  (docs at /docs)
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from copy import deepcopy

from fastapi import FastAPI
from pydantic import BaseModel, Field

from app.config import SETTINGS
from app.data.store import Repository
from app.ingestion import io, paths
from app.ingestion.orchestration import pipeline
from app.matching.matcher import ProductMatcher
from app.models import OptimizationResult, Store, UserCartItem
from app.optimization import greedy, ortools_solver

STATE: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not pipeline.is_built():
        pipeline.run_fixture()             # offline build from the real-data sample
    repo = Repository.load()
    STATE["repo"] = repo
    STATE["matcher"] = ProductMatcher(repo)
    yield
    STATE.clear()


app = FastAPI(title="smart-cart", version="1.0.0", lifespan=lifespan)


class MatchRequest(BaseModel):
    items: list[str] = Field(..., examples=[["chicken breast", "milk", "spinach"]])


class OptimizeRequest(BaseModel):
    items: list[str] = Field(..., examples=[["chicken breast", "rice", "eggs", "milk", "spinach"]])
    max_stores: int | None = None
    user_lat: float | None = None
    user_lon: float | None = None
    use_ilp: bool = False


class OptimizeResponse(BaseModel):
    matcher_backend: str
    recommended: str
    single_store: OptimizationResult
    multi_store: OptimizationResult


@app.get("/stores", response_model=list[Store])
def get_stores(user_lat: float | None = None, user_lon: float | None = None):
    return STATE["repo"].stores(user_lat, user_lon)


@app.get("/price-stats")
def price_stats():
    """Per-category price stats (gold.category_price_stats)."""
    return io.read_delta(paths.GOLD_CATEGORY_PRICE_STATS).to_dict(orient="records")


@app.get("/cheapest")
def cheapest():
    """Cheapest store per product (gold.cheapest_products)."""
    return io.read_delta(paths.GOLD_CHEAPEST_PRODUCTS).to_dict(orient="records")


@app.get("/ingestion/runs")
def ingestion_runs():
    """Ingestion run history (meta.ingestion_runs)."""
    if not paths.exists(paths.META_RUNS):
        return []
    return io.read_delta(paths.META_RUNS).to_dict(orient="records")


@app.get("/ingestion/quality")
def ingestion_quality():
    """Latest data quality check results (quality.quality_results)."""
    if not paths.exists(paths.QUALITY_RESULTS):
        return []
    return io.read_delta(paths.QUALITY_RESULTS).to_dict(orient="records")


@app.post("/match-items")
def match_items(req: MatchRequest):
    matcher: ProductMatcher = STATE["matcher"]
    results = []
    for q in req.items:
        available = [m for m in matcher.match_across_stores(q).values() if m.available]
        best = min(available, key=lambda m: (-m.score, m.price)) if available else None
        results.append({
            "query": q,
            "matched": best.product_name if best else None,
            "method": best.method if best else "none",
            "confidence": best.score if best else 0.0,
            "available_in_stores": len(available),
            "price_range": (
                [round(min(m.price for m in available), 2),
                 round(max(m.price for m in available), 2)] if available else None),
        })
    return {"matcher_backend": matcher.backend, "results": results}


@app.post("/optimize-cart", response_model=OptimizeResponse)
def optimize_cart(req: OptimizeRequest):
    repo: Repository = STATE["repo"]
    matcher: ProductMatcher = STATE["matcher"]

    settings = SETTINGS
    if any(v is not None for v in (req.max_stores, req.user_lat, req.user_lon)):
        settings = deepcopy(SETTINGS)
        if req.max_stores is not None:
            settings.max_stores = req.max_stores
        if req.user_lat is not None:
            settings.user_lat = req.user_lat
        if req.user_lon is not None:
            settings.user_lon = req.user_lon

    cart = [UserCartItem(raw_text=i) for i in req.items]
    result = greedy.optimize_cart(repo, matcher, cart, settings)

    if req.use_ilp and ortools_solver.is_available():
        options = greedy._collect_options(matcher, cart)
        qty = {ci.raw_text: ci.quantity for ci in cart}
        oneway = {s: repo.distance_km(s, settings.user_lat, settings.user_lon)
                  for s in repo.all_store_ids()}
        ilp = ortools_solver.optimize_multi_store_ilp(
            options, qty, oneway, repo, settings.weights, settings.max_stores)
        if ilp is not None:
            result["multi_store"] = ilp

    recommended = ("multi_store"
                   if result["multi_store"].objective < result["single_store"].objective
                   else "single_store")
    return OptimizeResponse(
        matcher_backend=matcher.backend, recommended=recommended,
        single_store=result["single_store"], multi_store=result["multi_store"])
