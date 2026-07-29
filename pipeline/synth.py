"""Demo-mode data generator.

Produces a customer-month panel in the exact schema of the public
Santander product dataset, so every downstream layer (dbt models, ML,
dashboard) is identical whether you run on real Kaggle data or this
generator. The panel is not random noise: customers belong to latent
segments, products have cross-sell relationships, and adoption depends
on tenure, income and activity. Models can only beat the popularity
baseline in backtests because this structure exists to be learned.

Kaggle's competition terms do not allow redistributing the real file,
which is why the repository ships with this generator instead.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import config

SEGMENTS = ["01 - TOP", "02 - PARTICULARES", "03 - UNIVERSITARIO"]
SEGMENT_P = [0.15, 0.60, 0.25]
CHANNELS = ["KHE", "KAT", "KFC", "KHQ", "KFA", "RED"]
PROVINCES = [
    "MADRID", "BARCELONA", "VALENCIA", "SEVILLA", "ZARAGOZA",
    "MALAGA", "MURCIA", "BILBAO", "ALICANTE", "CORDOBA",
]

# Monthly probability that a non-holder adds the product (baseline,
# before segment / activity / cross-sell adjustments).
BASE_HAZARD = {
    "ind_cco_fin_ult1": 0.030, "ind_recibo_ult1": 0.020,
    "ind_ecue_fin_ult1": 0.012, "ind_cno_fin_ult1": 0.010,
    "ind_nomina_ult1": 0.008, "ind_nom_pens_ult1": 0.008,
    "ind_tjcr_fin_ult1": 0.007, "ind_reca_fin_ult1": 0.005,
    "ind_ctop_fin_ult1": 0.004, "ind_dela_fin_ult1": 0.003,
    "ind_fond_fin_ult1": 0.002, "ind_valo_fin_ult1": 0.002,
    "ind_plan_fin_ult1": 0.002, "ind_ctma_fin_ult1": 0.0015,
    "ind_ctpp_fin_ult1": 0.0015, "ind_pres_fin_ult1": 0.001,
    "ind_hip_fin_ult1": 0.0008, "ind_deme_fin_ult1": 0.0008,
    "ind_deco_fin_ult1": 0.0008, "ind_ctju_fin_ult1": 0.0005,
    "ind_viv_fin_ult1": 0.0005, "ind_ahor_fin_ult1": 0.0003,
    "ind_aval_fin_ult1": 0.0001, "ind_cder_fin_ult1": 0.0001,
}

# Monthly probability that a holder drops the product.
CHURN = {
    "ind_deco_fin_ult1": 0.02, "ind_deme_fin_ult1": 0.02,
    "ind_dela_fin_ult1": 0.015, "ind_tjcr_fin_ult1": 0.010,
    "ind_nomina_ult1": 0.010, "ind_nom_pens_ult1": 0.008,
    "ind_recibo_ult1": 0.010, "ind_cco_fin_ult1": 0.003,
}
DEFAULT_CHURN = 0.005

INVESTMENT = {
    "ind_fond_fin_ult1", "ind_valo_fin_ult1", "ind_plan_fin_ult1",
    "ind_dela_fin_ult1", "ind_deme_fin_ult1", "ind_deco_fin_ult1",
}

# Share of customers holding each product at their first snapshot.
STARTER_P = {
    "ind_cco_fin_ult1": 0.62, "ind_recibo_ult1": 0.28,
    "ind_ecue_fin_ult1": 0.10, "ind_cno_fin_ult1": 0.12,
    "ind_nomina_ult1": 0.07, "ind_nom_pens_ult1": 0.06,
    "ind_tjcr_fin_ult1": 0.05, "ind_ctop_fin_ult1": 0.04,
}


def _customers(rng: np.random.Generator, n: int) -> pd.DataFrame:
    seg = rng.choice(len(SEGMENTS), size=n, p=SEGMENT_P)
    age = np.select(
        [seg == 0, seg == 1, seg == 2],
        [rng.normal(48, 10, n), rng.normal(42, 13, n), rng.normal(22, 3, n)],
    ).clip(18, 90).astype(int)
    renta = np.select(
        [seg == 0, seg == 1, seg == 2],
        [
            rng.lognormal(11.6, 0.45, n),
            rng.lognormal(10.9, 0.50, n),
            rng.lognormal(10.1, 0.40, n),
        ],
    ).round(2)
    # 85% of the book exists before the panel starts; the rest join
    # during it, which gives the pipeline genuine new-customer arrivals.
    join_month = np.where(
        rng.random(n) < 0.85, 0, rng.integers(1, len(config.SNAPSHOT_MONTHS), n)
    )
    tenure0 = np.where(join_month == 0, rng.integers(3, 240, n), 0)
    return pd.DataFrame(
        {
            "ncodpers": np.arange(100_000, 100_000 + n),
            "segment_ix": seg,
            "sexo": rng.choice(["H", "V"], n),
            "age": age,
            "renta": renta,
            "canal_entrada": rng.choice(CHANNELS, n, p=[0.35, 0.25, 0.15, 0.10, 0.10, 0.05]),
            "nomprov": rng.choice(PROVINCES, n),
            "active": (rng.random(n) < np.select([seg == 0, seg == 1, seg == 2], [0.75, 0.5, 0.45])).astype(int),
            "join_month": join_month,
            "tenure0": tenure0,
        }
    )


def _hazard(prod: str, cust: pd.DataFrame, hold: dict[str, np.ndarray],
            season: float) -> np.ndarray:
    """Per-customer monthly add probability for one product."""
    h = np.full(len(cust), BASE_HAZARD[prod])
    seg = cust["segment_ix"].to_numpy()
    renta_hi = cust["renta"].to_numpy() > np.quantile(cust["renta"], 0.75)
    age = cust["age"].to_numpy()

    if prod in INVESTMENT:
        h *= np.where(seg == 0, 4.0, np.where(seg == 2, 0.2, 1.0))
        h *= np.where(renta_hi, 3.0, 1.0)
    if prod == "ind_ecue_fin_ult1":
        h *= np.where(seg == 2, 3.0, 1.0)
    if prod == "ind_ctju_fin_ult1":
        h *= np.where(age < 21, 8.0, 0.05)
    if prod == "ind_nomina_ult1":
        h *= np.where(hold["ind_cno_fin_ult1"] == 1, 6.0, 1.0)
    if prod == "ind_nom_pens_ult1":
        h *= np.where(hold["ind_nomina_ult1"] == 1, 8.0, 1.0)
    if prod == "ind_recibo_ult1":
        h *= np.where(
            (hold["ind_nomina_ult1"] == 1) | (hold["ind_cco_fin_ult1"] == 1), 3.0, 1.0
        )
    if prod == "ind_tjcr_fin_ult1":
        h *= np.where(hold["ind_cno_fin_ult1"] == 1, 4.0, 1.0)
        h *= np.where(renta_hi, 1.5, 1.0)
    if prod == "ind_cno_fin_ult1":
        h *= np.where(hold["ind_cco_fin_ult1"] == 1, 3.0, 1.0)
    if prod == "ind_reca_fin_ult1":
        h *= np.where(hold["ind_cco_fin_ult1"] == 1, 2.0, 1.0)
    if prod == "ind_hip_fin_ult1":
        h *= np.where((age >= 28) & (age <= 45) & renta_hi, 3.0, 1.0)

    h *= np.where(cust["active"].to_numpy() == 1, 2.5, 0.5)
    h *= season
    return h.clip(0, 0.6)


def generate_panel() -> pd.DataFrame:
    """Build the full 17-month customer panel and cache it to parquet."""
    if config.SYNTH_CACHE.exists():
        return pd.read_parquet(config.SYNTH_CACHE)

    rng = np.random.default_rng(config.SYNTH_SEED)
    cust = _customers(rng, config.SYNTH_CUSTOMERS)
    n = len(cust)
    hold = {p: np.zeros(n, dtype=np.int8) for p in config.PRODUCT_COLS}
    started = np.zeros(n, dtype=bool)
    rows: list[pd.DataFrame] = []

    for m_ix, snapshot in enumerate(config.SNAPSHOT_MONTHS):
        present = cust["join_month"].to_numpy() <= m_ix
        newly = present & ~started
        for p in config.PRODUCT_COLS:
            starter = STARTER_P.get(p, 0.0)
            if starter and newly.any():
                hold[p][newly] = (rng.random(newly.sum()) < starter).astype(np.int8)
        started |= newly

        season = 1.0 + 0.2 * np.sin(2 * np.pi * m_ix / 12.0)
        for p in config.PRODUCT_COLS:
            h = _hazard(p, cust, hold, season)
            adds = present & (hold[p] == 0) & (rng.random(n) < h)
            drops = present & (hold[p] == 1) & (rng.random(n) < CHURN.get(p, DEFAULT_CHURN))
            hold[p][adds] = 1
            hold[p][drops] = 0

        # a small share of customers flip activity status each month
        flip = rng.random(n) < 0.02
        cust.loc[flip, "active"] = 1 - cust.loc[flip, "active"]

        tenure = cust["tenure0"].to_numpy() + (m_ix - cust["join_month"].to_numpy())
        snap = pd.DataFrame(
            {
                "fecha_dato": snapshot,
                "ncodpers": cust["ncodpers"],
                "sexo": cust["sexo"],
                "age": cust["age"],
                "fecha_alta": pd.to_datetime(snapshot)
                - pd.to_timedelta(tenure * 30, unit="D"),
                "antiguedad": tenure,
                "canal_entrada": cust["canal_entrada"],
                "nomprov": cust["nomprov"],
                "ind_actividad_cliente": cust["active"],
                "renta": cust["renta"],
                "segmento": [SEGMENTS[i] for i in cust["segment_ix"]],
            }
        )
        for p in config.PRODUCT_COLS:
            snap[p] = hold[p]
        rows.append(snap[present.tolist()])

    panel = pd.concat(rows, ignore_index=True)
    panel["fecha_alta"] = panel["fecha_alta"].dt.strftime("%Y-%m-%d")
    config.ensure_dirs()
    panel.to_parquet(config.SYNTH_CACHE, index=False)
    return panel
