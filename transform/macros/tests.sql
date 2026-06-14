{% test positive(model, column_name) %}
-- fails for any non-positive or null value
select {{ column_name }}
from {{ model }}
where {{ column_name }} is null or {{ column_name }} <= 0
{% endtest %}


{% test valid_gtin(model, column_name) %}
-- fails for barcodes that aren't 8/12/13/14 digits (a cheap structural UPC check;
-- the full check-digit validation lives in the Python quality layer)
select {{ column_name }}
from {{ model }}
where length(regexp_replace({{ column_name }}, '[^0-9]', '', 'g')) not in (8, 12, 13, 14)
{% endtest %}
