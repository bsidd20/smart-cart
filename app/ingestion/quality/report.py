"""Automated data-quality validation report.

Summarizes the latest run's quality checks and exits non-zero if any error-severity
check failed, so it can act as a pipeline gate (the Airflow task fails -> alert).

    python -m app.ingestion.quality.report
"""

from __future__ import annotations

import sys

from app.ingestion import io, paths


def generate() -> int:
    if not paths.exists(paths.QUALITY_RESULTS):
        print("no quality results found")
        return 0
    df = io.read_delta(paths.QUALITY_RESULTS)
    latest = df.sort_values("checked_at")["run_id"].iloc[-1]
    df = df[df["run_id"] == latest]

    print(f"# Data quality report (run {latest})\n")
    for r in df.itertuples(index=False):
        status = "PASS" if r.passed else "FAIL"
        print(
            f"- [{status}] {r.check_name} ({r.layer}.{r.table}) "
            f"severity={r.severity} failed={r.failed_count}/{r.total_count}"
        )

    hard_fails = df[(df["severity"] == "error") & (~df["passed"])]
    if len(hard_fails):
        print(f"\n{len(hard_fails)} error-severity check(s) FAILED")
        return 1
    print("\nall error-severity checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(generate())
