"""Publish committed results tables to the static API as ``web/public/api/v1/results.json`` (Phase 6).

The web app displays only numbers from this file and the daily forecast/track-record files (CLAUDE.md rule 3).
Every block names the ``outputs/`` file it came from.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd

OUT = Path("outputs")
API = Path("web/public/api/v1")
SHOW = ["B1", "B0", "B2", "B3_fc", "M1_fc", "M2_fc", "P1", "M1", "M2"]


def _r(x: float, k: int = 3) -> float | None:
    return None if pd.isna(x) else round(float(x), k)


def headline() -> dict[str, Any]:
    t = pd.read_csv(OUT / "results_test.csv", dtype={"lead": str, "season": str})
    rows = []
    for season in ("2025-2026", "2025", "2026"):
        for m in SHOW:
            r = t[(t.season == season) & (t.lead == "all") & (t.model == m)]
            if r.empty:
                continue
            r = r.iloc[0]
            rows.append(
                {
                    "season": season,
                    "model": m,
                    "description": r.description,
                    "upper_bound": bool(r.perfect_prog),
                    "brier": _r(r.brier, 4),
                    "bss_vs_climatology": _r(r.bss_B1),
                    "bss_ci": [_r(r.bss_B1_lo), _r(r.bss_B1_hi)],
                    "auc": _r(r.auc),
                    "auc_ci": [_r(r.auc_lo), _r(r.auc_hi)],
                    "base_rate": _r(r.base_rate),
                }
            )
    by_lead = []
    for m in ("B0", "M1", "M2", "M1_fc", "P1"):
        for L in ("1", "2", "3", "5", "7"):
            r = t[(t.season == "2025-2026") & (t.lead == L) & (t.model == m)].iloc[0]
            by_lead.append(
                {
                    "model": m,
                    "lead": int(L),
                    "bss_vs_climatology": _r(r.bss_B1),
                    "bss_ci": [_r(r.bss_B1_lo), _r(r.bss_B1_hi)],
                }
            )
    return {"source": "outputs/results_test.csv", "rows": rows, "by_lead": by_lead}


def reliability() -> dict[str, Any]:
    r = pd.read_csv(OUT / "reliability_test.csv", dtype={"lead": str, "season": str})
    r = r[(r.season == "2025-2026") & (r.lead == "all") & (r.model.isin(["B1", "M1_fc", "M2"]))]
    return {
        "source": "outputs/reliability_test.csv",
        "bins": [
            {"model": x.model, "p_mean": _r(x.p_mean), "obs_freq": _r(x.obs_freq), "n": int(x.n)}
            for x in r.itertuples()
        ],
    }


def backtest() -> dict[str, Any]:
    b = pd.read_csv(OUT / "backtest_test.csv")
    b = b[b.booking_lead == 2]
    rows = [
        {
            "budget_hours": int(x.budget_hours),
            "policy": x.policy,
            "share_of_oracle": _r(x.share_of_oracle),
            "ci": [_r(x.share_of_oracle_lo), _r(x.share_of_oracle_hi)],
        }
        for x in b.itertuples()
    ]
    return {"source": "outputs/backtest_test.csv", "label": "SIMULATED", "booking_lead_days": 2, "rows": rows}


def ablation() -> dict[str, Any]:
    p = pd.read_csv(OUT / "results_test_paired.csv", dtype={"lead": str, "season": str})
    rows = []
    for m in ("M1_no_p1", "M1_no_afai", "M1_no_wind", "M1_fc"):
        r = p[(p.season == "2025-2026") & (p.lead == "all") & (p.model == m) & (p.reference == "M1")].iloc[0]
        rows.append(
            {
                "model": m,
                "brier_minus_M1": _r(r.brier_diff, 4),
                "ci": [_r(r.diff_lo, 4), _r(r.diff_hi, 4)],
                "verdict": r.verdict,
            }
        )
    return {"source": "outputs/results_test_paired.csv", "reference": "M1", "rows": rows}


def main() -> None:
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    meta = json.loads((OUT / "results_test_meta.json").read_text())
    doc = {
        "generated_from_commit": head,
        "test_unlocked_utc": meta["unlocked_utc"],
        "model_version": "v0.1-test-frozen",
        "headline": headline(),
        "reliability": reliability(),
        "backtest": backtest(),
        "ablation": ablation(),
        "interval_table": {
            "source": "outputs/m2_interval_table.csv",
            "rows": pd.read_csv(OUT / "m2_interval_table.csv").round(4).to_dict(orient="records"),
        },
        "gallery": {
            "source": "outputs/failure_gallery.csv",
            "rows": pd.read_csv(OUT / "failure_gallery.csv").round(3).to_dict(orient="records"),
        },
    }
    API.mkdir(parents=True, exist_ok=True)
    (API / "results.json").write_text(json.dumps(doc, indent=1) + "\n")
    print(f"wrote {API / 'results.json'}")


if __name__ == "__main__":
    main()
