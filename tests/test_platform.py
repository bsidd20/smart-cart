"""Tests for the data-platform features: quarantine and schema-drift detection."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ingestion import io, paths  # noqa: E402
from app.ingestion.metadata import schema  # noqa: E402
from app.ingestion.orchestration import pipeline  # noqa: E402


def test_quarantine_captures_bad_records():
    pipeline.run_fixture()
    assert paths.exists(paths.QUALITY_QUARANTINE)
    q = io.read_delta(paths.QUALITY_QUARANTINE)
    assert len(q) >= 1
    assert (q["quarantine_reason"].str.len() > 0).all()


def test_schema_drift_detects_added_and_removed_columns():
    cols = (schema.EXPECTED["openfoodfacts"] | {"new_field"}) - {"brands"}
    drift = schema.detect_drift("openfoodfacts", cols)
    by_col = {d["column"]: d for d in drift}
    assert by_col["new_field"]["change"] == "added_column"
    assert by_col["new_field"]["severity"] == "info"  # additive is safe
    assert by_col["brands"]["change"] == "removed_column"
    assert by_col["brands"]["severity"] == "error"  # breaking


if __name__ == "__main__":
    test_quarantine_captures_bad_records()
    test_schema_drift_detects_added_and_removed_columns()
    print("ok")
