-- Denormalized store x product x price. The table the application serves from.
select
    s.store_id,
    s.store_name,
    s.chain,
    s.lat,
    s.lon,
    p.product_id,
    p.product_name,
    p.category,
    p.search_terms,
    i.price,
    i.in_stock
from {{ ref('int_inventory_current') }} i
inner join {{ ref('int_stores') }} s on i.store_id = s.store_id
inner join {{ ref('product_catalog') }} p on i.barcode = p.product_id
