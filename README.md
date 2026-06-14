# smart-cart

Turn a grocery list into a shopping plan. Given items like
`["chicken breast", "rice", "eggs", "milk", "spinach"]`, smart-cart returns the best
single store to buy everything, the cheapest practical multi-store split, and a short
reason for each item.

The centerpiece is a data platform; the optimizer is one consumer of it. Product data
is pulled from [Open Food Facts](https://world.openfoodfacts.org) into Bronze Delta
tables, transformed by **dbt** (staging -> intermediate -> marts) with tests and
lineage, validated, and served as Gold marts. It runs locally and free using real
Delta Lake (via `delta-rs`), DuckDB, and dbt, and is designed to lift onto AWS
(Terraform) with Airflow orchestration and GitHub Actions CI.

Open Food Facts has product data but no prices, so the store/price layer is modeled on
top of the real product master behind a single swappable module. Full design:
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/INGESTION.md](docs/INGESTION.md).

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

## Data platform

- **dbt** (`transform/`) is the transform layer: sources over the Bronze Delta tables,
  `staging` -> `intermediate` -> `marts`, with data tests and generated lineage. Run it
  in a Python 3.13 env:
  ```bash
  python3.13 -m venv .venv-dbt && source .venv-dbt/bin/activate && pip install -r requirements-dbt.txt
  export SMARTCART_LAKE=$(pwd)/data/lake SMARTCART_MARTS=$(pwd)/data/lake/marts
  cd transform && dbt build --profiles-dir .   # builds marts + runs tests
  dbt docs generate --profiles-dir . && dbt docs serve --profiles-dir .   # lineage
  ```
- **Orchestration** (`orchestration/airflow/`): a daily DAG with retries/backoff,
  backfills (`catchup`), failure alerts, and quality gates.
- **Schema evolution**: source drift is detected per run (`app/ingestion/metadata/schema.py`)
  - new columns are allowed, removals are flagged.
- **Quarantine**: malformed records are routed to a quarantine table, not dropped.
- **Partitioning + performance**: Delta tables are partitioned by category/date for
  partition pruning; `scripts/benchmark.py` shows pruning (~91% files skipped) and
  small-file compaction / Z-order with before/after numbers. See
  [docs/PERFORMANCE.md](docs/PERFORMANCE.md).
- **Streaming** (`streaming/`, `spark/`): Kafka price-event stream -> Spark Structured
  Streaming -> Bronze Delta, with a dead-letter queue, offset tracking, event schema
  versioning, watermarks/late handling, and replay. The whole stack (Kafka, producer,
  consumer, Spark) runs with **`docker compose up --build`** - host needs only Docker;
  the producer/consumer logic is also unit-tested without a broker. See
  [docs/STREAMING.md](docs/STREAMING.md).
- **Scale**: `scripts/scale_simulation.py` builds millions of rows and benchmarks
  partition pruning + compaction at a size where it matters (2M rows: one-day query
  3.6x faster, compaction 1200->30 files). PySpark + Delta jobs in `spark/` are the
  distributed path. See [docs/SCALE.md](docs/SCALE.md).
- **Cloud / IaC** (`infra/`): Terraform for an S3 lakehouse with dev/stage/prod isolation.
- **CI** (`.github/workflows/ci.yml`): ruff lint + format, pytest, and a full dbt
  build+test on every push.

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
  ingestion/         sources, bronze, silver, gold, metadata, quality, orchestration
  data/              repository (reads Gold)
  matching/          fuzzy, semantic, orchestrator
  optimization/      ranking, greedy, ortools
transform/           dbt project (staging -> intermediate -> marts, tests, lineage)
streaming/           Kafka producer/consumer, DLQ, replay, schema versioning
spark/               PySpark + Delta: Structured Streaming + batch jobs
orchestration/airflow/  production DAG (retries, backfills, alerts, optimize, quality gates)
infra/               Terraform: S3 lakehouse, dev/stage/prod
Dockerfile           app image for the containerized producer/consumer
docker-compose.yml   one-command stack: Kafka (KRaft) + UI + producer + consumer + Spark
scripts/             ingest.py, demo.py, benchmark.py, scale_simulation.py
tests/               app + platform + streaming tests, real-data fixture
docs/                ARCHITECTURE, INGESTION, PERFORMANCE, STREAMING, SCALE
```
