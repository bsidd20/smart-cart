"""Orchestrates the ingestion pipeline end to end.

  run_full         live pull of everything from Open Food Facts, then transform
  run_incremental  live pull of only products changed since the last watermark
  run_fixture      offline build from a committed real-data sample (fast/deterministic)

Transform = silver products -> model store/price layer -> silver store/inventory
-> gold -> quality checks -> metrics. Bronze is append-only; Silver MERGEs.
"""

from __future__ import annotations

import json
import time

from app.config import PROJECT_ROOT
from app.ingestion import paths
from app.ingestion.bronze import products as bronze_products
from app.ingestion.bronze import stores as bronze_stores
from app.ingestion.gold import build as gold
from app.ingestion.metadata import metrics, runs, schema
from app.ingestion.quality import checks, quarantine
from app.ingestion.silver import inventory as silver_inv
from app.ingestion.silver import products as silver_products
from app.ingestion.silver import stores as silver_stores
from app.ingestion.sources.openfoodfacts import OpenFoodFactsSource

FIXTURE = PROJECT_ROOT / "tests" / "fixtures" / "off_products_sample.json"


def _ingest(records: list[dict], mode: str) -> dict:
    run = runs.start_run("openfoodfacts", mode)
    run["schema_version"] = "off_v2"
    t0 = time.time()
    n = bronze_products.land(records, run)
    rejected = sum(1 for r in records if not r.get("barcode") or not r.get("product_name"))
    if records:  # detect/log source schema drift before declaring the run done
        schema.log_drift(
            run["run_id"],
            "openfoodfacts",
            schema.detect_drift("openfoodfacts", set(records[0].keys())),
        )
    runs.finish_run(run, rows_ingested=n, rows_rejected=rejected, duration_s=time.time() - t0)

    watermarks: dict[str, int] = {}
    for r in records:
        k = r["taxonomy_key"]
        watermarks[k] = max(watermarks.get(k, 0), int(r.get("last_modified_t") or 0))
    runs.set_watermarks("openfoodfacts", watermarks)
    return run


def ingest_live(page_size: int = 40, max_pages: int = 1, incremental: bool = False) -> dict:
    src = OpenFoodFactsSource(page_size=page_size, max_pages=max_pages)
    since = runs.get_watermarks(src.name) if incremental else {}
    records = src.fetch(since_ts=since)
    return _ingest(records, "incremental" if incremental else "full")


def ingest_fixture() -> dict:
    records = json.loads(FIXTURE.read_text())
    return _ingest(records, "fixture")


def transform(run_id: str, seed: int = 42) -> None:
    quarantine.quarantine_bad_products(run_id)  # route malformed records aside
    silver_products.build()
    bronze_stores.model(seed=seed)
    silver_stores.build()
    silver_inv.build()
    gold.build()
    checks.run_checks(run_id)
    metrics.capture(run_id)


def run_full(page_size: int = 40, max_pages: int = 1, seed: int = 42) -> dict:
    run = ingest_live(page_size, max_pages, incremental=False)
    transform(run["run_id"], seed)
    return run


def run_incremental(page_size: int = 40, max_pages: int = 1, seed: int = 42) -> dict:
    run = ingest_live(page_size, max_pages, incremental=True)
    transform(run["run_id"], seed)
    return run


def run_fixture(seed: int = 42) -> dict:
    run = ingest_fixture()
    transform(run["run_id"], seed)
    return run


def is_built() -> bool:
    return paths.exists(paths.GOLD_OFFERS)
