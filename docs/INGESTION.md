# Ingestion platform

How smart-cart pulls real product data and turns it into the Gold tables the app
serves from. Everything is free to run and built on Delta Lake + DuckDB locally.

## Data sources

| Source | Auth | Limits | What it gives us | Role |
|--------|------|--------|------------------|------|
| Open Food Facts | none | ~10 search req/min | real barcodes, names, brands, categories, `last_modified_t` | primary product master |
| USDA FoodData Central | free key | ~1k/hr | nutrition, standardized names | optional enrichment |
| pricing | - | - | no free real-time source exists | modeled layer (labeled) |

**Open Food Facts** is the primary source: no key, real UPCs, and a
`last_modified_t` timestamp that doubles as an incremental watermark. There is no
free real-time grocery *price* API, so prices are **modeled** on top of the real
product master (`app/ingestion/bronze/stores.py`) behind a clean seam: swap that
one module for a real price feed and nothing downstream changes.

## Architecture

```
 Open Food Facts ─┐
                  │  sources/openfoodfacts.py  (paginated, watermark-filtered, retry/backoff)
                  ▼
 BRONZE  raw_products (append-only, raw payload + run_id/ingested_at/source/schema_version)
 (Delta)  raw_stores, raw_price_events        <- modeled pricing layer
                  │  DuckDB SQL transforms
                  ▼
 SILVER  dim_product   (dedupe by barcode via window fn, clean, unit-normalize, MERGE upsert)
 (Delta)  dim_store, fact_inventory (latest price per store/product, MERGE upsert)
                  │
                  ▼
 GOLD    product_catalog / store_product_offers / category_price_stats
 (Delta)  cheapest_products / product_search_index
                  │
                  ▼
 SERVING  Repository -> Matcher -> Optimizer -> FastAPI

 META   ingestion_runs / watermarks / ingestion_metrics      QUALITY  quality_results
```

## Layers

**Bronze** (`bronze/`) is append-only and stores records as received, with
ingestion metadata (`run_id`, `ingested_at`, `source_system`, `schema_version`).
No cleaning happens here, so it can be replayed to rebuild everything downstream.

**Silver** (`silver/`) uses DuckDB SQL window functions to keep one row per key:
`row_number() OVER (PARTITION BY barcode ORDER BY last_modified_t DESC)`. It trims
and validates fields, normalizes units (oz->g, fl oz->ml), maps each product to our
taxonomy, assigns a modeled base price, and builds search terms. It is written with
a Delta **MERGE**, so re-runs upsert only changed rows.

**Gold** (`gold/`) joins Silver into serving + analytics tables:
- `store_product_offers` - denormalized store x product x price; the table the app reads
- `product_catalog` - clean product master for search/browse
- `category_price_stats` - per-category price spread and cheapest store
- `cheapest_products` - cheapest store per product (deals / price comparison)
- `product_search_index` - per-product search terms + availability

## Incremental loading

- **Watermark**: per (source, category) we store the max `last_modified_t` seen
  (`meta.watermarks`). The next pull asks Open Food Facts for that category sorted by
  modification time and keeps only records newer than the watermark.
- **Upsert**: Silver MERGEs on `barcode` (products) and `store_id|barcode`
  (inventory), so changed prices/products update in place instead of duplicating.
- **Late-arriving data**: because Silver keys on business identity (barcode) and
  orders by `last_modified_t`, a record that arrives out of order still resolves to
  the correct latest version.
- **Tradeoff**: Bronze keeps full history (cheap, replayable, audit-friendly); Silver
  keeps current state (small, fast to serve). Reprocessing always starts from Bronze.

## Data quality (`quality/`)

Each run appends results to `quality.quality_results`:

| check | layer | severity | what it catches |
|-------|-------|----------|-----------------|
| malformed_records | bronze | warn | empty barcode or product name |
| duplicate_products | silver | error | barcode not unique after dedupe |
| missing_categories | silver | error | product with no category |
| invalid_upcs | silver | warn | GTIN check-digit failure |
| invalid_prices | gold | error | price null, <= 0, or absurd |

`error` checks are contracts that must hold; `warn` checks track real-world noise we
tolerate but want visibility into.

## Observability (`metadata/`)

- `ingestion_runs` - one row per run: source, mode, status, rows ingested/rejected, duration
- `ingestion_metrics` - row counts per table and data freshness (hours since newest product)
- `watermarks` - incremental state per source/category

Served over HTTP at `/ingestion/runs` and `/ingestion/quality`.

## Folder structure

```
app/ingestion/
  sources/        openfoodfacts.py, base.py
  bronze/         products.py (raw landing), stores.py (modeled price layer)
  silver/         products.py, stores.py, inventory.py
  gold/           build.py (5 serving/analytics tables)
  metadata/       runs.py (runs + watermarks), metrics.py
  quality/        checks.py
  orchestration/  pipeline.py (run_full / run_incremental / run_fixture)
  io.py           Delta read/write + MERGE + DuckDB SQL helper
  paths.py        table registry
  category_map.py taxonomy -> OFF category + base price
```

## Scaling and the Databricks mapping

The local choices map directly to the platform, so the same design scales from a
laptop to billions of rows:

| local | Databricks | why it scales |
|-------|------------|---------------|
| Delta Lake via delta-rs | Delta Lake | same open format; partitioning, Z-order, compaction |
| DuckDB SQL transforms | Spark SQL / Photon | same SQL, distributed execution |
| `pipeline.py` | Delta Live Tables / Workflows | declarative DAG, retries, lineage |
| watermark + MERGE | Structured Streaming + MERGE | incremental at scale, exactly-once |
| `quality_results` checks | DLT expectations / Lakehouse Monitoring | quality enforced in-pipeline |
| `ingestion_runs` / metrics | Unity Catalog lineage + system tables | governed observability |

At larger scale the price/event stream would be the streaming path (Auto Loader or
Kafka -> Bronze), Silver/Gold would partition by category and date, and Gold would be
Z-ordered on the join keys the optimizer filters on.
