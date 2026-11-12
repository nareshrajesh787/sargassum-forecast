"""Frozen forecast bundle for live use (Phase 6).

The daily job cannot rebuild models: the training data is not in the repo, and models are frozen at tag
``v0.1-test-frozen``. This packs exactly what produced the test-season predictions into one committed file:

  hybrid models (M1, M2 isotonic, M1_fc/M2_fc), from data/models/hybrid_v1.pkl (sha256 checked against
  data/test_lock/UNLOCK.json)
  baselines B0–B3 fitted on 2020–2023 (as in models.hybrid.stacked_baselines for evaluation rows)
  P1 configuration + its index→probability mapping (fit on 2021–2023)

``verify()`` re-predicts every test row from the bundle and requires an exact match with the frozen test
predictions in data/test_lock/preds_test.parquet.
"""

from __future__ import annotations

import hashlib
import json
import pickle
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

BUNDLE = Path("models/artifacts/forecast_bundle_v1.pkl")
BUNDLE_META = Path("models/artifacts/forecast_bundle_v1.json")
MODEL_FILE = Path("data/models/hybrid_v1.pkl")
UNLOCK = Path("data/test_lock/UNLOCK.json")
MODEL_VERSION = "v0.1-test-frozen"


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def build() -> dict[str, Any]:
    from eval.run_hybrid import attach_p1
    from eval.run_val import FEATURES, TRAIN_DEFAULT
    from models.baselines import fit_all
    from physics.score import fit_mapping, load_arrivals

    sha = _sha(MODEL_FILE)
    unlock = json.loads(UNLOCK.read_text())
    if unlock["model_sha256"] != sha:
        raise SystemExit("hybrid model differs from the frozen test model")
    with MODEL_FILE.open("rb") as f:
        hyb = pickle.load(f)
    feats, p1meta = attach_p1(pd.read_parquet(FEATURES))
    assert p1meta is not None
    tr = feats[feats.season.isin(TRAIN_DEFAULT)].reset_index(drop=True)
    baselines = fit_all(tr)
    arr = load_arrivals(modes=(p1meta["chosen_mode"],))
    arr = arr[np.isclose(arr.windage, p1meta["chosen_windage"])]
    lab = feats[["site", "date", "lead", "season", "event"]]
    trp = lab.merge(arr[["site", "date", "lead", "idx_window"]], on=["site", "date", "lead"])
    mapping = fit_mapping(trp[trp.season.isin(p1meta["mapping_train_seasons"])])
    bundle = {
        "model_version": MODEL_VERSION,
        "hybrid": hyb["models"],
        "params": hyb["params"],
        "baselines": baselines,
        "p1": p1meta,
        "p1_mapping": mapping,
        "train_seasons": TRAIN_DEFAULT,
        "hybrid_sha256": sha,
    }
    BUNDLE.parent.mkdir(parents=True, exist_ok=True)
    with BUNDLE.open("wb") as f:
        pickle.dump(bundle, f)
    meta = {
        "model_version": MODEL_VERSION,
        "bundle_sha256": _sha(BUNDLE),
        "hybrid_sha256": sha,
        "p1": p1meta,
        "train_seasons": TRAIN_DEFAULT,
        "features": {k: m.features for k, m in hyb["models"].items()},
    }
    BUNDLE_META.write_text(json.dumps(meta, indent=1) + "\n")
    return bundle


def load() -> dict[str, Any]:
    with BUNDLE.open("rb") as f:
        b: dict[str, Any] = pickle.load(f)
    return b


def predict(bundle: dict[str, Any], df: pd.DataFrame) -> pd.DataFrame:
    """All served/compared outputs for feature rows ``df`` (needs p1_idx_window/p1_idx_cum as log1p and the
    raw P1 index in ``idx_window``)."""
    from models.baselines import predict_all
    from physics.score import predict_mapping

    df = df.reset_index(drop=True).copy()
    base = predict_all(bundle["baselines"], df)
    for c, m in zip(["b0", "b1", "b2", "b3"], ["B0", "B1", "B2", "B3"], strict=True):
        df[c] = base[m].to_numpy()
    out = pd.DataFrame(index=df.index)
    for k in ("B0", "B1", "B2", "B3", "B3_fc"):
        out[k] = base[k].to_numpy()
    out["P1"] = predict_mapping(bundle["p1_mapping"], df[["lead", "idx_window"]])
    for abl, h in bundle["hybrid"].items():
        out["M1" if abl == "full" else f"M1_{abl}"] = h.predict_m1(df)
        if abl == "full":
            out["M2"] = h.predict_m2(df)
        if abl == "fc":
            out["M2_fc"] = h.predict_m2(df)
    return out


def verify() -> int:
    """Re-predict the frozen test rows from the bundle; returns the number of mismatching cells (must be 0)."""
    from physics.score import load_arrivals

    b = load()
    test = pd.read_parquet("data/test_lock/features/v1/features.parquet")
    arr = load_arrivals(root=Path("data/test_lock/p1"), modes=(b["p1"]["chosen_mode"],))
    arr = arr[np.isclose(arr.windage, b["p1"]["chosen_windage"])]
    a = arr[["site", "date", "lead", "idx_window", "idx_cum"]].copy()
    a["p1_idx_window"], a["p1_idx_cum"] = np.log1p(a.idx_window), np.log1p(a.idx_cum)
    test = test.merge(a, on=["site", "date", "lead"], how="left")
    got = predict(b, test)
    ref = pd.read_parquet("data/test_lock/preds_test.parquet").reset_index(drop=True)
    cols = [c for c in got.columns if c in ref.columns]
    bad = 0
    for c in cols:
        bad += int((~np.isclose(got[c].to_numpy(), ref[c].to_numpy(), atol=1e-12, equal_nan=True)).sum())
    print(f"bundle verify: {len(ref)} rows × {len(cols)} models, mismatches = {bad}")
    return bad


if __name__ == "__main__":
    build()
    raise SystemExit(1 if verify() else 0)


def load_meta() -> dict[str, Any]:
    meta: dict[str, Any] = json.loads(BUNDLE_META.read_text())
    return meta
