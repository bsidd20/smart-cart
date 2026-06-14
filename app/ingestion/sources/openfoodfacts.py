"""Open Food Facts source (https://world.openfoodfacts.org).

Free, no auth, real products with barcodes, brands, categories, and a
last_modified_t timestamp we use as the incremental watermark. We pull per
taxonomy category, filtered to one country for quality, and keep only records
newer than the category's watermark.
"""

from __future__ import annotations

import json
import time

import httpx

from app.ingestion.category_map import TAXONOMY

BASE = "https://world.openfoodfacts.org/api/v2/search"
USER_AGENT = "smart-cart/1.0 (+https://github.com/bsidd20/smart-cart)"
FIELDS = "code,product_name,brands,categories_tags_en,quantity,nutriments,last_modified_t,lang"


class OpenFoodFactsSource:
    name = "openfoodfacts"
    schema_version = "off_v2"

    def __init__(
        self,
        country: str = "United-States",
        page_size: int = 100,
        max_pages: int = 1,
        delay_s: float = 6.0,
    ):
        self.country = country
        self.page_size = page_size
        self.max_pages = max_pages
        self.delay_s = delay_s  # OFF asks for <=10 search req/min

    def fetch(self, since_ts: dict[str, int] | None = None) -> list[dict]:
        since_ts = since_ts or {}
        records: list[dict] = []
        for i, (tkey, cfg) in enumerate(TAXONOMY.items()):
            if i:
                time.sleep(self.delay_s)  # stay under the search rate limit
            try:
                records.extend(
                    self._fetch_category(tkey, cfg["off_category"], since_ts.get(tkey, 0))
                )
            except Exception as exc:  # isolate failures to one category
                print(f"  [warn] category '{tkey}' failed after retries: {exc}")
        return records

    def _get(self, params: dict, retries: int = 4) -> httpx.Response:
        """GET with exponential backoff on transient/5xx/429 responses."""
        transient = {408, 425, 429, 500, 502, 503, 504}
        last = None
        for attempt in range(retries):
            try:
                resp = httpx.get(
                    BASE,
                    params=params,
                    headers={"User-Agent": USER_AGENT},
                    timeout=60,
                    follow_redirects=True,
                )
                if resp.status_code in transient:
                    raise httpx.HTTPStatusError(
                        f"{resp.status_code}", request=resp.request, response=resp
                    )
                resp.raise_for_status()
                return resp
            except Exception as exc:
                last = exc
                time.sleep(self.delay_s * (2**attempt))
        raise RuntimeError(f"all retries failed: {last}")

    def _fetch_category(self, tkey: str, off_category: str, watermark: int) -> list[dict]:
        out: list[dict] = []
        for page in range(1, self.max_pages + 1):
            params = {
                "categories_tags_en": off_category,
                "countries_tags_en": self.country,
                "fields": FIELDS,
                "page_size": self.page_size,
                "page": page,
                "sort_by": "last_modified_t",
            }
            resp = self._get(params)
            products = resp.json().get("products", [])
            if not products:
                break
            for p in products:
                lm = int(p.get("last_modified_t") or 0)
                if lm <= watermark:  # incremental: skip unchanged products
                    continue
                out.append(
                    {
                        "barcode": str(p.get("code") or "").strip(),
                        "product_name": (p.get("product_name") or "").strip(),
                        "brands": p.get("brands"),
                        "categories_tags": "|".join(p.get("categories_tags_en") or []),
                        "quantity": p.get("quantity"),
                        "lang": p.get("lang"),
                        "last_modified_t": lm,
                        "taxonomy_key": tkey,
                        "raw_payload": json.dumps(p, ensure_ascii=False),
                    }
                )
            if len(products) < self.page_size:
                break
            time.sleep(self.delay_s)
        return out
