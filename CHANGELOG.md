# Changelog

## Unreleased
- Language filtering for non-English Open Food Facts products (cleaner matches).
- Tracking known issues for incremental pagination, schema drift depth, and
  incremental dbt models (see GitHub issues).

## v0.2.0 - streaming and scale
- Kafka price-event stream: producer, consumer, dead-letter queue, replay, event
  schema versioning, watermark/late handling.
- Spark Structured Streaming (Kafka to Bronze) and a batch PySpark + Delta job.
- One-command stack via Docker Compose (Kafka + producer + consumer + Spark).
- Scale simulation (millions of rows) plus partition pruning, compaction, Z-order.

## v0.1.0 - batch lakehouse
- Open Food Facts ingestion into Bronze Delta with incremental watermarks.
- dbt staging/intermediate/marts with tests and lineage.
- Data quality checks, quarantine, schema-drift detection, observability tables.
- FastAPI app with the product matcher and the greedy/ILP cart optimizer.
- Airflow DAG, Terraform (S3 lakehouse, dev/stage/prod), GitHub Actions CI.
