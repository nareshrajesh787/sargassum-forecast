"""Shared helpers for the Phase 1 spike reruns (``spike/s*.py``).

Each script recomputes one row of SPEC "Feasibility tests run on live data" from cached raw data and
writes ``outputs/spike/<script>.json``:

    {"test": ..., "definition": ..., "results": [{"metric", "spike", "rerun", "unit"}...], "notes": [...]}

``spike/compare.py`` gathers them into ``outputs/spike/comparison.csv`` and flags any metric whose
rerun differs from the spike number by more than the tolerance. KICKOFF says "flag any number that
differs by more than 0.03". That is applied as an absolute difference for proportions, rates and AUCs
(values in [-1, 1]) and as a 3% relative difference for counts and other magnitudes.

Test-season note: several spike numbers were computed on 2025–2026 Broward observations, which are the
test seasons (CLAUDE.md rule 4). Rerunning them is an explicit KICKOFF instruction and G2 depends on
them. The scripts that touch 2025–2026 labels compute only the exact spike metrics (fixed rules, no
fitted parameters, no model selection) and set ``"touches_test_seasons": true`` in their output.
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

OUT = Path("outputs/spike")
LABELS = Path("data/interim/labels")
TOL_ABS = 0.03
TOL_REL = 0.03


def is_proportion(x: float) -> bool:
    return -1.0 <= x <= 1.0


def differs(spike: Any, rerun: Any) -> bool | None:
    if spike is None or rerun is None or (isinstance(rerun, float) and math.isnan(rerun)):
        return None
    if isinstance(spike, str) or isinstance(rerun, str):
        return str(spike) != str(rerun)
    if is_proportion(spike) and is_proportion(rerun):
        return abs(rerun - spike) > TOL_ABS
    return abs(rerun - spike) > TOL_REL * max(abs(spike), 1e-12)


def write(
    name: str,
    test: str,
    definition: str,
    results: list[dict[str, Any]],
    notes: list[str] | None = None,
    touches_test_seasons: bool = False,
    extra: dict[str, Any] | None = None,
) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    for r in results:
        for k in ("spike", "rerun"):
            v = r.get(k)
            if isinstance(v, (np.floating, np.integer)):
                r[k] = v.item()
            if isinstance(r.get(k), float):
                r[k] = round(r[k], 4)
        r["flag_gt_tol"] = differs(r.get("spike"), r.get("rerun"))
    doc = {
        "test": test,
        "script": f"spike/{name}.py",
        "definition": definition,
        "touches_test_seasons": touches_test_seasons,
        "results": results,
        "notes": notes or [],
        "generated_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        **(extra or {}),
    }
    p = OUT / f"{name}.json"
    p.write_text(json.dumps(doc, indent=1, default=str) + "\n")
    for r in results:
        print(f"  {r['metric']}: spike={r.get('spike')} rerun={r.get('rerun')} flag={r['flag_gt_tol']}")
    return p


def load_site_days() -> pd.DataFrame:
    p = LABELS / "site_day.parquet"
    if not p.exists():
        raise FileNotFoundError("run `uv run python -m pipeline.labels.fiu_labels` first")
    return pd.read_parquet(p)


def load_reports() -> pd.DataFrame:
    return pd.read_parquet(LABELS / "reports.parquet")


def auc(y: Any, s: Any) -> float:
    """ROC-AUC with ties counted as 1/2 (Mann–Whitney). NaNs dropped."""
    y = np.asarray(y, dtype=float)
    s = np.asarray(s, dtype=float)
    m = ~(np.isnan(y) | np.isnan(s))
    y, s = y[m], s[m]
    pos, neg = s[y == 1], s[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    ranks = pd.Series(np.concatenate([pos, neg])).rank().to_numpy()
    return float((ranks[: len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))
