"""Gold: serving and analytics tables joined from the Silver layer.

store_product_offers is the denormalized table the app serves from. The other two
are analytics: per-product price stats and a per-store price index.
"""
from __future__ import annotations

from app.lakehouse import io, paths


def build() -> None:
    offers = io.sql(
        """
        SELECT s.store_id, s.name AS store_name, s.chain, s.lat, s.lon,
               p.product_id, p.name AS product_name, p.category, p.unit, p.search_terms,
               i.price, i.in_stock
        FROM inv i
        JOIN store s ON i.store_id = s.store_id
        JOIN product p ON i.product_id = p.product_id
        """,
        inv=paths.SILVER_FACT_INVENTORY,
        store=paths.SILVER_DIM_STORE,
        product=paths.SILVER_DIM_PRODUCT,
    )
    io.write_delta(offers, paths.GOLD_OFFERS)

    price_stats = io.sql(
        """
        SELECT p.product_id, p.name AS product_name, p.category,
               count(*) AS num_stores,
               round(min(i.price), 2) AS min_price,
               round(avg(i.price), 2) AS avg_price,
               round(max(i.price), 2) AS max_price,
               arg_min(s.name, i.price) AS cheapest_store
        FROM inv i
        JOIN store s ON i.store_id = s.store_id
        JOIN product p ON i.product_id = p.product_id
        WHERE i.in_stock
        GROUP BY p.product_id, p.name, p.category
        """,
        inv=paths.SILVER_FACT_INVENTORY,
        store=paths.SILVER_DIM_STORE,
        product=paths.SILVER_DIM_PRODUCT,
    )
    io.write_delta(price_stats, paths.GOLD_PRICE_STATS)

    store_index = io.sql(
        """
        WITH offers AS (
            SELECT i.store_id, s.name AS store_name, s.chain, i.product_id, i.price
            FROM inv i JOIN store s ON i.store_id = s.store_id
            WHERE i.in_stock
        ),
        mins AS (SELECT product_id, min(price) AS mp FROM offers GROUP BY product_id)
        SELECT o.store_id, any_value(o.store_name) AS store_name, any_value(o.chain) AS chain,
               round(avg(o.price / m.mp), 3) AS price_index,
               count(*) AS products_in_stock
        FROM offers o JOIN mins m ON o.product_id = m.product_id
        GROUP BY o.store_id
        ORDER BY price_index
        """,
        inv=paths.SILVER_FACT_INVENTORY,
        store=paths.SILVER_DIM_STORE,
    )
    io.write_delta(store_index, paths.GOLD_STORE_INDEX)
