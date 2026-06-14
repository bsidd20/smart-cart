"""Schema-drift detection.

We register the columns we expect from each source. On every ingest we compare the
incoming columns to that contract and log any drift:

  - added columns   -> safe (Delta supports schema evolution); landed and logged
  - removed columns -> breaking (downstream models depend on them); logged as error

Tradeoff: additive evolution is allowed automatically so new upstream fields don't
break ingestion, but removals are surfaced loudly because they break contracts. The
alternative (reject any change) is safer but brittle; the alternative (accept any
change silently) is convenient but how pipelines rot.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from app.ingestion import io, paths

# the columns each source is contracted to provide (the raw extracted fields)
EXPECTED: dict[str, set[str]] = {
    "openfoodfacts": {
        "barcode",
        "product_name",
        "brands",
        "categories_tags",
        "quantity",
        "lang",
        "last_modified_t",
        "taxonomy_key",
        "raw_payload",
    },
}


def detect_drift(source: str, actual_columns: set[str]) -> list[dict]:
    expected = EXPECTED.get(source, set())
    drift = []
    for col in sorted(actual_columns - expected):
        drift.append({"change": "added_column", "column": col, "severity": "info"})
    for col in sorted(expected - actual_columns):
        drift.append({"change": "removed_column", "column": col, "severity": "error"})
    return drift


def log_drift(run_id: str, source: str, drift: list[dict]) -> None:
    if not drift:
        return
    now = datetime.now(timezone.utc).isoformat()
    rows = [{"run_id": run_id, "source": source, "detected_at": now, **d} for d in drift]
    io.write_delta(pd.DataFrame(rows), paths.META_SCHEMA_DRIFT, mode="append")
