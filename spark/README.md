# spark

PySpark + Delta jobs for the streaming and large-scale paths. Spark needs a JVM, so
these run in the Spark container (no local Java required).

## Structured Streaming (Kafka -> Bronze Delta)

```bash
docker compose --profile spark up --build   # Kafka + producer + Spark streaming job
```

That single command starts Kafka, the producer (feeds events), and the Spark
Structured Streaming job. `stream_bronze.py` reads `price-events`, parses + watermarks,
and upserts into Bronze Delta with an idempotent MERGE inside `foreachBatch`. Offsets
and state are checkpointed, so a restart resumes exactly-once.

## Batch transform (Bronze -> Silver)

```bash
docker compose run --rm spark-stream spark-submit \
  --packages io.delta:delta-spark_2.12:3.2.0 \
  --conf spark.sql.extensions=io.delta.sql.DeltaSparkSessionExtension \
  --conf spark.sql.catalog.spark_catalog=org.apache.spark.sql.delta.catalog.DeltaCatalog \
  /app/spark/batch_silver.py milk        # optional category -> partition pruning
```

## When to use Spark vs the local path

On a laptop the DuckDB + dbt path is faster (no JVM, no shuffle overhead). Spark earns
its keep once the data no longer fits one machine: it parallelizes the same partitioned
reads, window dedup, and MERGE across a cluster. The dbt models are plain SQL, so they
port to `dbt-spark` unchanged - the engine changes, not the logic.
