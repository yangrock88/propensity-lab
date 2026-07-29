# Executive Summary

Prepared by: Rocky Yang
Last reviewed: 2026-07-28

## What this system does

For a retail bank with 24 products and a monthly customer snapshot, it
answers two questions from a fixed panel of historical customer data:

1. For each customer, which products are they most likely to add next
   month? Seven ranked suggestions per customer, each with a reason a
   relationship manager could read aloud.
2. For each product, how many customers will add it over the next six
   months? A planning number with an honest uncertainty band.

The first question drives cross-sell targeting. The second drives
capacity and revenue planning. Both come from the same certified data,
so the person planning and the person targeting are never working from
different numbers.

## How to read the headline metric

The system's quality is measured by MAP@7: if we show seven suggestions,
how high up the list do the products the customer actually added appear?
It is scored by walk-forward backtesting, meaning the models are trained
only on months before a cutoff and judged on what really happened in the
cutoff month. Nothing about the future leaks into the past. This is the
same discipline the system faces in production: score today, get judged
next month.

At the review date the champion scores 0.536 against a popularity
baseline of 0.511, a 5% lift. Every leaderboard number on the dashboard
is from the backtest, never from training data.

## Why five models instead of one

The suite is a deliberate ladder, and each rung answers a question a
stakeholder should ask before trusting the system.

Step 1: popularity baseline. Before any modeling, what does "just
recommend the most-added products" achieve? This is the floor. Any
consultant deck that skips this number is hiding something. Here the
floor is high (0.511), which tells us most adds concentrate in a few
everyday products. That fact alone shapes expectations for everything
fancier.

Step 2: item-item collaborative filtering. The classic "customers who
hold X also add Y". It roughly matches the baseline on accuracy, but it
pays its way differently: its similarity matrix generates the
plain-language explanation attached to every recommendation. Accuracy is
not the only currency; a recommendation nobody can explain is a
recommendation nobody acts on.

Step 3: matrix factorization (ALS). The standard next step in
recommender systems, included to test whether hidden bundle structure
exists beyond pairwise patterns. It loses to the baseline here, and we
show that on the dashboard rather than burying it. With 24 products
there is not enough latent structure to find. Keeping a negative result
visible is what makes the rest of the leaderboard believable.

Step 4: gradient boosting (LightGBM), the champion. It treats each
product as its own prediction problem and folds in what the
collaborative models cannot see: age, income, tenure, activity, how
recently the customer added anything. This family won the public
competition on this dataset, and it wins our internal leaderboard too.
The 5% lift over the baseline is the honest size of the prize; at the
scale of a real book, five percent better targeting on millions of
monthly decisions is material.

Step 5: a blend of the two strongest models. Cheap to test, and today it
does not beat the champion, because the boosted model already consumes
the holdings signal the collaborative filter runs on. The leaderboard
re-runs with each pipeline execution, so any code or data change is
immediately re-evaluated. Champion selection is automatic, not a matter of opinion.

## The forecasting choice

Product adoption counts are short monthly series, under two years long.
The right tool at that length is deliberately simple: damped-trend
exponential smoothing, validated by backcasting the last three months
before projecting six ahead. The dashboard draws the uncertainty band,
and the per-product backcast error ships with the forecast so a planner
can see how much to trust each curve. Heavier methods were considered
and rejected: with 16 monthly points, seasonal terms and covariate
models have nothing solid to learn from, and a wrong-but-confident
forecast is worse than a modest one with a visible band.

## Operating model

The pipeline replays monthly snapshots sequentially from the historical
dataset, mirroring how a production warehouse receives new monthly data.
Each run loads the next snapshot, rebuilds the warehouse models, runs
twenty automated checks, retrains all five models, re-runs the backtest,
and republishes recommendations and forecasts. If a run fails, the
previous outputs stay live and the failure is logged; the dashboard
degrades to stale, never to wrong.

Total infrastructure cost: zero. Everything runs locally on DuckDB, dbt,
Python and open-source libraries.
