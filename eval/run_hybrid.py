"""Phase 4, validation stage: tune M1, fit M2 and ablations, evaluate on 2024 (no test data touched).

Writes
  outputs/m1_trials.csv              the ≤ 50 random-search trials (val log loss)
  outputs/m1_params.json             chosen hyper-parameters, feature lists, P1 configuration used
  outputs/results_val_hybrid.csv     B0, B1, B3, M1, M2 and the ablations on 2024 (bootstrap CIs)
  outputs/results_val_hybrid_paired.csv
2024 scores for M1/M2 are optimistic (tuned and calibrated on 2024). Only the test seasons are a fair score.
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

from eval.run_val import FEATURES, TRAIN_DEFAULT, VAL_SEASONS, evaluate
from models.hybrid import ABLATIONS, N_TRIALS, Hybrid, feature_list, stacked_baselines, tune

OUT = Path("outputs")
MODEL_DIR = Path("data/models")
P1_META = OUT / "results_val_p1_meta.json"


def attach_p1(df: pd.DataFrame) -> tuple[pd.DataFrame, dict | None]:
    """Add p1_idx_window / p1_idx_cum (log1p) for the configuration chosen in Phase 3, if it exists."""
    if not P1_META.exists():
        return df, None
    from physics.score import load_arrivals

    meta = json.loads(P1_META.read_text())
    arr = load_arrivals(modes=(meta["chosen_mode"],))
    arr = arr[np.isclose(arr.windage, meta["chosen_windage"])]
    cols = arr[["site", "date", "lead", "idx_window", "idx_cum"]].rename(
        columns={"idx_window": "p1_idx_window", "idx_cum": "p1_idx_cum"}
    )
    cols[["p1_idx_window", "p1_idx_cum"]] = np.log1p(cols[["p1_idx_window", "p1_idx_cum"]])
    return df.merge(cols, on=["site", "date", "lead"], how="left"), meta


def design(df: pd.DataFrame, train_seasons: list[int], eval_frames: list[pd.DataFrame]):  # type: ignore[no-untyped-def]
    tr = df[df.season.isin(train_seasons)].reset_index(drop=True)
    return stacked_baselines(tr, eval_frames)


def main() -> None:
    feats = pd.read_parquet(FEATURES)
    feats, p1meta = attach_p1(feats)
    va_raw = feats[feats.season.isin(VAL_SEASONS)].reset_index(drop=True)
    tr, (va,) = design(feats, TRAIN_DEFAULT, [va_raw])
    full = feature_list(tr, "full")
    params, trials = tune(tr, va, full)
    OUT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(trials).to_csv(OUT / "m1_trials.csv", index=False, float_format="%.5f")

    preds = pd.DataFrame(index=va.index)
    preds["B0"], preds["B1"], preds["B3"] = va["b0"], va["b1"], va["b3"]
    models: dict[str, Hybrid] = {}
    for abl in ABLATIONS:
        if abl == "no_p1" and p1meta is None:
            continue
        h = Hybrid(feature_list(tr, abl), params).fit(tr).calibrate(va)
        models[abl] = h
        name = "M1" if abl == "full" else f"M1_{abl}"
        preds[name] = h.predict_m1(va)
        if abl == "full":
            preds["M2"] = h.predict_m2(va)
        if abl == "fc":
            preds["M2_fc"] = h.predict_m2(va)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    with (MODEL_DIR / "hybrid_v1.pkl").open("wb") as f:
        pickle.dump({"models": models, "params": params, "train_seasons": TRAIN_DEFAULT}, f)

    names = list(preds.columns)
    res, paired = evaluate(va, preds, names)
    res.to_csv(OUT / "results_val_hybrid.csv", index=False, float_format="%.4f")
    paired.to_csv(OUT / "results_val_hybrid_paired.csv", index=False, float_format="%.4f")
    imp = pd.Series(models["full"].model.booster_.feature_importance("gain"), index=models["full"].features)
    meta = {
        "params": params,
        "n_trials": N_TRIALS,
        "best_val_logloss": min(t["val_logloss"] for t in trials),
        "train_seasons": TRAIN_DEFAULT,
        "val_seasons": VAL_SEASONS,
        "p1": p1meta,
        "features": {k: m.features for k, m in models.items()},
        "top_gain_features": imp.sort_values(ascending=False).head(15).round(1).to_dict(),
        "note": "M1 tuned and M2 calibrated on 2024: validation scores are optimistic",
    }
    (OUT / "m1_params.json").write_text(json.dumps(meta, indent=1) + "\n")
    show = res[res.lead == "all"][
        [
            "model",
            "brier",
            "bss_B0",
            "bss_B0_lo",
            "bss_B0_hi",
            "bss_B1",
            "bss_B1_lo",
            "bss_B1_hi",
            "auc",
            "auc_lo",
            "auc_hi",
        ]
    ]
    print(show.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    print(json.dumps(meta["top_gain_features"], indent=0))


if __name__ == "__main__":
    main()
