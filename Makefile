VENV := .venv
DBT_VENV := .venv-dbt
PY := $(VENV)/bin/python
LAKE := $(CURDIR)/data/lake

.DEFAULT_GOAL := help

# --- environment ---------------------------------------------------------- #
$(PY):
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install -q --upgrade pip
	$(VENV)/bin/pip install -q -r requirements.txt -r requirements-streaming.txt ruff pytest

setup: $(PY) ## create the venv and install dependencies

$(DBT_VENV)/bin/dbt:
	python3.13 -m venv $(DBT_VENV)
	$(DBT_VENV)/bin/pip install -q -r requirements-dbt.txt

# --- run / test ----------------------------------------------------------- #
test: setup ## lint and run the test suite
	$(VENV)/bin/ruff check app scripts tests streaming spark
	$(VENV)/bin/pytest -q

lint: setup ## check lint and formatting
	$(VENV)/bin/ruff check app scripts tests streaming spark
	$(VENV)/bin/ruff format --check app scripts tests streaming spark

format: setup ## auto-format the code
	$(VENV)/bin/ruff format app scripts tests streaming spark

demo: setup ## run the end-to-end example (builds the lakehouse if needed)
	$(PY) scripts/demo.py

api: setup ## serve the API at http://127.0.0.1:8000/docs
	$(VENV)/bin/uvicorn app.main:app --reload

ingest: setup ## build the lakehouse from the committed real-data sample
	$(PY) scripts/ingest.py

ingest-live: setup ## pull fresh data from Open Food Facts (rate-limited)
	$(PY) scripts/ingest.py --live

benchmark: setup ## partition pruning + compaction on the sample data
	$(PY) scripts/benchmark.py

scale: setup ## scale benchmark (default 2,000,000 rows; override: make scale ROWS=5000000)
	$(PY) scripts/scale_simulation.py $(or $(ROWS),2000000)

# --- dbt ------------------------------------------------------------------ #
dbt: $(DBT_VENV)/bin/dbt ingest ## build dbt models and run dbt tests
	mkdir -p $(LAKE)/marts
	cd transform && SMARTCART_LAKE=$(LAKE) SMARTCART_MARTS=$(LAKE)/marts \
		$(CURDIR)/$(DBT_VENV)/bin/dbt build --profiles-dir .

dbt-docs: $(DBT_VENV)/bin/dbt ## generate and serve the dbt lineage docs
	cd transform && SMARTCART_LAKE=$(LAKE) SMARTCART_MARTS=$(LAKE)/marts \
		$(CURDIR)/$(DBT_VENV)/bin/dbt docs generate --profiles-dir . && \
		$(CURDIR)/$(DBT_VENV)/bin/dbt docs serve --profiles-dir .

# --- streaming (Docker) --------------------------------------------------- #
stream: ## start the streaming stack (Kafka + producer + consumer)
	docker compose up --build

spark: ## start the streaming stack with the Spark Structured Streaming engine
	docker compose --profile spark up --build

stream-down: ## stop and remove the streaming stack
	docker compose down

# --- misc ----------------------------------------------------------------- #
clean: ## remove generated data and caches
	rm -rf data .pytest_cache .ruff_cache **/__pycache__ transform/target transform/logs

help: ## show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

.PHONY: setup test lint format demo api ingest ingest-live benchmark scale dbt dbt-docs stream spark stream-down clean help
