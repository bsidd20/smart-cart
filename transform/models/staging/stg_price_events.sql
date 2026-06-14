select
    event_id,
    store_id,
    barcode,
    cast(price as double) as price,
    in_stock,
    observed_at
from {{ source('bronze', 'raw_price_events') }}
