# Design Notes

Prepared by: Rocky Yang
Last reviewed: 2026-07-28

The build followed a design-thinking loop: understand the people who
would use it, define the problem sharply, consider several shapes the
answer could take, prototype the risky parts first, and test against
real behavior rather than opinion. This file records how each stage
changed the product, because decisions without recorded reasons get
re-litigated forever.

## 1. Empathize: who is this for?

Three users, three different needs from the same data.

- A relationship manager wants a short list per customer and a reason
  they can say out loud. They do not care about MAP@7. If the reason
  column had not existed, the recommendations would have been ignored.
- A finance planner wants a number per product per future month, plus a
  sense of how much to trust it. They asked, in effect, for the error
  bars more than the line.
- A data lead wants to know whether the thing is on and whether the
  numbers can be trusted: when did it last run, did the tests pass, is
  the champion actually better than doing nothing?

Each user got a dedicated region of the dashboard: the customer lookup,
the forecast card, and the leaderboard plus pipeline health strip.

## 2. Define: the problem statement

"Rank the products each customer is likely to add next month, and
project per-product adoption, from monthly snapshots, refreshed daily,
with every number traceable to a certified table and an honest
backtest."

Two sharp edges in that sentence drove the architecture. "Traceable"
ruled out ad-hoc pandas jobs and put dbt models with tests between the
raw file and everything else. "Honest backtest" ruled out random
train/test splits, because a random split on panel data lets the model
peek at the future; the evaluation had to be walk-forward.

## 3. Ideate: shapes that were considered and dropped

- One big multiclass model predicting "the next product". Dropped:
  customers add zero, one or several products in a month, so the problem
  is 24 binary decisions, not one classification.
- A deep sequence model over customer histories. Dropped: seventeen
  monthly steps is too shallow a sequence to reward the complexity, and
  the result would be unexplainable to the people in stage 1.
- Live scoring inside the dashboard. Dropped: training at request time
  couples user experience to model runtime and makes failures visible as
  blank pages. Publishing artifacts once a day makes the app trivially
  fast and failures invisible to end users.
- A cloud warehouse. Dropped: DuckDB gives real SQL, real dbt support
  and zero setup on a laptop. The dbt models would move to a hosted
  warehouse without rewriting.

## 4. Prototype: risky parts first

The first working code was not the dashboard. It was the transitions
frame (the leakage-safe training table) and the walk-forward harness,
because if models could not beat the popularity baseline there was no
product worth designing screens for. The synthetic demo generator was
built with real cross-sell structure in it (payroll pulls pension,
checking is a gateway) precisely so the backtest could fail honestly if
the modeling was wrong.

The dashboard came last and reads only published artifacts, which meant
it could be developed and restyled freely without touching anything that
computes numbers.

## 5. Test: what changed as a result

- Early versions showed raw model scores next to recommendations.
  Scores mean nothing across customers, so they were replaced with a
  within-customer bar and a reason string.
- The leaderboard originally listed models alphabetically. Sorting by
  MAP@7 with the baseline visually anchored made the "is this better
  than doing nothing" question answerable at a glance.
- The forecast card gained per-product backcast error after it became
  clear that a single global accuracy number hid how much the products
  differ.
- The failed-run behavior (keep yesterday's artifacts, show the refresh
  timestamp) came from asking what a user should see on the morning the
  pipeline breaks.

## Visual language

White cards on a soft gray canvas, one accent color, Inter type,
generous spacing, no gridline clutter, no legends where a direct label
works. The reference points were the current generation of clean
product dashboards (Stripe and Linear being the obvious ones). Charts
follow the same restraint: history is a solid line, forecast is dashed,
uncertainty is a soft fill, and nothing animates without a reason.
