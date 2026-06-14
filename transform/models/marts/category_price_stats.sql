-- Per-category price spread and cheapest store (merchandising / price checks).
select
    category,
    count(distinct product_id) as num_products,
    count(*)                   as num_offers,
    round(min(price), 2)       as min_price,
    round(avg(price), 2)       as avg_price,
    round(max(price), 2)       as max_price,
    arg_min(store_name, price) as cheapest_store
from {{ ref('store_product_offers') }}
where in_stock
group by category
