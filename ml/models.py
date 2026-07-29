"""The recommendation model suite.

Every model implements the same two methods:

    fit(train)   train is a transitions frame from ml.features
    score(rows)  returns an (n_rows x 24) matrix of raw scores

Score masking for already-held products happens in the caller, so each
model stays focused on ranking quality. The suite deliberately spans
three families: a popularity baseline (the honesty floor), two
collaborative filters (item-item and ALS factorization), and a
supervised gradient-boosting approach that also uses demographics and
recency. The blend rank-averages the two strongest members.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from scipy.stats import rankdata

from ml import features
from ml.features import PRODUCTS


class Popularity:
    """Rank products by their global add rate among non-holders."""

    name = "popularity_baseline"

    def fit(self, train: pd.DataFrame) -> "Popularity":
        y = features.targets_matrix(train).astype(np.float64)
        held = features.holdings_matrix(train)
        eligible = (held == 0).sum(axis=0).clip(min=1)
        self.rates_ = y.sum(axis=0) / eligible
        return self

    def score(self, rows: pd.DataFrame) -> np.ndarray:
        return np.tile(self.rates_, (len(rows), 1))


class ItemItemCF:
    """Cosine similarity between products over the holdings matrix.

    A customer's score for product j is the similarity-weighted count of
    products they already hold. Interpretable and cheap: the similarity
    matrix doubles as the 'because you hold X' explanation source.
    """

    name = "item_item_cf"

    def fit(self, train: pd.DataFrame) -> "ItemItemCF":
        last_month = train["target_month"].max()
        H = features.holdings_matrix(train[train["target_month"] == last_month])
        norms = np.linalg.norm(H, axis=0).clip(min=1e-9)
        sim = (H.T @ H) / np.outer(norms, norms)
        np.fill_diagonal(sim, 0.0)
        self.sim_ = sim
        return self

    def score(self, rows: pd.DataFrame) -> np.ndarray:
        return features.holdings_matrix(rows) @ self.sim_

    def top_driver(self, held_row: np.ndarray, product_ix: int) -> int | None:
        """Index of the held product that contributes most to a score."""
        contrib = held_row * self.sim_[:, product_ix]
        if contrib.max() <= 0:
            return None
        return int(contrib.argmax())


class ALS:
    """Implicit-feedback alternating least squares (Hu, Koren, Volinsky).

    Confidence weighting c = 1 + alpha * r on the binary holdings
    matrix. Learns latent factors that capture bundle structure the
    item-item model can only see pairwise. Pure numpy: at this scale
    (tens of thousands of customers, 24 products) compiled libraries
    would be overkill.
    """

    name = "als_factorization"

    def __init__(self, factors: int = 8, reg: float = 0.5,
                 alpha: float = 10.0, iters: int = 12, seed: int = 7):
        self.k, self.reg, self.alpha, self.iters, self.seed = (
            factors, reg, alpha, iters, seed,
        )

    def fit(self, train: pd.DataFrame) -> "ALS":
        last_month = train["target_month"].max()
        snap = train[train["target_month"] == last_month]
        R = features.holdings_matrix(snap)  # users x items, binary
        n_u, n_i = R.shape
        rng = np.random.default_rng(self.seed)
        U = rng.normal(0, 0.01, (n_u, self.k))
        V = rng.normal(0, 0.01, (n_i, self.k))
        eye = np.eye(self.k)

        for _ in range(self.iters):
            U = self._solve(R, V, eye)
            V = self._solve(R.T, U, eye)

        self.V_ = V
        self.eye_ = eye
        return self

    def _solve(self, R: np.ndarray, F: np.ndarray, eye: np.ndarray) -> np.ndarray:
        """One half-step: solve for the side whose rows are in R."""
        FtF = F.T @ F
        out = np.zeros((R.shape[0], self.k))
        for u in range(R.shape[0]):
            r = R[u]
            idx = np.nonzero(r)[0]
            if len(idx) == 0:
                continue
            Fi = F[idx]
            # (FtF + alpha * Fi^T Fi + reg I) x = (1 + alpha) Fi^T 1
            A = FtF + self.alpha * (Fi.T @ Fi) + self.reg * eye
            b = (1.0 + self.alpha) * Fi.sum(axis=0)
            out[u] = np.linalg.solve(A, b)
        return out

    def score(self, rows: pd.DataFrame) -> np.ndarray:
        """Fold-in: derive a user vector from the row's holdings."""
        H = features.holdings_matrix(rows)
        FtF = self.V_.T @ self.V_
        scores = np.zeros((len(rows), len(PRODUCTS)))
        cache: dict[bytes, np.ndarray] = {}
        for i in range(len(rows)):
            key = H[i].tobytes()
            if key not in cache:
                idx = np.nonzero(H[i])[0]
                if len(idx) == 0:
                    cache[key] = np.zeros(len(PRODUCTS))
                else:
                    Fi = self.V_[idx]
                    A = FtF + self.alpha * (Fi.T @ Fi) + self.reg * self.eye_
                    b = (1.0 + self.alpha) * Fi.sum(axis=0)
                    u = np.linalg.solve(A, b)
                    cache[key] = u @ self.V_.T
            scores[i] = cache[key]
        return scores


class GradientBoosting:
    """One LightGBM binary classifier per product on lagged features.

    The same family that won the original Kaggle competition. Sees
    everything the collaborative filters cannot: demographics, tenure,
    activity, add-recency. Products with too few training positives
    fall back to the popularity rate so scores stay well-defined.
    """

    name = "lightgbm"
    MIN_POSITIVES = 30

    def fit(self, train: pd.DataFrame) -> "GradientBoosting":
        X, self.feat_names_ = features.feature_matrix(train)
        Y = features.targets_matrix(train)
        held = features.holdings_matrix(train)
        self.models_: dict[int, LGBMClassifier] = {}
        self.fallback_ = Popularity().fit(train).rates_

        for j, p in enumerate(PRODUCTS):
            candidates = held[:, j] == 0
            y = Y[candidates, j]
            if y.sum() < self.MIN_POSITIVES:
                continue
            clf = LGBMClassifier(
                n_estimators=150, learning_rate=0.05, num_leaves=31,
                min_child_samples=50, subsample=0.9, subsample_freq=1,
                colsample_bytree=0.8, random_state=7, verbose=-1,
            )
            clf.fit(X[candidates], y)
            self.models_[j] = clf
        return self

    def score(self, rows: pd.DataFrame) -> np.ndarray:
        X, _ = features.feature_matrix(rows)
        scores = np.tile(self.fallback_, (len(rows), 1))
        for j, clf in self.models_.items():
            scores[:, j] = clf.predict_proba(X)[:, 1]
        return scores


class Blend:
    """Rank-average of LightGBM and item-item CF.

    The two strongest members err differently: boosting leans on who
    the customer is (demographics, recency), the item-item filter leans
    on what they hold. Averaging their ranks is a low-variance way to
    combine them without a meta-model this data volume could not
    justify.
    """

    name = "blend_lgbm_cf"

    def __init__(self, lgbm: GradientBoosting, cf: ItemItemCF):
        self.lgbm, self.cf = lgbm, cf

    def fit(self, train: pd.DataFrame) -> "Blend":
        return self  # members are fitted independently

    def score(self, rows: pd.DataFrame) -> np.ndarray:
        a = rankdata(self.lgbm.score(rows), axis=1)
        b = rankdata(self.cf.score(rows), axis=1)
        return (a + b) / 2.0


def build_suite(train: pd.DataFrame) -> list:
    """Fit every model on the given training transitions."""
    pop = Popularity().fit(train)
    cf = ItemItemCF().fit(train)
    als = ALS().fit(train)
    lgbm = GradientBoosting().fit(train)
    blend = Blend(lgbm, cf).fit(train)
    return [pop, cf, als, lgbm, blend]
