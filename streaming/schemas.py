"""Versioned event schemas for price events.

Every event carries a `schema_version`. The consumer accepts any known version,
validates against that version's contract, and upgrades older events to the latest
shape so downstream code only deals with one schema. The event contract can then
evolve without a coordinated big-bang producer/consumer deploy.

  v1: schema_version, event_id, store_id, product_id, price, observed_at
  v2: adds in_stock and currency
"""

from __future__ import annotations

import json

LATEST_VERSION = 2

REQUIRED_FIELDS: dict[int, set[str]] = {
    1: {"event_id", "store_id", "product_id", "price", "observed_at"},
    2: {"event_id", "store_id", "product_id", "price", "observed_at", "in_stock", "currency"},
}


def serialize(event: dict) -> bytes:
    return json.dumps(event).encode("utf-8")


def deserialize(raw: bytes) -> dict:
    return json.loads(raw)


def validate(event: dict) -> tuple[bool, str | None]:
    version = event.get("schema_version")
    if version not in REQUIRED_FIELDS:
        return False, f"unknown schema_version: {version!r}"
    missing = REQUIRED_FIELDS[version] - event.keys()
    if missing:
        return False, f"missing fields for v{version}: {sorted(missing)}"
    price = event.get("price")
    if not isinstance(price, (int, float)) or isinstance(price, bool) or price <= 0:
        return False, f"invalid price: {price!r}"
    return True, None


def upgrade(event: dict) -> dict:
    """Migrate any known version to LATEST_VERSION (forward-compatible)."""
    out = dict(event)
    if out.get("schema_version", 1) == 1:
        out.setdefault("in_stock", True)
        out.setdefault("currency", "USD")
        out["schema_version"] = 2
    return out
