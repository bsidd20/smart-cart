-- One row per product (latest by last_modified_t), malformed rows dropped, mapped
-- to our taxonomy with a modeled base price and search terms.
with ranked as (
    select
        *,
        row_number() over (
            partition by barcode
            order by last_modified_t desc, ingested_at desc
        ) as rn
    from {{ ref('stg_products') }}
    where length(barcode) > 0 and length(product_name) > 0
),

latest as (select * from ranked where rn = 1)

select
    l.barcode,
    l.product_name,
    l.brands,
    l.taxonomy_key as category,
    cm.product_group,
    -- modeled base price: deterministic from barcode (no free price source exists)
    round(cm.base_price * (0.85 + (
        mod(coalesce(try_cast(right(regexp_replace(l.barcode, '[^0-9]', '', 'g'), 4) as integer), 0), 31)
    ) / 100.0), 2) as base_price,
    -- search terms: category term + name tokens, but skip the dairy term for plant milks
    case
        when l.taxonomy_key = 'milk' and (
            lower(l.product_name) like '%almond%' or lower(l.product_name) like '%oat%'
            or lower(l.product_name) like '%soy%' or lower(l.product_name) like '%coconut%')
        then lower(regexp_replace(trim(l.product_name), '\s+', '|', 'g'))
        else cm.term || '|' || lower(regexp_replace(trim(l.product_name), '\s+', '|', 'g'))
    end as search_terms,
    l.last_modified_t
from latest l
inner join {{ ref('category_map') }} cm on l.taxonomy_key = cm.taxonomy_key
