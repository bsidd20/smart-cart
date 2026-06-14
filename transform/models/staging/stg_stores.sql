select
    store_id,
    trim(name)        as store_name,
    trim(chain)       as chain,
    cast(lat as double) as lat,
    cast(lon as double) as lon,
    ingested_at
from {{ source('bronze', 'raw_stores') }}
