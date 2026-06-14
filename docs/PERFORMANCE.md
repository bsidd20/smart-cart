# Partitioning and file maintenance

Run `python scripts/benchmark.py` for live before/after numbers.

## Partitioning

Delta tables are partitioned on the columns queries filter by, so reads open only the
relevant directories (partition pruning):

| table | partition key | why |
|-------|---------------|-----|
| `bronze.raw_products` | `taxonomy_key` (category) | most reads are per-category |
| `silver.dim_product` | `category` | same |
| `gold.store_product_offers` | `category` | the optimizer and analytics filter by category |
| `bronze.raw_price_events` | `event_date` | time-series; reads target recent dates |

On the sample data, `store_product_offers` has 11 files across 11 category partitions,
so a `WHERE category = 'milk'` query opens 1 of 11 files - **~91% skipped before reading
any data**. That ratio is scale-invariant: at billions of rows it is the same fraction
of I/O, scan cost, and warehouse compute avoided. This is the single biggest lever on
both performance and cost in a columnar lakehouse.

Partition choice is a tradeoff: too coarse and pruning barely helps; too fine (high
cardinality, e.g. per-barcode) and you get the small-file problem below plus slow
metadata. Category and date are low-cardinality and match the query patterns.

## Small-file compaction

Incremental loads land many small files (one or more per micro-batch per partition).
Too many small files means slow listing and per-file open overhead. `compact()` rewrites
them into fewer larger files. In the benchmark, 8 micro-batch appends grow
`bronze.raw_products` from 11 to 19 files; compaction brings it back to 11 (removes 9,
writes 1 per affected partition).

## Z-ordering

`z_order([cols])` co-locates rows by a secondary column inside each file, so queries
filtering on that column (here `store_id` on `store_product_offers`) skip more files via
min/max statistics. Use it for the high-value filter columns that are not the partition
key.

## How this maps to the platform

- delta-rs `compact()` / `z_order()` -> Databricks `OPTIMIZE` / `OPTIMIZE ... ZORDER BY`
  and Delta auto-optimize; partition pruning -> the same on Spark/Photon and Snowflake
  micro-partitions.
- Cost: partition pruning + compaction reduce bytes scanned and small-file overhead,
  which is what most warehouse/lakehouse billing is based on; the S3 lifecycle rules in
  `infra/` expire old object versions to cap storage cost.
- A maintenance job (compact + z-order, then `VACUUM` on the platform) runs on a
  schedule after ingestion, the same way the Airflow DAG would trigger it.
