"""M1 (LightGBM hybrid, lead as a feature) and M2 (M1 + isotonic calibration fit on validation).

Inputs (SPEC "Model suite"): B0–B3 outputs, P1 arrival index, AFAI features, winds, waves, currents, tide,
calendar (lead, day of season, site). Baseline outputs are *stacked*: on training rows they are
leave-one-season-out predictions, so M1 never sees a baseline fitted on the same row. On validation and test
rows they come from baselines fitted on all training seasons.

Hyper-parameters: seeded random search, ``N_TRIALS`` ≤ 50 (SPEC), fit on train and scored by log loss on the
validation season. M2: ``IsotonicRegression`` fit on M1's validation predictions. Both use the validation season,
so their 2024 scores are optimistic. The test seasons are the real evaluation.

Ablations drop whole input families, including any baseline derived from them:
  no_p1    − P1 arrival features
  no_afai  − AFAI 1D/3D features and B2, B3 (AFAI-based)
  no_wind  − wind features and B3 (wind-based)
  fc       − every perfect-prog input (winds, waves, currents, P1, B3): the leakage-safe model M1_fc / M2_fc
             (added after the Phase 4 leakage-cop audit, before the test unlock)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import log_loss

from models.baselines import fit_all, predict_all

SEED = 20261110
N_TRIALS = 50
BASE_COLS = ["b0", "b1", "b2", "b3"]
CALENDAR = ["lead", "day_of_season", "site_idx"]
TIDE = ["tide_range_m", "tide_hours_since_high_12utc", "tide_phase_12utc"]
PERSIST = ["last_sev", "last_event", "last_age_days", "n_reports_7d", "event_rate_7d", "region_event_rate_3d"]
WIND = ["wind_pp_onshore", "wind_pp_speed", "wind_pp_onshore_3d"]
WAVES = ["waves_pp_hs", "waves_pp_tp", "waves_pp_onshore"]
CURR = ["curr_pp_onshore", "curr_pp_along"]
P1 = ["p1_idx_window", "p1_idx_cum"]
ABLATIONS = {
    "full": [],
    "no_p1": P1,
    "no_afai": ["afai", "b2", "b3"],
    "no_wind": WIND + ["b3"],
    # leakage-safe: only inputs known at the issue time (no perfect-prog drivers, no P1, no wind-based B3)
    "fc": WIND + WAVES + CURR + P1 + ["b3"],
}


def afai_cols(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c.startswith(("afai1d_", "afai3d_"))]


def feature_list(df: pd.DataFrame, ablation: str = "full") -> list[str]:
    cols = CALENDAR + TIDE + PERSIST + afai_cols(df) + WIND + WAVES + CURR + BASE_COLS
    cols += [c for c in P1 if c in df.columns]
    drop = ABLATIONS[ablation]
    out = []
    for c in cols:
        if c in drop or ("afai" in drop and c.startswith(("afai1d_", "afai3d_"))):
            continue
        out.append(c)
    return out


def stacked_baselines(train: pd.DataFrame, others: list[pd.DataFrame]) -> tuple[pd.DataFrame, list[pd.DataFrame]]:
    """Add b0..b3: leave-one-season-out on ``train``; fit-on-all-train for each frame in ``others``."""
    train = train.copy()
    for c in BASE_COLS:
        train[c] = np.nan
    for s in sorted(train.season.unique()):
        hold = train.season == s
        fitted = fit_all(train[~hold].reset_index(drop=True))
        p = predict_all(fitted, train[hold].reset_index(drop=True))
        for c, m in zip(BASE_COLS, ["B0", "B1", "B2", "B3"], strict=True):
            train.loc[hold, c] = p[m].to_numpy()
    fitted = fit_all(train.reset_index(drop=True))
    outs = []
    for o in others:
        o = o.copy().reset_index(drop=True)
        p = predict_all(fitted, o)
        for c, m in zip(BASE_COLS, ["B0", "B1", "B2", "B3"], strict=True):
            o[c] = p[m].to_numpy()
        outs.append(o)
    return train, outs


def sample_params(rng: np.random.Generator) -> dict[str, Any]:
    return {
        "num_leaves": int(rng.choice([7, 15, 31, 63])),
        "learning_rate": float(10 ** rng.uniform(-2.0, -0.8)),
        "n_estimators": int(rng.choice([100, 200, 400, 800])),
        "min_child_samples": int(rng.choice([20, 50, 100, 200])),
        "colsample_bytree": float(rng.uniform(0.5, 1.0)),
        "subsample": float(rng.uniform(0.6, 1.0)),
        "subsample_freq": 1,
        "reg_lambda": float(10 ** rng.uniform(-2, 1.5)),
    }


def _lgbm(params: dict[str, Any]) -> Any:
    import lightgbm as lgb

    return lgb.LGBMClassifier(objective="binary", random_state=SEED, verbose=-1, n_jobs=4, **params)


@dataclass
class Hybrid:
    features: list[str]
    params: dict[str, Any]
    model: Any = None
    iso: IsotonicRegression | None = None
    trials: list[dict[str, Any]] = field(default_factory=list)

    def fit(self, train: pd.DataFrame) -> Hybrid:
        self.model = _lgbm(self.params).fit(train[self.features], train["event"])
        return self

    def predict_m1(self, df: pd.DataFrame) -> np.ndarray:
        return np.asarray(self.model.predict_proba(df[self.features])[:, 1])

    def calibrate(self, val: pd.DataFrame) -> Hybrid:
        self.iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip").fit(
            self.predict_m1(val), val["event"]
        )
        return self

    def predict_m2(self, df: pd.DataFrame) -> np.ndarray:
        assert self.iso is not None, "calibrate() first"
        return np.asarray(self.iso.predict(self.predict_m1(df)))


def tune(
    train: pd.DataFrame, val: pd.DataFrame, features: list[str], n_trials: int = N_TRIALS, seed: int = SEED
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rng = np.random.default_rng(seed)
    trials = []
    for t in range(n_trials):
        params = sample_params(rng)
        m = _lgbm(params).fit(train[features], train["event"])
        p = m.predict_proba(val[features])[:, 1]
        trials.append({"trial": t, "val_logloss": float(log_loss(val["event"], p)), **params})
    best = min(trials, key=lambda r: r["val_logloss"])
    params = {k: v for k, v in best.items() if k not in ("trial", "val_logloss")}
    return params, trials
