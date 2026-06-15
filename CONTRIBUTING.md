# Contributing

Notes for working in this repo (mostly for future me).

## Prerequisites

- Python 3.13 (dbt) and 3.11+ for the app. The app code runs on 3.13 and 3.14; dbt
  needs 3.13.
- Docker, only if you want the Kafka/Spark streaming path.
- Java is not required locally. Spark runs in a container.

## Getting set up

Everything common is in the Makefile (`make help`):

```bash
make demo        # build the lakehouse from the sample and run the example
make test        # ruff + the test suite
make api         # FastAPI at http://127.0.0.1:8000/docs
make dbt         # build dbt models and run dbt tests (creates the 3.13 venv)
make stream      # Kafka + producer + consumer (Docker)
```

`make setup` creates the venv and installs deps; the other targets call it
automatically, so you usually do not run it directly.

## How the repo is laid out

```
app/            the application: ingestion platform + matcher + optimizer + API
  ingestion/    sources, bronze, silver, gold, metadata, quality, orchestration
  data/         the repository that reads Gold
  matching/     fuzzy + semantic matching
  optimization/ ranking, greedy, ILP
transform/      dbt project (the transform layer)
streaming/      Kafka producer/consumer, DLQ, replay, schema versioning
spark/          PySpark + Delta jobs (run in the Spark container)
orchestration/  Airflow DAG
infra/          Terraform (S3 lakehouse, dev/stage/prod)
scripts/        ingest, demo, benchmark, scale_simulation
tests/          tests + the committed real-data fixture
docs/           architecture, decisions, and the per-area design docs
```

The data flows Open Food Facts -> Bronze (Delta) -> dbt Silver/Gold -> serving. Python
does extract and load, dbt does transform. See `docs/ARCHITECTURE.md` and
`docs/DECISIONS.md`.

## Conventions

- **Style**: ruff for lint and format (`make lint`, `make format`). 100-col lines.
- **Tests**: `pytest`. New behavior gets a test. The streaming logic is tested without a
  broker by injecting fakes; keep it that way so CI does not need Kafka.
- **dbt**: data contracts live in the `_models.yml` files next to the models. Add tests
  there, not as one-off scripts.
- **Data**: `data/` is generated and gitignored. The committed sample is
  `tests/fixtures/off_products_sample.json`. Rebuild with `make ingest`.

## Adding things

- **A new source**: implement the `Source` protocol in `app/ingestion/sources/`, land it
  in Bronze, register the expected schema in `metadata/schema.py`.
- **A new mart**: add the model under `transform/models/marts/`, document and test it in
  the matching `_models.yml`.
- **A new quality check**: add it to `app/ingestion/quality/checks.py` with a severity;
  `error` checks are contracts, `warn` checks are tracked noise.

## Known limitations

Tracked in the GitHub issues and summarized in the README. If you pick one up, the fix
notes are usually in the issue.
