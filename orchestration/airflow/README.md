# orchestration (Airflow)

`dags/smartcart_ingestion.py` is the daily pipeline DAG:

```
ingest_incremental -> [dbt_seed -> dbt_build] -> quality_report -> freshness_check
```

- **Retries / backoff**: 3 retries with exponential backoff (transient API failures).
- **Backfills**: `catchup=True` + `max_active_runs=1`; the watermark + MERGE design
  makes re-runs idempotent, so `airflow dags backfill smartcart_ingestion -s <date>`
  is safe.
- **Failure alerts**: `on_failure_callback` (wire to Slack/PagerDuty per environment).
- **Quality gate**: `dbt_build` runs data tests; `quality_report` exits non-zero on any
  error-severity failure; `freshness_check` fails if data is older than the SLA.

Set Airflow Variables `smartcart_repo` and `smartcart_lake` per environment. Targets
MWAA / Cloud Composer / self-hosted Airflow 2.x.

Dagster is a strong alternative (native dbt asset integration, asset lineage,
declarative backfills); Airflow is used here for its ubiquity at the target companies.
