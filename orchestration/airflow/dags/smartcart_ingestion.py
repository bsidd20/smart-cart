"""Daily smart-cart ingestion DAG.

Flow: incremental ingest -> dbt build (models + tests) -> quality report -> freshness
check. Designed for a deployed Airflow (MWAA / Composer / self-hosted); locally the
same steps run via scripts/ingest.py and `dbt build`.

Production behaviours wired here:
  - retries with exponential backoff (transient API/network failures are expected)
  - catchup=True + max_active_runs=1 so historical dates can be backfilled safely,
    one run at a time (the watermark/MERGE design makes re-runs idempotent)
  - on_failure_callback to fan a failure out to Slack/PagerDuty
"""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from airflow.utils.task_group import TaskGroup

# Set as an Airflow Variable in each environment (dev/stage/prod).
REPO = "{{ var.value.get('smartcart_repo', '/opt/smartcart') }}"
LAKE = "{{ var.value.get('smartcart_lake', '/opt/smartcart/data/lake') }}"

DBT_ENV = (
    f"SMARTCART_LAKE={LAKE} "
    f"SMARTCART_MARTS={LAKE}/marts "
    "SMARTCART_DUCKDB=/tmp/smartcart_{{ ds_nodash }}.duckdb"
)


def notify_failure(context):
    """Hook for alerting. Wire to Slack/PagerDuty via a connection in real deploys."""
    ti = context["task_instance"]
    print(f"ALERT smartcart_ingestion failed: task={ti.task_id} run={context['run_id']}")


default_args = {
    "owner": "data-engineering",
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=30),
    "on_failure_callback": notify_failure,
}

with DAG(
    dag_id="smartcart_ingestion",
    description="Open Food Facts -> Delta bronze -> dbt marts, with quality gates",
    start_date=datetime(2024, 1, 1),
    schedule="0 6 * * *",        # daily at 06:00
    catchup=True,                # enable backfills of historical dates
    max_active_runs=1,           # idempotent re-runs, but serialize for safety
    default_args=default_args,
    tags=["smartcart", "ingestion", "dbt"],
) as dag:
    ingest = BashOperator(
        task_id="ingest_incremental",
        bash_command=f"cd {REPO} && .venv/bin/python scripts/ingest.py --incremental",
    )

    with TaskGroup(group_id="transform_dbt") as transform_dbt:
        dbt_seed = BashOperator(
            task_id="dbt_seed",
            bash_command=f"cd {REPO}/transform && {DBT_ENV} dbt seed --profiles-dir .",
        )
        dbt_build = BashOperator(
            task_id="dbt_build",  # runs models and data tests; non-zero exit fails the task
            bash_command=f"cd {REPO}/transform && {DBT_ENV} dbt build --profiles-dir .",
        )
        dbt_seed >> dbt_build

    quality_report = BashOperator(
        task_id="quality_report",
        bash_command=f"cd {REPO} && .venv/bin/python -m app.ingestion.quality.report",
    )

    def _check_freshness():
        # Fails the task if data is older than the SLA, which alerts via the callback.
        from app.ingestion import io, paths

        metrics = io.read_delta(paths.META_METRICS)
        fresh = metrics[metrics["metric"] == "freshness_hours"]["value"].max()
        assert fresh is not None and fresh < 48, f"data is stale: {fresh}h"

    freshness_check = PythonOperator(
        task_id="freshness_check",
        python_callable=_check_freshness,
    )

    ingest >> transform_dbt >> quality_report >> freshness_check
