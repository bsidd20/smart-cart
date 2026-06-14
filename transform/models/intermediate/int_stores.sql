-- One row per store (latest ingested), valid coordinates only.
with ranked as (
    select
        *,
        row_number() over (partition by store_id order by ingested_at desc) as rn
    from {{ ref('stg_stores') }}
)
select store_id, store_name, chain, lat, lon
from ranked
where rn = 1 and lat is not null and lon is not null
