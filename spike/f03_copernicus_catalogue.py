"""Feasibility: Copernicus Marine catalogue — SMOC forecast/archive depth and the reanalysis question."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from pipeline.ingest.copernicus import PRODUCTS, SMOC, catalogue_rows, has_credentials

OUT = Path("outputs/feasibility")


def main() -> None:
    rows = [r for pid in PRODUCTS for r in catalogue_rows(pid)]
    df = pd.DataFrame(rows)
    df = df[df.current_vars.map(len) > 0]
    OUT.mkdir(parents=True, exist_ok=True)
    df.assign(current_vars=df.current_vars.map(",".join)).to_csv(OUT / "copernicus_catalogue.csv", index=False)
    smoc = df[df.dataset_id == SMOC].iloc[0]
    glorys = df[df.dataset_id.str.contains("glo_phy_my_0.083deg_P1D")]
    summary = {
        "credentials_configured": has_credentials(),
        "smoc_dataset": SMOC,
        "smoc_time_min": smoc.time_min,
        "smoc_time_max": smoc.time_max,
        "smoc_step_hours": smoc.time_step_hours,
        "smoc_grid_deg": smoc.lat_step_deg,
        "smoc_vars": smoc.current_vars,
        "reanalysis_same_grid_dataset": glorys.dataset_id.tolist(),
        "reanalysis_time_min": glorys.time_min.min() if len(glorys) else None,
        "reanalysis_time_max": glorys.time_max.max() if len(glorys) else None,
        "reanalysis_step_hours": glorys.time_step_hours.tolist(),
        "reanalysis_vars": glorys.current_vars.tolist(),
        "answer": None,
    }
    smoc_covers_2021 = smoc.time_min <= "2021-03-01"
    summary["answer"] = (
        "Same 1/12° grid: yes (GLORYS12V1, daily means of uo/vo, 1993 onward). Same product: no — no hourly "
        "fields, no tides, no Stokes drift (Stokes from the 0.2° wave reanalysis instead). SMOC itself starts "
        f"{smoc.time_min[:10]}, so it covers the 2021+ seasons"
        + ("" if smoc_covers_2021 else " (NOT 2021)")
        + ". Past forecast runs are not in the catalogue: the archive is a best-analysis series."
    )
    (OUT / "copernicus_catalogue.json").write_text(json.dumps(summary, indent=1, default=str) + "\n")
    print(df[["dataset_id", "time_min", "time_max", "time_step_hours", "lat_step_deg"]].to_string(index=False))
    print(summary["answer"])


if __name__ == "__main__":
    main()
