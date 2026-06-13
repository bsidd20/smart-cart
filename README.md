# smart-cart

Turn a grocery list into a shopping plan. Given items like
`["chicken breast", "rice", "eggs", "milk", "spinach"]`, smart-cart returns the best
single store to buy everything, the cheapest practical multi-store split, and a short
reason for each item.

It's built on a real ingestion pipeline: product data is pulled from
[Open Food Facts](https://world.openfoodfacts.org) into Bronze Delta tables, cleaned
and deduplicated into Silver, and rolled up into Gold serving tables. The matcher and
optimizer serve off Gold. Everything runs locally and free, using real Delta Lake
tables (via `delta-rs`), DuckDB for SQL, and FastAPI for the API.

Open Food Facts has product data but no prices, so the store/price layer is modeled on
top of the real product master behind a single swappable module. See
[docs/INGESTION.md](docs/INGESTION.md) for the full data design.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python scripts/ingest.py            # offline build from the committed real-data sample
python scripts/demo.py              # run an example end to end
```

To pull fresh data from Open Food Facts (rate-limited, takes a few minutes):

```bash
python scripts/ingest.py --live         # full pull
python scripts/ingest.py --incremental  # only products changed since the last run
```

API:

```bash
uvicorn app.main:app --reload       # docs at http://127.0.0.1:8000/docs
```

Tests: `pytest`

## Architecture

```
 Open Food Facts -> BRONZE (raw) -> SILVER (clean/dedupe) -> GOLD (serving) -> API
                    + modeled store/price layer
                    + meta (runs, watermarks, metrics) + quality (checks)
```

- **Bronze** lands raw records append-only with ingestion metadata (run id, timestamp,
  source, schema version). No cleaning here, so it can be replayed.
- **Silver** keeps one row per key with DuckDB window functions, normalizes units,
  maps categories, and MERGE-upserts so re-runs only touch changed rows.
- **Gold** has `store_product_offers` (served to the app), `product_catalog`,
  `category_price_stats`, `cheapest_products`, and `product_search_index`.
- **Incremental**: a per-category `last_modified_t` watermark means each pull only
  fetches changed products; Silver MERGEs them in.
- **Quality + observability**: every run records check results, row counts, and data
  freshness to dedicated tables, exposed at `/ingestion/quality` and `/ingestion/runs`.

## Endpoints

- `GET /stores` - stores near the user with distances
- `POST /match-items` - `{"items": ["milk", "spinach"]}` -> best product per item
- `POST /optimize-cart` - `{"items": [...], "max_stores": 3, "use_ilp": false}` ->
  single-store plan, multi-store plan, and per-item reasons
- `GET /price-stats` - per-category price spread (Gold)
- `GET /cheapest` - cheapest store per product (Gold)
- `GET /ingestion/runs`, `GET /ingestion/quality` - run history and quality results

## Matching and optimization

**Matching** (`app/matching/`). Each list item is matched to a product at each store.
Fuzzy matching (RapidFuzz) handles typos, plurals and word order; an optional embedding
matcher handles meaning. A score threshold keeps bad substitutions out, so "spinach"
doesn't match "spaghetti", and a category exclusion rule keeps "milk" off plant milks.

**Optimization** (`app/optimization/`). The single-store answer scores each store's
basket and picks the best. The multi-store answer assigns each item to a store to
minimize one objective:

```
price*basket + distance*round_trip_km + subs*sum(1 - match_score)
  + visit*num_stores + coverage*num_missing
```

The greedy solver starts from each item's cheapest store, consolidates down to
`max_stores`, and drops any store that isn't worth the extra trip. Weights live in
`app/config.py`. `ortools_solver.py` solves the same objective exactly as an ILP if
OR-Tools is installed.

## Layout

```
app/
  main.py            FastAPI app
  models.py          data models
  config.py          paths, location, weights
  ingestion/         sources, bronze, silver, gold, metadata, quality, orchestration
  data/              repository (reads Gold)
  matching/          fuzzy, semantic, orchestrator
  optimization/      ranking, greedy, ortools
scripts/             ingest.py, demo.py
tests/               tests + real-data fixture
docs/                INGESTION.md
```
