# Engineering notes

Notes to myself on the things that bit me, the calls I made, and what I'd do with a
real budget. Kept honest on purpose: a few of these are design decisions I haven't
yet stress-tested, and they're labeled as such.

## Real issues I hit (and the fixes)

**The matcher bought the wrong product.** Early on, a "spinach" query came back as
"Spaghetti 500g". The accept threshold was 0.50 and the token-set ratio rated
spinach/spaghetti right at that line, so it slipped through. A unit test then caught a
worse one: the cheap hashing-embedding fallback matched "milk" to "Almond Milk"
(they share a lot of "milk" character n-grams). Two changes fixed it: I raised
`min_accept_score` to 0.72 and bumped the substitution penalty, and I stopped letting
the hashing embedder *accept* a match on its own. Only a real sentence-transformer is
trusted to override the fuzzy score. The takeaway I keep coming back to: a similarity
score is a knob, and a mis-tuned one will happily buy you the wrong thing.

**Open Food Facts throws transient errors under load.** Pulling categories one after
another, I'd get a 406 or a 503 on some random category mid-run. The first version let
that sink the whole run. I added retry with exponential backoff, round-robined across
mirrors, and isolated failures per category so one bad category logs a warning and the
run continues with partial results. The earlier OpenStreetMap version had the same
problem, so I'd already learned to treat upstream APIs as flaky by default.

**Small-file explosion.** Micro-batch writes create one file per batch per partition.
In the 2M-row scale test, 40 batches over 30 date partitions left 1,200 tiny files and
a full scan took about 54 ms. Compaction rewrote them to 30 files (one per partition)
and the scan dropped to about 17 ms. The fix wasn't the compaction call, it was making
it a scheduled step after the load (the DAG's optimize task) instead of something I run
by hand and forget.

**A pandas index leaked into the table.** The first Delta MERGE write quietly carried a
`__index_level_0__` column into the schema, because I handed `write_deltalake` a
DataFrame directly. Converting to Arrow with `preserve_index=False` in the IO helper
killed it. Tiny bug, but it would have shown up in every downstream read.

**Non-English products produced odd matches.** Real OFF data has entries like
"Hahnchengeschnetzeltes" (German chicken strips) that the lexical matcher would happily
return for "chicken breast". I filtered Silver to English/ASCII names (PR #7). Coverage
stayed at 100% because each category still had several English products after the cut.

**The demo numbers kept growing.** Bronze is append-only, so every time I re-ran the
build it piled on more rows, and the quality summary printed once per accumulated run.
I made the fixture build a clean deterministic rebuild and changed the demo to show only
the latest run's checks.

**Streaming duplicates and late data (by design, not yet stress-tested).** Being
straight here: the Kafka/Spark path is built and unit-tested, but I haven't pushed real
volume through it, so these are design choices rather than war stories. Producer retries
with `acks=all` give at-least-once, which means duplicates, so the consumer sink is an
idempotent Delta MERGE on `event_id`: a redelivered message upserts instead of
duplicating, which gets effectively-once without Kafka transactions. For late events,
`withWatermark("event_ts", "1 hour")` bounds the state Spark holds; anything later than
that is dropped. That's the tradeoff, bounded memory against completeness. If
completeness mattered more I'd widen the watermark and send the dropped stragglers to a
side output instead of losing them.

## Architecture tradeoffs

**Kafka vs batch-only.** The product data from OFF changes slowly, so batch plus a
`last_modified_t` watermark is the right tool there. Prices change fast, which is why
the price feed is the streaming candidate. I kept both instead of forcing everything
into one model: batch for the slow product master, streaming for the fast price events.
It's Lambda-ish, but because both land in the same Bronze Delta there's no second
serving copy to reconcile.

**DuckDB alongside Spark.** On a laptop, DuckDB plus delta-rs beats Spark easily: no
JVM, no shuffle. Spark only earns its keep once the data outgrows one machine. I didn't
want to fake a cluster on a 2M-row laptop dataset, so DuckDB is the default and Spark is
the documented distributed path. The transforms are SQL, so they move between the two.

**dbt instead of hand-written Spark SQL.** dbt gives me tests, lineage, and a
declarative model graph without building any of it myself, and it runs on DuckDB locally
and `dbt-spark` at scale with the same models. Writing the equivalent in raw Spark SQL
would mean re-inventing the testing and lineage. So dbt owns the T; Python stays the EL,
where the retry and API logic belongs.

**Delta vs Iceberg vs Hudi.** All three give ACID and time travel on object storage. I
went with Delta because delta-rs runs the whole thing locally without a JVM (Iceberg's
Python write story is thinner), the format maps one-to-one onto Databricks, and
MERGE/OPTIMIZE/Z-order are first-class. I'd reach for Iceberg if I needed real
engine-neutrality or hidden partitioning, and Hudi if record-level upserts with strong
incremental pull were the central requirement.

## What I'd do next in production

- **Observability stack.** Metrics currently live in Delta tables. I'd ship them to
  Prometheus and Grafana for real dashboards and alerts, and add OpenLineage for lineage
  across systems rather than just within dbt. Consumer lag and data freshness are the
  first two alerts I'd wire.
- **Schema registry.** The JSON `schema_version` field doesn't enforce compatibility
  across teams. I'd move to Avro or Protobuf with Confluent Schema Registry and
  compatibility checks at the broker.
- **Data contracts.** Tie that to a CI gate so a producer change that breaks the agreed
  schema can't merge. That's the piece that protects the platform from its own users,
  and it's the gap I'd close first.
- **Cost monitoring.** Track bytes scanned, file counts, and compute per pipeline and
  alert on regressions. The scale benchmark is the seed of this; partition pruning and
  compaction are the levers it would watch.
- **SLA enforcement.** Freshness SLOs per dataset, surfaced and paged when breached. The
  DAG's freshness check is a stub of this today.
