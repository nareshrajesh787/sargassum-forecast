"""Feasibility: measured ERDDAP AFAI throughput for the full 2019–2026 Mar–Oct pull (1D and 3D), and the
time steps (days) each season actually has. Reads the adapter's ``_throughput.csv`` logs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from pipeline.ingest.afai import BROWARD_UPSTREAM, DATASETS

ROOT = Path("data/raw/afai")
OUT = Path("outputs/feasibility")


def main() -> None:
    rows: list[pd.DataFrame] = []
    summary: dict[str, Any] = {}
    for key in ("1D", "3D"):
        t = pd.read_csv(ROOT / DATASETS[key] / BROWARD_UPSTREAM.tag / "_throughput.csv")
        t = t[t.status == "ok"].drop_duplicates("month", keep="last")
        t["season"] = t.month.str[:4].astype(int)
        t["dataset"] = key
        rows.append(t)
        by = t.groupby("season").agg(steps=("steps", "sum"), seconds=("seconds", "sum"), mb=("bytes", "sum"))
        by["mb"] = by.mb / 1e6
        by["calendar_days"] = 245
        by["missing_days"] = by.calendar_days - by.steps
        summary[key] = {
            "months": int(len(t)),
            "values": int(t["values"].sum()),
            "seconds_total": round(float(t.seconds.sum()), 1),
            "values_per_second": round(float(t["values"].sum() / t.seconds.sum())),
            "values_per_second_month_min": round(float((t["values"] / t.seconds).min())),
            "values_per_second_month_max": round(float((t["values"] / t.seconds).max())),
            "mb_total": round(float(t.bytes.sum() / 1e6), 1),
            "pixels_per_day": int(t["values"].sum() / t.steps.sum()),
            "per_season": by.round(1).reset_index().to_dict(orient="records"),
        }
    OUT.mkdir(parents=True, exist_ok=True)
    pd.concat(rows).to_csv(OUT / "afai_throughput_by_month.csv", index=False)
    summary["box"] = BROWARD_UPSTREAM.tag
    summary["grid_deg"] = 0.015
    summary["plan"] = (
        "full box 23–28N, 82–78W at native 0.015° (no coarsening), netCDF month by month; "
        "both products for 2019–2026 Mar–Oct measured end to end"
    )
    (OUT / "afai_throughput.json").write_text(json.dumps(summary, indent=1) + "\n")
    for key in ("1D", "3D"):
        s = summary[key]
        print(key, {k: s[k] for k in s if k != "per_season"})


if __name__ == "__main__":
    main()
