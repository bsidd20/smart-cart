-- Per-product search terms + availability (typeahead / matching).
select
    product_id,
    any_value(product_name) as product_name,
    any_value(category)     as category,
    any_value(search_terms) as search_terms,
    count(*) filter (where in_stock) as num_stores_in_stock,
    round(min(price), 2)    as min_price
from {{ ref('store_product_offers') }}
group by product_id
