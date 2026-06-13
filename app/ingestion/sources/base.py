"""Source interface. A source knows how to fetch raw records, optionally only
those changed since a per-category watermark (for incremental loads)."""
from __future__ import annotations

from typing import Protocol


class Source(Protocol):
    name: str
    schema_version: str

    def fetch(self, since_ts: dict[str, int] | None = None) -> list[dict]:
        ...
