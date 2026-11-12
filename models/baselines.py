"""Baselines B0–B3 (SPEC "Model suite"). Every model is fit on training rows only and returns P(event).

B0  Persistence: state of the site's latest report ≤ 3 days old, available by the issue time
    (event / no event / none) → conditional event rate per (lead, state) from train, shrunk toward the
    lead's base rate (``B0_PRIOR`` pseudo-counts).
B1  Climatology: site × day-of-year event rate from train site-days, Gaussian-smoothed over day of year
    (σ = ``B1_SIGMA_DAYS``) and shrunk toward the all-site curve (``B1_SHRINK`` pseudo-counts).
B2  SIR-style index (after Trinanes et al. 2023): AFAI detection-fraction anomaly within 50 km of the
    site, 7-day mean ending I−1 minus the 30-day baseline ending I−8 (``afai1d_r50_anom``) → logistic
    regression per lead (missing index → 0 plus a missing flag).
B3  B2 + onshore wind on the target day → logistic per lead. Winds exist from 2022, so B3 trains on the
    2022+ part of the training seasons. ``B3`` uses perfect-prog winds (upper bound); ``B3_fc`` applies
    the same fitted model to lead-L forecast winds (2024+ only, leakage-safe).

Hyper-parameters (``B0_PRIOR``, ``B1_SIGMA_DAYS``, ``B1_SHRINK``) are fixed a priori, not tuned.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from pipeline.sites import SITE_IDS

B0_PRIOR = 2.0
B1_SIGMA_DAYS = 10.0
B1_SHRINK = 20.0
SEED = 20261110


def _state(last_event: pd.Series) -> pd.Series:
    return last_event.map({1.0: "event", 0.0: "no_event"}).fillna("none")


@dataclass
class B0:
    table: dict[tuple[int, str], float] = field(default_factory=dict)
    base: dict[int, float] = field(default_factory=dict)

    def fit(self, tr: pd.DataFrame) -> B0:
        st = _state(tr["last_event"])
        for L, g in tr.groupby("lead"):
            p0 = float(g["event"].mean())
            self.base[int(L)] = p0
            for s in ("event", "no_event", "none"):
                y = g.loc[st.loc[g.index] == s, "event"]
                self.table[(int(L), s)] = (float(y.sum()) + B0_PRIOR * p0) / (len(y) + B0_PRIOR)
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        st = _state(df["last_event"])
        return np.array([self.table[(int(L), s)] for L, s in zip(df["lead"], st, strict=True)])


def _kernel_rate(doy: np.ndarray, y: np.ndarray, grid: np.ndarray, sigma: float) -> tuple[np.ndarray, np.ndarray]:
    d = grid[:, None] - doy[None, :]
    w = np.exp(-0.5 * (d / sigma) ** 2)
    return (w * y[None, :]).sum(1), w.sum(1)


@dataclass
class B1:
    curve: dict[str, np.ndarray] = field(default_factory=dict)
    grid: np.ndarray = field(default_factory=lambda: np.arange(1, 367))

    def fit(self, site_days: pd.DataFrame) -> B1:
        """``site_days``: one row per labeled train site-day with columns site, doy, event."""
        doy = site_days["doy"].to_numpy(float)
        y = site_days["event"].to_numpy(float)
        num, den = _kernel_rate(doy, y, self.grid, B1_SIGMA_DAYS)
        pooled = num / np.maximum(den, 1e-9)
        for s in SITE_IDS:
            m = (site_days["site"] == s).to_numpy()
            ns, ds = _kernel_rate(doy[m], y[m], self.grid, B1_SIGMA_DAYS)
            self.curve[s] = (ns + B1_SHRINK * pooled) / (ds + B1_SHRINK)
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        idx = df["doy"].to_numpy(int) - 1
        return np.array([self.curve[s][i] for s, i in zip(df["site"], idx, strict=True)])


def _x_b2(df: pd.DataFrame) -> np.ndarray:
    idx = df["afai1d_r50_anom"]
    return np.column_stack([idx.fillna(0).to_numpy(), idx.isna().to_numpy(float)])


@dataclass
class PerLeadLogit:
    xfun: object
    models: dict[int, LogisticRegression | float] = field(default_factory=dict)

    def fit(self, tr: pd.DataFrame) -> PerLeadLogit:
        for L, g in tr.groupby("lead"):
            y = g["event"].to_numpy()
            if len(np.unique(y)) < 2:  # one class only (tiny fold): constant event rate
                self.models[int(L)] = float(y.mean())
                continue
            m = LogisticRegression(C=1e4, max_iter=1000, random_state=SEED)
            m.fit(self.xfun(g), y)  # type: ignore[operator]
            self.models[int(L)] = m
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        out = np.full(len(df), np.nan)
        for L, g in df.groupby("lead"):
            pos = df.index.get_indexer(g.index)
            x = self.xfun(g)  # type: ignore[operator]
            ok = np.isfinite(x).all(axis=1)  # rows with a missing input (e.g. no wind before 2022) → NaN
            if ok.any():
                m = self.models[int(L)]
                out[pos[ok]] = m if isinstance(m, float) else m.predict_proba(x[ok])[:, 1]
        return out


def _x_b3(df: pd.DataFrame) -> np.ndarray:
    """B3 inputs: the B2 index (+ missing flag) and onshore wind (module-level so fitted models pickle)."""
    return np.column_stack([_x_b2(df), df["wind_pp_onshore"].to_numpy()])


def b2() -> PerLeadLogit:
    return PerLeadLogit(_x_b2)


def b3() -> PerLeadLogit:
    return PerLeadLogit(_x_b3)


def fit_all(train: pd.DataFrame) -> dict[str, object]:
    """Fit B0–B3 on training rows. B1 uses unique site-days; B3 uses rows with wind (2022+)."""
    sd = train.drop_duplicates(["site", "date"])[["site", "doy", "event"]]
    tr_w = train[train["wind_pp_onshore"].notna()]
    return {"B0": B0().fit(train), "B1": B1().fit(sd), "B2": b2().fit(train), "B3": b3().fit(tr_w)}


def predict_all(fitted: dict[str, object], df: pd.DataFrame) -> pd.DataFrame:
    """Predictions for every baseline. ``B3_fc`` = the B3 model fed lead-L forecast winds."""
    out = pd.DataFrame(index=df.index)
    for name, m in fitted.items():
        out[name] = m.predict(df)  # type: ignore[attr-defined]
    fc = df.copy()
    fc["wind_pp_onshore"] = fc["wind_fc_onshore"]
    out["B3_fc"] = fitted["B3"].predict(fc)  # type: ignore[attr-defined]
    return out
