-- Light typing/renaming over raw product records. No dedup or filtering yet.
select
    cast(barcode as varchar)        as barcode,
    trim(product_name)              as product_name,
    brands,
    categories_tags,
    quantity,
    lang,
    cast(last_modified_t as bigint) as last_modified_t,
    taxonomy_key,
    ingested_at
from {{ source('bronze', 'raw_products') }}
