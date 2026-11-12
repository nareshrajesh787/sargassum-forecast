"""Feasibility: Open-Meteo coverage per feed × site, 2022–2026 (Mar–Oct non-null share), snapped grid cell
and its distance from the site, first/last non-null hour, and first hour of each lead-specific wind."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from pipeline.ingest.openmeteo import FEEDS, hourly_frame
from pipeline.sites import SITES, distance_km

ROOT = Path("data/raw/openmeteo")
OUT = Path("outputs/feasibility")


def main() -> None:
    rows = []
    lead_start: dict[str, Any] = {}
    for fname, feed in FEEDS.items():
        for site in SITES:
            f = hourly_frame(ROOT, fname, site.id)
            seas = f[f.index.month.isin(range(3, 11))]
            gl, gn = float(f.grid_lat.iloc[-1]), float(f.grid_lon.iloc[-1])
            for var in feed.hourly:
                s = f[var]
                nn = s.dropna()
                row = {
                    "feed": fname,
                    "site": site.id,
                    "variable": var,
                    "grid_lat": gl,
                    "grid_lon": gn,
                    "grid_km_from_site": round(float(distance_km(np.array(gl), np.array(gn), site.lat, site.lon)), 2),
                    "first_non_null": nn.index.min().isoformat() if len(nn) else None,
                    "last_non_null": nn.index.max().isoformat() if len(nn) else None,
                }
                for y in range(2022, 2027):
                    sy = seas[var][seas.index.year == y]
                    row[f"season_{y}_non_null"] = round(float(sy.notna().mean()), 4) if len(sy) else None
                rows.append(row)
                if fname == "wind_prev" and var.startswith("wind_speed") and site.id == SITES[0].id:
                    lead_start[var] = row["first_non_null"]
    df = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT / "openmeteo_coverage.csv", index=False)
    runs = sorted(ROOT.glob("_run_*.json"))
    run = [json.loads(p.read_text()) for p in runs]
    cells = df.groupby("feed").apply(lambda g: g[["grid_lat", "grid_lon"]].drop_duplicates().shape[0])
    summary = {
        "distinct_grid_cells_for_8_sites": cells.to_dict(),
        "grid_km_from_site_range": df.groupby("feed").grid_km_from_site.agg(["min", "max"]).to_dict(orient="index"),
        "wind_prev_first_non_null": lead_start,
        "requests": sum(r["requests"] for r in run),
        "weighted_calls_estimate": round(sum(r["calls_weighted"] for r in run)),
        "seconds": round(sum(r["seconds"] for r in run), 1),
    }
    (OUT / "openmeteo_coverage.json").write_text(json.dumps(summary, indent=1) + "\n")
    print(json.dumps(summary, indent=1))
    first = df[df.site == SITES[0].id][
        ["feed", "variable", "first_non_null", "last_non_null"] + [f"season_{y}_non_null" for y in range(2022, 2027)]
    ]
    print(first.to_string(index=False))


if __name__ == "__main__":
    main()
