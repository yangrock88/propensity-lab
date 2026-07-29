-- One row per (snapshot_date, customer_id, product) with the ownership
-- flag and its previous-month value. This is the long-format backbone
-- for add detection and product aggregates.

with unpivoted as (

    select
        snapshot_date,
        customer_id,
        product,
        holds
    from {{ ref('stg_customer_snapshots') }}
        unpivot (holds for product in (
            {% for p in var('product_names') %}{{ p }}{% if not loop.last %},
            {% endif %}{% endfor %}
        ))

)

select
    snapshot_date,
    customer_id,
    product,
    holds,
    lag(holds) over (
        partition by customer_id, product
        order by snapshot_date
    ) as prev_holds
from unpivoted
