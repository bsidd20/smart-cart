-- Clean product master for search, browse, and enrichment joins.
select
    barcode as product_id,
    product_name,
    brands,
    category,
    product_group,
    base_price,
    search_terms
from {{ ref('int_products_deduped') }}
