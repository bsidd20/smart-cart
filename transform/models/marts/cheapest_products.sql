-- Cheapest store per product (deals / price comparison).
with ranked as (
    select
        *,
        row_number() over (partition by product_id order by price) as rn
    from {{ ref('store_product_offers') }}
    where in_stock
)
select
    product_id,
    product_name,
    category,
    round(price, 2)  as cheapest_price,
    store_name       as cheapest_store
from ranked
where rn = 1
