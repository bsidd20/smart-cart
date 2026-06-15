# smart-cart

Turn a grocery list into a shopping plan. Given items like
`["chicken breast", "rice", "eggs", "milk", "spinach"]`, it returns the best single
store to buy everything, the cheapest practical multi-store split, and a short reason
for each item.

The shopping app is the small part. The bulk of this repo is the data platform behind
it: real product data pulled from [Open Food Facts](https://world.openfoodfacts.org)
into a Delta Lake medallion (Bronze/Silver/Gold), transformed by dbt, validated, and
served as Gold marts, with both batch and streaming ingestion. It runs locally and free
on delta-rs, DuckDB, and dbt, and is laid out to lift onto AWS (Terraform) with Airflow
and CI.

## Why this exists

I wanted to build a modern lakehouse end to end rather than the usual single slice. Most
examples stop at "read a CSV into a table"; the parts that are actually hard, like
incremental loading, schema evolution, quality gates, partitioning, and streaming, get
skipped. So I built all of it on free tools and made the grocery optimizer the consumer,
because a real consumer forces the data to be correct and useful in a way a dashboard
does not. Using real Open Food Facts data (messy, multilingual, full of gaps) kept it
honest. It was built as a focused sprint, then hardened as I found problems.

There is no free real-time grocery price API, so pricing is modeled on top of the real
product master and isolated to one module. That seam is labeled on purpose; I would
rather have honest data with a clear swap point than a fabricated price source.

## Setup

Common tasks are in the Makefile (`make help`):

```bash
make demo        # build the lakehouse from the sample and run the example
make test        # lint + test suite
make api         # API at http://127.0.0.1:8000/docs
make scale       # 2M-row partition-pruning + compaction benchmark
make dbt         # build dbt models and run dbt tests (creates a python3.13 venv)
make stream      # Kafka + producer + consumer via Docker
```

Or directly: `pip install -r requirements.txt`, then `python scripts/ingest.py` and
`python scripts/demo.py`. `python scripts/ingest.py --live` pulls fresh data from Open
Food Facts (rate-limited).

## Architecture

```
 Open Food Facts -> BRONZE (raw, append-only) -> SILVER (clean, MERGE) -> GOLD (serving) -> API
 Kafka price events ->                       (Spark Structured Streaming)
                      + meta (runs, watermarks, metrics) + quality (checks, quarantine)
```

Python does extract and load; dbt does transform. Bronze is the append-only replay log;
Silver is the current state maintained with Delta MERGE; Gold is denormalized for
serving. The full picture is in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), and the
reasoning behind each choice (Delta vs Iceberg, DuckDB vs Spark, dbt vs Spark SQL, and
so on) is in [docs/DECISIONS.md](docs/DECISIONS.md).

The platform pieces:
- **dbt** (`transform/`): staging -> intermediate -> marts, with data tests and lineage.
- **Streaming** (`streaming/`, `spark/`): Kafka price events -> Spark Structured
  Streaming -> Bronze, with a dead-letter queue, replay, schema versioning, and
  watermarks. The whole stack runs with `docker compose up --build`; the logic is also
  unit-tested without a broker. See [docs/STREAMING.md](docs/STREAMING.md).
- **Quality + observability**: per-run check results, quarantine for bad records, schema
  drift detection, row counts, and freshness, exposed at `/ingestion/quality` and
  `/ingestion/runs`.
- **Partitioning + performance**: partitioned by category/date; compaction and Z-order.
  `scripts/scale_simulation.py` benchmarks it at 2M rows. See
  [docs/PERFORMANCE.md](docs/PERFORMANCE.md) and [docs/SCALE.md](docs/SCALE.md).
- **Orchestration** (`orchestration/airflow/`): a daily DAG with retries/backoff,
  backfills, an optimize step, and quality gates.
- **Cloud / CI** (`infra/`, CI): Terraform for an S3 lakehouse (dev/stage/prod), and a
  GitHub Actions pipeline that lints, tests, and runs dbt build+test.

## Endpoints

- `GET /stores` - stores near the user with distances
- `POST /match-items` - `{"items": ["milk", "spinach"]}` -> best product per item
- `POST /optimize-cart` - `{"items": [...], "max_stores": 3}` -> single-store plan,
  multi-store plan, and per-item reasons
- `GET /price-stats`, `GET /cheapest` - analytics from Gold
- `GET /ingestion/runs`, `GET /ingestion/quality` - run history and quality results

## Matching and optimization

Each list item is matched to a product at each store: fuzzy matching (RapidFuzz) for
typos and word order, with an optional embedding matcher for meaning. A score threshold
keeps bad substitutions out (so "spinach" does not match "spaghetti"), and the cheap
hashing-embedding fallback is not trusted to accept a match on its own.

The optimizer minimizes one objective:

```
price*basket + distance*round_trip_km + subs*sum(1 - match_score)
  + visit*num_stores + coverage*num_missing
```

The greedy solver starts from each item's cheapest store, consolidates to `max_stores`,
and drops any store not worth the trip. The weights in `app/config.py` are the knobs:
raise the distance/visit weights and plans collapse to one store; lower them and they
fan out to cheaper stores. `ortools_solver.py` solves the same objective exactly when
OR-Tools is available.

## When things break

How the system behaves under the failures that matter, and where it is honestly weak:

- **Upstream API flaky** (Open Food Facts returns 406/503 under load): retry with
  backoff, round-robin across mirrors, and per-category isolation, so one bad category
  logs a warning and the run finishes with partial results.
- **Duplicate stream events**: at-least-once delivery means duplicates, so the consumer
  sink is an idempotent Delta MERGE on `event_id`. Redelivery upserts, not duplicates.
- **Malformed records**: routed to a quarantine table with a reason, not dropped, so the
  run keeps moving and bad data stays inspectable.
- **Partial batch run**: per-category isolation keeps the run alive, but there is no
  atomic run boundary yet, so a downstream reader can see a partially-loaded day. Known
  gap; the fix is a stage-then-swap or a `run_id` gate.
- **Corrupt file**: Delta's transaction log protects metadata, and Bronze is replayable,
  so recovery is time-travel to a prior version or re-deriving Silver/Gold from Bronze.
  There is no automated corruption check; that is a gap.
- **Late events**: `withWatermark` bounds the state Spark holds; events later than the
  watermark are dropped. That is the memory-vs-completeness tradeoff, and I would add a
  side output for stragglers if completeness mattered more.

## Scaling

The levers are partition pruning and compaction, both measured in the 2M-row simulation:
a one-day query opens ~1/30 of the files (about 3.6x faster), and compaction collapsed
1,200 small files to 30 and sped full scans ~3x. Those ratios hold at any size.

The path past one machine is Spark: the dbt models are SQL, so they run on `dbt-spark`
unchanged, and `spark/` has the equivalent PySpark + Delta jobs. The honest limits: the
MERGE keys are not the partition keys, so MERGE cannot prune partitions at very large
scale; the dbt marts are full-refresh; and I have not run this past a few million rows.
See [docs/SCALE.md](docs/SCALE.md).

## Known limitations

The weak spots I would harden before calling this production-grade (tracked in the
issues):

- Incremental pull fetches one page per category, so a category with more than a page of
  changes between runs would miss some. Needs cursor pagination.
- Schema-drift detection compares the extracted column set, not the raw upstream payload,
  so it catches our-side changes but not arbitrary upstream ones. A schema registry fixes
  this.
- MERGE keys are not aligned with partition keys (see Scaling).
- dbt marts are full-refresh, not incremental.
- Matching is lexical, so messy or non-English data still produces the occasional odd
  pick. Real sentence embeddings would help.
- Pricing is modeled (no free price feed exists), isolated for a clean swap.
- OR-Tools has no wheel for current Python, so the exact solver is optional.

The bugs I actually hit and what I changed are in [docs/NOTES.md](docs/NOTES.md).
Contributing and onboarding notes are in [CONTRIBUTING.md](CONTRIBUTING.md).

## Layout

```
app/
  main.py            FastAPI app
  ingestion/         sources, bronze, silver, gold, metadata, quality, orchestration
  data/              repository (reads Gold)
  matching/          fuzzy, semantic, orchestrator
  optimization/      ranking, greedy, ortools
transform/           dbt project (staging -> intermediate -> marts, tests, lineage)
streaming/           Kafka producer/consumer, DLQ, replay, schema versioning
spark/               PySpark + Delta: Structured Streaming + batch jobs
orchestration/airflow/  daily DAG (retries, backfills, optimize, quality gates)
infra/               Terraform: S3 lakehouse, dev/stage/prod
docker-compose.yml   one-command stack: Kafka (KRaft) + UI + producer + consumer + Spark
scripts/             ingest, demo, benchmark, scale_simulation
tests/               app + platform + streaming tests, real-data fixture
docs/                ARCHITECTURE, DECISIONS, INGESTION, PERFORMANCE, STREAMING, SCALE, NOTES
```
