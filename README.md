# smart-cart

Turn a grocery list into a shopping plan. Given items like
`["chicken breast", "rice", "eggs", "milk", "spinach"]`, smart-cart returns the best
single store to buy everything, the cheapest practical multi-store split, and a short
reason for each item.

The data side is a small **lakehouse**: raw store/product/price feeds land in Bronze,
get cleaned and deduplicated into Silver, and roll up into Gold serving tables. The
matcher and optimizer serve off Gold. Everything runs locally and free, using real
Delta Lake tables (via `delta-rs`), DuckDB for SQL, and FastAPI for the API.

## Architecture

```
  raw feeds            BRONZE                SILVER                  GOLD              serving
  ---------            ------                ------                  ----              -------
  store feed    ->  stores (raw)     ->  dim_store (deduped)   \
  supplier feed ->  products (raw)   ->  dim_product (deduped)  ->  store_product_offers -> Repository
  price scrape  ->  price_events     ->  fact_inventory               (denormalized)        -> matcher
                    (append-only,        (latest price per       ->  product_price_stats     -> optimizer
                     daily versions)      store/product)         ->  store_price_index   -> /price-stats, /store-index
```

- **Bronze**: raw rows exactly as received. Price events are appended one day at a
  time, so the Delta table keeps versions (time travel works).
- **Silver**: one row per key. `dim_store`/`dim_product` drop re-ingested duplicates
  and clean fields; `fact_inventory` keeps the latest price event per (store, product)
  using a window function.
- **Gold**: `store_product_offers` is the denormalized table the app reads;
  `product_price_stats` and `store_price_index` are analytics.

Transforms are DuckDB SQL over the Delta tables (`app/lakehouse/`). The app never
touches Bronze/Silver; it only reads Gold.

### How it maps to Databricks

The local stack is chosen so each piece has a direct Databricks equivalent:

| Local (this repo)            | Databricks            |
|------------------------------|-----------------------|
| Delta Lake via `delta-rs`    | Delta Lake            |
| DuckDB SQL transforms        | Spark SQL / Photon    |
| `pipeline.py` (bronze->gold) | Delta Live Tables / Workflows |
| DuckDB serving queries       | Databricks SQL        |
| table paths in `paths.py`    | Unity Catalog tables  |

The table format is the same open Delta format in both, so the Gold tables here would
load on Databricks unchanged.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python scripts/build_lakehouse.py   # bronze -> silver -> gold
python scripts/demo.py              # run an example end to end
```

API:

```bash
uvicorn app.main:app --reload       # docs at http://127.0.0.1:8000/docs
```

Tests: `pytest`

## Endpoints

- `GET /stores` - stores near the user with distances
- `POST /match-items` - `{"items": ["milk", "spinach"]}` -> best product per item
- `POST /optimize-cart` - `{"items": [...], "max_stores": 3, "use_ilp": false}` ->
  single-store plan, multi-store plan, and per-item reasons
- `GET /price-stats` - per-product price stats across stores (from Gold)
- `GET /store-index` - per-store price index, cheapest first (from Gold)

```json
POST /optimize-cart
{ "items": ["chicken breast", "rice", "eggs", "milk", "spinach"] }
```

Each plan comes back with an `objective` score so you can see which one the engine
prefers and why.

## Matching and optimization

**Matching** (`app/matching/`). Each list item is matched to a product at each store.
Fuzzy matching (RapidFuzz) handles typos, plurals and word order; an optional embedding
matcher handles meaning. The embedder is pluggable - a small hashing vector by default
so there are no heavy dependencies, or `sentence-transformers` if it's installed. A
score threshold keeps bad substitutions out, so "spinach" doesn't get matched to
"spaghetti".

**Optimization** (`app/optimization/`). The single-store answer scores each store's
basket and picks the best. The multi-store answer assigns each item to a store to
minimize one objective:

```
price*basket + distance*round_trip_km + subs*sum(1 - match_score)
  + visit*num_stores + coverage*num_missing
```

The greedy solver starts from each item's cheapest store, consolidates down to
`max_stores`, and drops any store that isn't worth the extra trip. Weights live in
`app/config.py`: raising distance/visit weights pushes plans toward a single store,
lowering them lets plans fan out to cheaper stores. `ortools_solver.py` solves the same
objective exactly as an ILP if OR-Tools is installed.

## Notes

- The synthetic feeds in `app/data/simulator.py` are the only thing you'd replace to
  use real data; the pipeline downstream doesn't change.
- The default embedder is a cheap hashing vector and is only used to re-rank, not to
  accept a match on its own. Install `sentence-transformers` for real semantic matching.
- The greedy solver is fast and easy to follow but isn't guaranteed optimal; the ILP is
  there for when that matters.

## Layout

```
app/
  main.py            FastAPI app
  models.py          data models
  config.py          paths, location, weights
  lakehouse/         bronze, silver, gold, pipeline, io, paths
  data/              simulator (raw feeds) + repository (reads Gold)
  matching/          fuzzy, semantic, orchestrator
  optimization/      ranking, greedy, ortools
scripts/             build_lakehouse.py, demo.py
tests/
```
