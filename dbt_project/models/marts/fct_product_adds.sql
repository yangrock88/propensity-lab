-- Product add events: a customer's flag flipped 0 -> 1 between two
-- consecutive snapshots. This is the ground truth the recommender is
-- trained and evaluated on, and the quantity the adoption forecast
-- projects forward.

select
    snapshot_date as add_month,
    customer_id,
    product
from {{ ref('int_holdings_long') }}
where holds = 1
  and prev_holds = 0
