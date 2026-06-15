# Design decisions

Short records of the calls that shaped this project, with the alternatives I weighed
and what each one cost me. Roughly in the order they came up.

## Medallion layout: append-only Bronze, MERGE Silver

Bronze stores raw records exactly as pulled, append-only, with ingestion metadata.
Silver is one row per business key, maintained with a Delta MERGE. Gold is the
denormalized serving tables.

The reason for the split is that capture and interpretation have different failure
modes. If my cleaning or scoring logic is wrong, I want to fix it and re-derive Silver
and Gold from Bronze without re-hitting the source. Bronze is the replay log; Silver is
the current state. The cost is storage (I keep the raw history) and that Silver is not
the source of truth, only a projection.

## Delta Lake over Iceberg or Hudi

All three give ACID and time travel on object storage. I picked Delta because delta-rs
runs the whole thing locally without a JVM, which keeps the project laptop-friendly, and
because the format maps one-to-one onto Databricks if this ever moved there. MERGE,
OPTIMIZE, and Z-order are first-class.

Iceberg would be the better call if I needed engine neutrality or hidden partitioning.
Hudi if record-level upserts with strong incremental pull were the central requirement.
For a single-writer lakehouse that might later run on Databricks, Delta was the path of
least resistance.

## DuckDB as the default engine, Spark as the scale path

On a laptop, DuckDB plus delta-rs is faster than Spark: no JVM, no shuffle, no cluster.
Spark only earns its overhead once the data outgrows one machine. I deliberately did not
stand up Spark on a 2M-row dataset, because a cluster on toy data measures nothing and
reads as cargo-culting.

So DuckDB is the default and Spark is the documented distributed path (`spark/`, run via
Docker). The transforms are SQL, so the logic moves between them. The cost is that two
engines exist in the repo, which a reviewer can fairly call redundant; the honest
framing is that one is the local default and the other is the scale story, not two
production engines.

## dbt for the transforms, Python for ingestion

dbt owns staging -> intermediate -> marts. It gives me tests, lineage, and a declarative
model graph for free, and the same models run on `dbt-spark` at scale unchanged.
Hand-writing that in Spark SQL would mean rebuilding the testing and lineage myself.

Ingestion stays in Python because that is where the retries, pagination, and API
quirks live, and that logic does not belong in SQL. This is the EL/T split: Python does
extract and load, dbt does transform.

## Two ingestion modes: batch for products, streaming for prices

Product data from Open Food Facts changes slowly, so batch with a `last_modified_t`
watermark is the right tool. Prices change fast, so the price feed is the streaming
candidate. Rather than force everything into one model, I kept both. Because both land
in the same Bronze Delta, there is no second serving copy to reconcile, which is the
thing that usually makes a Lambda architecture painful.

## At-least-once plus an idempotent sink, not Kafka transactions

The producer uses `acks=all` and retries, which gives at-least-once delivery and
therefore duplicates. Instead of reaching for Kafka exactly-once transactions, the
consumer sink is an idempotent Delta MERGE on `event_id`. A redelivered message upserts
rather than duplicates, which gets effectively-once with far less machinery.

Transactions would be the call if there were no natural idempotency key. Here there is
one, so the simpler design wins. The honest caveat: I have not run this under real load,
so this is a design decision, not a battle-tested one.

## Modeled pricing on a real product master

There is no free real-time grocery price API. I could have faked a price source, but a
labeled modeled layer is more defensible than a fabricated one. So products are real
(Open Food Facts), and prices are modeled per store and isolated to one module
(`bronze/stores.py`) so a real feed could replace it without touching anything
downstream. The cost is that the pricing is not real; the benefit is that the data
integrity is honest and the seam is clean.

## Partition by category and date

Tables are partitioned on the columns queries filter by, so reads prune to the relevant
directories. Category and date are low cardinality and match the access patterns.

The known weakness, which I track as an issue, is that the MERGE keys (`barcode`,
`event_id`) are not the partition keys, so MERGE cannot prune partitions at large scale.
The fix is liquid clustering or aligning the clustering with the merge predicate; I left
it because at this size it does not bite.

## Greedy optimizer first, ILP optional

The multi-store assignment is a small constrained optimization. I wrote the greedy
solver first because it is O(items x stores), transparent, and explainable per item,
which is what the product needs ("why did you send me here?"). The exact ILP
(`ortools_solver.py`) solves the same objective optimally and is there for when the
greedy gap matters. OR-Tools has no wheel for current Python, so greedy is the default
and the ILP is opt-in.
