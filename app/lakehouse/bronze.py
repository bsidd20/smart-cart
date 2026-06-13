"""Bronze: land the raw feeds as-is, no cleaning.

Stores and products are written once. Price events are appended one day at a time,
so the Delta table accumulates versions (and time travel works) the same way a daily
ingestion job would build it up.
"""
from __future__ import annotations

import pandas as pd

from app.lakehouse import io, paths


def ingest(raw: dict) -> None:
    io.write_delta(pd.DataFrame(raw["stores"]), paths.BRONZE_STORES, mode="overwrite")
    io.write_delta(pd.DataFrame(raw["products"]), paths.BRONZE_PRODUCTS, mode="overwrite")

    events = raw["price_events"]
    days = sorted({e["observed_at"][:10] for e in events})
    for i, day in enumerate(days):
        batch = [e for e in events if e["observed_at"].startswith(day)]
        io.write_delta(pd.DataFrame(batch), paths.BRONZE_PRICE_EVENTS,
                       mode="overwrite" if i == 0 else "append")
