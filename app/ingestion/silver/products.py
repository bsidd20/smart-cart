"""Silver product dimension built from Bronze raw products.

Steps: pick the latest row per barcode (DuckDB window function), trim/clean, drop
malformed rows, normalize units, map to our category taxonomy, assign a modeled
base price, and build search terms. The result is MERGEd into the dimension so
re-runs upsert changed products (incremental + late-arriving handling).
"""

from __future__ import annotations

import re

from app.ingestion import io, paths
from app.ingestion.category_map import TAXONOMY

_UNIT_TO_CANON = {  # -> (canonical_unit, factor)
    "kg": ("g", 1000.0),
    "g": ("g", 1.0),
    "mg": ("g", 0.001),
    "l": ("ml", 1000.0),
    "ml": ("ml", 1.0),
    "cl": ("ml", 10.0),
    "oz": ("g", 28.3495),
    "lb": ("g", 453.592),
    "fl oz": ("ml", 29.5735),
    "floz": ("ml", 29.5735),
}


def _parse_quantity(q) -> tuple[float | None, str | None]:
    if not isinstance(q, str):
        return None, None
    m = re.search(r"(\d+(?:\.\d+)?)\s*(fl\s*oz|floz|kg|mg|cl|ml|oz|lb|g|l)\b", q.lower())
    if not m:
        return None, None
    value, unit = float(m.group(1)), m.group(2).replace(" ", "")
    canon, factor = _UNIT_TO_CANON.get(unit, (None, None))
    return (round(value * factor, 2), canon) if canon else (None, None)


def _base_price(barcode: str, taxonomy_key: str) -> float:
    base = TAXONOMY[taxonomy_key]["base_price"]
    digits = re.sub(r"\D", "", barcode)[-4:] or "0"
    factor = 0.85 + (int(digits) % 31) / 100.0  # deterministic 0.85..1.15
    return round(base * factor, 2)


def _search_terms(name: str, brand, taxonomy_key: str) -> str:
    cfg = TAXONOMY[taxonomy_key]
    term = cfg["term"]
    name_l = name.lower()
    # Don't tag plant milks (etc.) with the generic dairy term, even though OFF files
    # them under the same category - it would make "milk" match "almond milk".
    add_term = not any(x in name_l for x in cfg.get("exclude", []))
    toks = re.findall(r"[a-z0-9]+", f"{name} {brand or ''}".lower())
    toks = [t for t in toks if len(t) > 1]
    ordered = ([term] if add_term else []) + [t for t in toks if t != term]
    seen, out = set(), []
    for t in ordered:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return "|".join(out[:10])


def build() -> tuple[int, int]:
    """Returns (rows_written, rows_rejected)."""
    latest = io.sql(
        """
        WITH ranked AS (
            SELECT *, row_number() OVER (
                PARTITION BY barcode
                ORDER BY last_modified_t DESC, ingested_at DESC) AS rn
            FROM bronze
        )
        SELECT trim(barcode) AS barcode, trim(product_name) AS product_name,
               brands, categories_tags, quantity, lang, last_modified_t, taxonomy_key
        FROM ranked WHERE rn = 1
        """,
        bronze=paths.BRONZE_RAW_PRODUCTS,
    )
    before = len(latest)

    # null handling / drop malformed: need a barcode, a name, and a known category
    clean = latest[
        (latest["barcode"].str.len() > 0)
        & (latest["product_name"].str.len() > 0)
        & (latest["taxonomy_key"].isin(TAXONOMY.keys()))
    ].copy()
    rejected = before - len(clean)

    # keep English, ASCII-named products: raw OFF data contains non-English entries
    # that the lexical matcher picks up oddly (e.g. "Hahnchengeschnetzeltes" for
    # chicken breast). See issue #5.
    clean = clean[
        (clean["lang"].isna() | clean["lang"].isin(["en", ""]))
        & clean["product_name"].map(lambda s: s.isascii())
    ].copy()

    clean["product_name"] = clean["product_name"].str.replace(r"\s+", " ", regex=True).str.strip()
    clean["category"] = clean["taxonomy_key"]
    clean["product_group"] = clean["taxonomy_key"].map(lambda k: TAXONOMY[k]["group"])
    qty = clean["quantity"].map(_parse_quantity)
    clean["size_value"] = [v for v, _ in qty]
    clean["size_unit"] = [u for _, u in qty]
    clean["base_price"] = [
        _base_price(b, k) for b, k in zip(clean["barcode"], clean["taxonomy_key"])
    ]
    clean["search_terms"] = [
        _search_terms(n, br, k)
        for n, br, k in zip(clean["product_name"], clean["brands"], clean["taxonomy_key"])
    ]

    out = clean[
        [
            "barcode",
            "product_name",
            "brands",
            "category",
            "product_group",
            "size_value",
            "size_unit",
            "base_price",
            "search_terms",
            "categories_tags",
            "last_modified_t",
        ]
    ]
    io.upsert_delta(out, paths.SILVER_DIM_PRODUCT, key="barcode", partition_by=["category"])
    return len(out), rejected
