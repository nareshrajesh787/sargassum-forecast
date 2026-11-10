"""Feasibility: SIR archive volume and continuity, from the local back-fill manifest (data/raw/sir)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

MANIFEST = Path("data/raw/sir/manifest.csv")
OUT = Path("outputs/feasibility")


def main() -> None:
    m = pd.read_csv(MANIFEST, parse_dates=["date"])
    m["kind"] = m.file.str.extract(r"^(sargassum_risk|Sargassum_risk_currents_FA|SIR)_")[0]
    per_day = m.groupby("date").bytes.sum()
    days = pd.date_range(m.date.min(), m.date.max(), freq="D")
    complete = m.groupby("date").file.nunique().reindex(days).fillna(0)
    summary = {
        "first_day": str(m.date.min().date()),
        "last_day": str(m.date.max().date()),
        "calendar_days": len(days),
        "days_with_all_3_files": int((complete == 3).sum()),
        "days_missing_any_file": int((complete < 3).sum()),
        "mb_per_day_mean": round(float(per_day.mean() / 1e6), 2),
        "mb_per_file_mean": {k: round(float(v / 1e6), 2) for k, v in m.groupby("kind").bytes.mean().items()},
        "gb_per_365_days_estimate": round(float(per_day.mean() * 365 / 1e9), 2),
        "gb_total_archived": round(float(m.bytes.sum() / 1e9), 2),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "sir_archive.json").write_text(json.dumps(summary, indent=1) + "\n")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
