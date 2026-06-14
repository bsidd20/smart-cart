"""Gold serving + analytics tables built from Silver.

product_catalog       - clean product master (search, browse, enrichment joins)
store_product_offers  - denormalized store x product x price; what the app serves
category_price_stats  - per-category price spread (merchandising / price checks)
cheapest_products     - cheapest store per product (deals, price comparison)
product_search_index  - per-product search terms + availability (typeahead/matching)
"""

from __future__ import annotations

from app.ingestion import io, paths


def build() -> None:
    catalog = io.sql(
        """
        SELECT barcode AS product_id, product_name, brands, category, product_group,
               size_value, size_unit, base_price, search_terms
        FROM product
        """,
        product=paths.SILVER_DIM_PRODUCT,
    )
    io.write_delta(catalog, paths.GOLD_PRODUCT_CATALOG)

    offers = io.sql(
        """
        SELECT s.store_id, s.name AS store_name, s.chain, s.lat, s.lon,
               p.barcode AS product_id, p.product_name, p.category,
               coalesce(p.size_unit, 'each') AS unit, p.search_terms,
               i.price, i.in_stock
        FROM inv i
        JOIN store s ON i.store_id = s.store_id
        JOIN product p ON i.barcode = p.barcode
        """,
        inv=paths.SILVER_FACT_INVENTORY,
        store=paths.SILVER_DIM_STORE,
        product=paths.SILVER_DIM_PRODUCT,
    )
    io.write_delta(offers, paths.GOLD_OFFERS)

    stats = io.sql(
        """
        SELECT category,
               count(DISTINCT product_id) AS num_products,
               count(*) AS num_offers,
               round(min(price), 2) AS min_price,
               round(avg(price), 2) AS avg_price,
               round(max(price), 2) AS max_price,
               arg_min(store_name, price) AS cheapest_store
        FROM offers WHERE in_stock
        GROUP BY category ORDER BY category
        """,
        offers=paths.GOLD_OFFERS,
    )
    io.write_delta(stats, paths.GOLD_CATEGORY_PRICE_STATS)

    cheapest = io.sql(
        """
        WITH ranked AS (
            SELECT *, row_number() OVER (
                PARTITION BY product_id ORDER BY price) AS rn
            FROM offers WHERE in_stock
        )
        SELECT product_id, product_name, category,
               round(price, 2) AS cheapest_price, store_name AS cheapest_store
        FROM ranked WHERE rn = 1 ORDER BY category, cheapest_price
        """,
        offers=paths.GOLD_OFFERS,
    )
    io.write_delta(cheapest, paths.GOLD_CHEAPEST_PRODUCTS)

    search_index = io.sql(
        """
        SELECT product_id, any_value(product_name) AS product_name,
               any_value(category) AS category, any_value(search_terms) AS search_terms,
               count(*) FILTER (WHERE in_stock) AS num_stores_in_stock,
               round(min(price), 2) AS min_price
        FROM offers GROUP BY product_id
        """,
        offers=paths.GOLD_OFFERS,
    )
    io.write_delta(search_index, paths.GOLD_PRODUCT_SEARCH_INDEX)
