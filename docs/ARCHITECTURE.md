# Architecture

smart-cart is a data platform with a small application on top. The platform ingests
real product data, refines it through a medallion lakehouse, validates it, and serves
governed marts; the grocery optimizer is one consumer of those marts.

## Components (current)

```mermaid
flowchart LR
  OFF[Open Food Facts API] -->|sources/openfoodfacts.py| BR
  subgraph Lakehouse[Delta Lake]
    BR[Bronze\nraw_products / raw_stores / raw_price_events] --> SV[Silver / dbt int_*\ndeduped, typed, normalized]
    SV --> GD[Gold / dbt marts\nproduct_catalog, store_product_offers,\ncategory_price_stats, cheapest_products, search_index]
  end
  BR -. schema drift .-> META[(meta:\nruns, watermarks, metrics, schema_drift)]
  SV -. checks .-> QA[(quality:\nquality_results, quarantine)]
  GD --> API[FastAPI]
  API --> OPT[matcher + optimizer]
  GD --> BI[analytics / BI]
```

dbt owns the transforms (staging -> intermediate -> marts); Python owns ingestion
(extract + load) and serving. dbt reads the Bronze Delta tables via DuckDB `delta_scan`.

## Data flow

```mermaid
flowchart TD
  A[Incremental pull\nlast_modified_t watermark] --> B[Bronze append\n+ run metadata]
  B --> C{Schema drift?}
  C -->|added col| D[log info, allow]
  C -->|removed col| E[log error]
  B --> F[Quarantine malformed]
  B --> G[dbt build:\nstaging -> intermediate -> marts]
  G --> H[dbt tests +\nquality_results]
  H -->|all error checks pass| I[Marts ready]
  H -->|hard failure| J[fail run + alert]
  I --> K[App serves / BI queries]
```

## Target cloud architecture (AWS)

```mermaid
flowchart LR
  subgraph AWS
    S3[(S3 data lake\nbronze/silver/gold, KMS, versioned)]
    MWAA[Airflow / MWAA] --> ING[Ingestion task\nECS/Fargate]
    ING --> S3
    MWAA --> DBT[dbt build\nECS task]
    DBT --> S3
    GLUE[Glue Catalog] --- S3
    ATHENA[Athena / Databricks SQL] --- S3
  end
  GH[GitHub Actions CI] -->|plan/apply| TF[Terraform]
  TF --> AWS
  CW[CloudWatch alarms] -. freshness/failure .-> MWAA
```

Environment isolation (dev/stage/prod) is enforced by separate Terraform state,
buckets, and IAM roles (`infra/`).

## CI/CD

```mermaid
flowchart LR
  PR[push / PR] --> L[ruff lint + format check]
  L --> T[pytest: app + platform]
  T --> D[ingest fixture -> dbt seed/build/test]
  D --> M{all green?}
  M -->|yes| OK[merge / deploy]
  M -->|no| X[block]
```

`.github/workflows/ci.yml` runs lint, tests, and a full dbt build+test on the
committed real-data sample, so data-quality regressions block the merge.

## Layer-to-platform mapping

| This repo (local, free) | AWS | Databricks / Snowflake |
|--|--|--|
| Delta via delta-rs | Delta on S3 | Delta Lake / Iceberg |
| DuckDB + dbt | dbt on ECS, Athena | Spark/Photon, Snowflake |
| Airflow DAG | MWAA / Composer | Workflows / DLT, Tasks |
| watermark + MERGE | same | Structured Streaming + MERGE / Streams+Tasks |
| quality_results + dbt tests | same + CloudWatch | DLT expectations / Snowflake DMFs |
| meta tables | + Glue/Unity lineage | Unity Catalog / Horizon |
| Terraform | Terraform | Terraform |

## Production practices

- **Configuration**: all tunables in `app/config.py`; pipeline paths in
  `app/ingestion/paths.py`; environment-specific values via env vars
  (`SMARTCART_LAKE`, dbt `profiles.yml` targets dev/prod).
- **Secrets**: none committed; cloud credentials come from the runtime role
  (IAM via `infra/`), API keys from env/secret store, never source.
- **Error handling**: ingestion retries with backoff and isolates per-source
  failures (one bad category does not fail the run); the run status is recorded.
- **Logging/observability**: every run writes to `ingestion_runs`, `ingestion_metrics`
  (row counts, freshness), `schema_drift`, and `quality_results`; the report module
  and freshness task act as gates.
- **Testing**: `pytest` for app + platform behavior, dbt tests for data contracts,
  ruff for style; all enforced in CI.

## Design decisions

- **dbt for T, Python for EL**: transforms are declarative SQL with tests and lineage;
  extraction/landing stays in Python where retries and API logic live.
- **Bronze append-only, Silver MERGE**: replayable raw history plus a small current-
  state layer; reprocessing always starts from Bronze.
- **Quarantine over drop**: bad records are inspectable and replayable, not lost.
- **Additive schema evolution allowed, removals flagged**: new upstream fields don't
  break ingestion; removed fields surface loudly because models depend on them.
- **Modeled pricing behind a seam**: no free price API exists, so pricing is modeled
  on the real product master and isolated to one module for a clean swap.
