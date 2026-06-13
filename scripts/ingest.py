"""Run the ingestion pipeline.

    python scripts/ingest.py              # offline build from the committed real-data sample
    python scripts/ingest.py --live       # live full pull from Open Food Facts
    python scripts/ingest.py --incremental # live pull of only products changed since last run
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ingestion import io, paths                       # noqa: E402
from app.ingestion.orchestration import pipeline          # noqa: E402


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else "--fixture"
    if arg == "--live":
        print("Live full pull from Open Food Facts (this is rate-limited, ~minutes)...")
        run = pipeline.run_full()
    elif arg == "--incremental":
        print("Incremental pull (only products changed since last watermark)...")
        run = pipeline.run_incremental()
    else:
        print("Offline build from the committed real-data sample...")
        run = pipeline.run_fixture()

    print(f"run {run['run_id']} status={run['status']} "
          f"ingested={run['rows_ingested']} rejected={run['rows_rejected']}")
    for name, p in [("bronze.raw_products", paths.BRONZE_RAW_PRODUCTS),
                    ("silver.dim_product", paths.SILVER_DIM_PRODUCT),
                    ("gold.store_product_offers", paths.GOLD_OFFERS)]:
        print(f"  {name:<28} {len(io.read_delta(p)):>5} rows")
    q = io.read_delta(paths.QUALITY_RESULTS)
    failed = q[(~q["passed"]) & (q["severity"] == "error")]
    print(f"quality: {len(q)} checks, {len(failed)} hard failures")


if __name__ == "__main__":
    main()
