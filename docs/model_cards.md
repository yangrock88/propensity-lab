# Model Cards

Maintainer: Rocky Yang
Last reviewed: 2026-07-28

Five recommendation models are trained on the full historical panel and
compared in a walk-forward backtest. The best one by MAP@7 becomes the
champion and produces the published recommendations. A sixth model, the adoption
forecaster, is a separate time-series system. Latest backtest numbers are
in data/artifacts/leaderboard.json; the numbers quoted here are from the
review date and will drift as more months load.

A shared rule for all rankers: products a customer already holds are
removed from their candidate list before ranking. Scores are only ever
compared within a single customer, not across customers.

---

## popularity_baseline

Purpose: the honesty floor. Every other model earns its place by beating
this one, and the dashboard shows the gap.

Method: rank products by global add rate among customers who do not
already hold them. Everyone gets the same ranking, filtered by their
holdings.

Training data: all loaded transition months.

Latest backtest: MAP@7 0.511 (by definition, lift 1.0).

Limitations: ignores everything about the individual. Its strength in
this dataset comes from the add distribution being head-heavy; a handful
of products (checking, direct debit, e-account) dominate adds, so global
popularity is genuinely hard to beat. That is worth knowing on its own.

Training cost: negligible — runs in milliseconds on the full panel.

## item_item_cf

Purpose: "customers who hold X tend to add Y". Also the source of the
plain-language reasons shown next to every recommendation, because its
similarity matrix is directly readable.

Method: cosine similarity between product columns of the binary
customer-by-product holdings matrix at the latest training month. A
customer's score for a product is the similarity-weighted count of
products they already hold.

Latest backtest: MAP@7 0.512, roughly even with the baseline.

Limitations: blind to demographics, tenure and recency. With only 24
products the similarity matrix is small and stable, but it can only
express pairwise structure. It earns its keep through interpretability:
when the champion recommends a pension deposit, this model can say it is
because the customer holds a payroll deposit.

Training cost: fast — similarity matrix computed once from the latest snapshot.

## als_factorization

Purpose: latent-factor collaborative filtering, included to test whether
bundle structure beyond pairwise similarity exists in the data.

Method: implicit-feedback alternating least squares (Hu, Koren and
Volinsky 2008) with confidence weighting c = 1 + alpha r, eight factors,
pure numpy. New customers are folded in by solving for a user vector from
their current holdings at scoring time.

Latest backtest: MAP@7 0.232. Clearly below the baseline.

Why keep a losing model: because the leaderboard is the point. With 24
products and mostly head-driven adds, there simply is not enough latent
structure for factorization to find, and showing that honestly is more
valuable than hiding it. If the catalog were hundreds of items this
family would be worth revisiting.

Training cost: moderate — alternating least-squares converges in 12 iterations.

## lightgbm (champion at review date)

Purpose: the supervised approach. Frames "will this customer add product
P next month" as 24 independent binary classification problems.

Method: one LightGBM classifier per product, trained on customers who did
not hold that product, predicting whether they add it in the next month.
Features: the 24 holdings flags, held-product count, adds in the last
three months, months since last add, age, tenure, log income, activity
flag, gender and segment indicators. Products with fewer than 30 training
positives fall back to the popularity rate so scores stay defined.

Leakage control: features for a row that predicts month t+1 are computed
strictly from months up to t. The transitions frame is built once in
ml/features.py and shared by training, backtesting and production
scoring, so there is no way for the three to disagree.

Latest backtest: MAP@7 0.536, precision@7 0.144, lift 1.05 over the
baseline.

Limitations: 24 separate classifiers do not share information across
products; rare products lean on the fallback. The +5% lift is real but
modest, which is typical for this dataset; the original Kaggle
competition was won by exactly this model family with margins of a
similar flavor.

Training cost: under a minute for all 24 classifiers at this dataset size.

## blend_lgbm_cf

Purpose: test whether the two strongest members combine into something
better than either.

Method: rank-average. Each model's scores are converted to within-
customer ranks and averaged. Rank space makes the two score scales
comparable without fitting a meta-model, which this data volume would
not justify.

Latest backtest: MAP@7 0.535, a hair under LightGBM alone.

Interpretation: the CF signal is mostly a subset of what LightGBM already
sees (the holdings flags are LightGBM features too), so blending adds
noise rather than information. The blend stays in the suite because the
answer could flip as more months load, and the leaderboard re-asks the
question every day.

## Adoption forecaster (separate system)

Purpose: for each product, project monthly add counts six months out.
This is the planning view: recommendations say who, the forecast says
how many.

Method: damped-trend exponential smoothing (Holt's method with damping)
per product, on the monthly add series from agg_product_month. With
under two years of monthly history, seasonal terms have no support and
heavier models (ARIMA with covariates, gradient-boosted forecasters)
have nothing to learn from; damping keeps short-history trends from
running away. Products with fewer than six observations fall back to a
trailing mean.

Validation: before the final fit, the last three months are held out and
backcast; per-product MAPE from that check ships inside
forecasts.parquet and the 80% band is built from the backcast residual
spread, widening with the square root of the horizon.

Limitations: the band assumes residuals stay roughly as they were, and a
regime change (a marketing push, a pricing change) would break any
extrapolation. Forecasts are floored at zero.
