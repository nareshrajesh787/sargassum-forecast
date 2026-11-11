"""Score P1 alone against B0/B1 on the 2024 validation season (Gate G3).

1. Arrival tables (``data/interim/p1/<mode>/<issue>.parquet``) → one row per (site, target date D, lead,
   mode, windage) with ``idx_window`` (arrivals in the 24 h before the morning of D) and ``idx_cum``.
2. Sweep (validation only, as the SPEC says): for each (mode, windage) the ROC-AUC of ``log1p(idx_window)`` on
   2024 labeled site-days, leads pooled. Rank-based, so no calibration is needed to choose. Written to
   ``outputs/p1_sweep_val.csv``. Picking the best of 8 configurations on 2024 flatters P1's 2024 AUC; the
   G3 summary says so.
3. The chosen configuration's index → probability: logistic regression per lead fit on training seasons
   (2021–2023 runs of that configuration only), then scored on 2024 with the paired weekly-block bootstrap
   from ``eval.run_val`` → ``outputs/results_val_p1.csv`` and ``outputs/results_val_p1_paired.csv``.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from eval.metrics import roc_auc
from physics.drift import OUT as P1_DIR

OUT = Path("outputs")
TRAIN_SEASONS = (2021, 2022, 2023)
VAL_SEASON = 2024
SEED = 20261110


def load_arrivals(root: Path = P1_DIR, modes: tuple[str, ...] = ("total", "no_stokes")) -> pd.DataFrame:
    frames = [pd.read_parquet(p) for m in modes for p in sorted((root / m).glob("*.parquet"))]
    frames = [f for f in frames if len(f)]
    if not frames:
        raise FileNotFoundError(f"no P1 arrival tables under {root}; run `python -m physics.drift` first")
    a = pd.concat(frames, ignore_index=True)
    a["issue_date"] = pd.to_datetime(a["issue_date"])
    a["date"] = a["issue_date"] + pd.to_timedelta(a["lead"], unit="D")
    return a


def p1_features(arr: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    """Join arrivals to labeled rows. Issue days whose seed field was empty (no detections) get index 0."""
    keys = ["site", "date", "lead"]
    return labels.merge(arr[keys + ["mode", "windage", "idx_window", "idx_cum"]], on=keys, how="inner")


def sweep(feat_val: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (mode, w), g in feat_val.groupby(["mode", "windage"]):
        rows.append(
            {
                "mode": mode,
                "windage": w,
                "n": len(g),
                "auc_window": roc_auc(g.event, np.log1p(g.idx_window)),
                "auc_cum": roc_auc(g.event, np.log1p(g.idx_cum)),
            }
        )
    return pd.DataFrame(rows).sort_values("auc_window", ascending=False).reset_index(drop=True)


def fit_mapping(train: pd.DataFrame) -> dict[int, LogisticRegression]:
    models = {}
    for L, g in train.groupby("lead"):
        m = LogisticRegression(C=1e4, max_iter=1000, random_state=SEED)
        m.fit(np.log1p(g[["idx_window"]].to_numpy()), g["event"].to_numpy())
        models[int(L)] = m
    return models


def predict_mapping(models: dict[int, LogisticRegression], df: pd.DataFrame) -> np.ndarray:
    out = np.full(len(df), np.nan)
    for L, g in df.groupby("lead"):
        out[df.index.get_indexer(g.index)] = models[int(L)].predict_proba(np.log1p(g[["idx_window"]].to_numpy()))[:, 1]
    return out


def main() -> None:
    from eval.run_val import FEATURES, TRAIN_DEFAULT, evaluate
    from models.baselines import fit_all, predict_all

    feats = pd.read_parquet(FEATURES)
    arr = load_arrivals()
    p1 = p1_features(arr, feats[["site", "date", "lead", "season", "event"]])
    sw = sweep(p1[p1.season == VAL_SEASON])
    OUT.mkdir(parents=True, exist_ok=True)
    sw.to_csv(OUT / "p1_sweep_val.csv", index=False, float_format="%.4f")
    best = sw.iloc[0]
    chosen = p1[(p1["mode"] == best["mode"]) & (p1.windage == best.windage)]
    tr = chosen[chosen.season.isin(TRAIN_SEASONS)]
    if tr.empty:
        raise SystemExit(f"run the chosen config on {TRAIN_SEASONS} first: mode={best['mode']} windage={best.windage}")
    mapping = fit_mapping(tr)
    va = feats[feats.season == VAL_SEASON].reset_index(drop=True)
    va = va.merge(chosen[["site", "date", "lead", "idx_window"]], on=["site", "date", "lead"], how="inner")
    preds = predict_all(fit_all(feats[feats.season.isin(TRAIN_DEFAULT)].reset_index(drop=True)), va)
    preds["P1"] = predict_mapping(mapping, va)
    res, paired = evaluate(va, preds, ["B0", "B1", "P1"])
    res.to_csv(OUT / "results_val_p1.csv", index=False, float_format="%.4f")
    paired.to_csv(OUT / "results_val_p1_paired.csv", index=False, float_format="%.4f")
    meta = {
        "chosen_mode": best["mode"],
        "chosen_windage": float(best.windage),
        "selection": "max 2024 AUC of idx_window",
        "mapping_train_seasons": list(TRAIN_SEASONS),
        "n_val_rows": len(va),
        "perfect_prog": True,
    }
    (OUT / "results_val_p1_meta.json").write_text(json.dumps(meta, indent=1) + "\n")
    print(sw.to_string(index=False))
    print(res[res.lead != "all"][["model", "lead", "brier", "bss_B0", "bss_B1", "auc"]].to_string(index=False))


if __name__ == "__main__":
    main()
