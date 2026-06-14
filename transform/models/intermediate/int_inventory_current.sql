-- Current price per (store, product): the latest price event for each pair.
with ranked as (
    select
        *,
        row_number() over (
            partition by store_id, barcode
            order by observed_at desc
        ) as rn
    from {{ ref('stg_price_events') }}
)
select store_id, barcode, price, in_stock, observed_at
from ranked
where rn = 1
