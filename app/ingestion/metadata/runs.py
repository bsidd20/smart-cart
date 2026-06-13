"""Ingestion run tracking and per-category watermarks.

Runs are append-only (an audit log). Watermarks are upserted so the next run only
pulls products modified since the last successful run.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pandas as pd

from app.ingestion import io, paths


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def start_run(source: str, mode: str) -> dict:
    return {"run_id": uuid.uuid4().hex[:12], "source": source, "mode": mode,
            "started_at": _now(), "finished_at": "", "status": "running",
            "rows_ingested": 0, "rows_rejected": 0, "duration_s": 0.0}


def finish_run(run: dict, rows_ingested: int, rows_rejected: int,
               duration_s: float, status: str = "success") -> dict:
    run.update(finished_at=_now(), status=status, rows_ingested=int(rows_ingested),
               rows_rejected=int(rows_rejected), duration_s=round(duration_s, 3))
    io.write_delta(pd.DataFrame([run]), paths.META_RUNS, mode="append")
    return run


def get_watermarks(source: str) -> dict[str, int]:
    if not paths.exists(paths.META_WATERMARKS):
        return {}
    df = io.read_delta(paths.META_WATERMARKS)
    df = df[df["source"] == source]
    return {c: int(ts) for c, ts in zip(df["category"], df["watermark_ts"])}


def set_watermarks(source: str, watermarks: dict[str, int]) -> None:
    rows = [{"wm_key": f"{source}|{cat}", "source": source, "category": cat,
             "watermark_ts": int(ts), "updated_at": _now()}
            for cat, ts in watermarks.items()]
    if rows:
        io.upsert_delta(pd.DataFrame(rows), paths.META_WATERMARKS, "wm_key")
