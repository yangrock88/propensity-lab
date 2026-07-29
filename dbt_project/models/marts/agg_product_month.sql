-- Product-month aggregate: holders, adds and drops per product per
-- snapshot. Feeds the adoption forecast and the trend charts.

with holdings as (

    select
        snapshot_date,
        product,
        sum(holds)                                        as holders,
        sum(case when holds = 1 and prev_holds = 0 then 1 else 0 end) as adds,
        sum(case when holds = 0 and prev_holds = 1 then 1 else 0 end) as drops
    from {{ ref('int_holdings_long') }}
    group by 1, 2

)

select
    snapshot_date,
    product,
    holders,
    adds,
    drops,
    holders - lag(holders) over (partition by product order by snapshot_date)
        as net_change
from holdings
