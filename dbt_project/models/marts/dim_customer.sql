-- Current view of each customer: latest demographic attributes plus
-- lifetime activity summary. One row per customer.

with latest as (

    select *
    from {{ ref('stg_customer_snapshots') }}
    qualify row_number() over (
        partition by customer_id
        order by snapshot_date desc
    ) = 1

),

adds as (

    select
        customer_id,
        count(*) as lifetime_product_adds
    from {{ ref('fct_product_adds') }}
    group by 1

)

select
    l.customer_id,
    l.snapshot_date as as_of_date,
    l.gender,
    l.age,
    l.customer_since,
    l.tenure_months,
    l.join_channel,
    l.province,
    l.is_active,
    l.gross_income,
    l.segment,
    l.held_product_count,
    coalesce(a.lifetime_product_adds, 0) as lifetime_product_adds
from latest l
left join adds a using (customer_id)
