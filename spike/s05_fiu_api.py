"""Spike row 5: FIU Sargassum Watch API — entry count, span, 8 fixed Broward sites reported ~daily Mar–Oct."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from pipeline.ingest import fiu
from pipeline.sites import SITES
from spike.common import load_reports, load_site_days, write


def main() -> None:
    snap = fiu.latest_snapshot(Path("data/raw/fiu"))
    meta = json.loads((snap / "_meta.json").read_text())
    rep = load_reports()
    sd = load_site_days()
    s = sd[sd.in_season]
    per_site_season = s.groupby(["site", "season"]).size()
    season_days = 245  # Mar 1 – Oct 31
    coverage = (per_site_season / season_days).groupby(level="site").mean()
    results = [
        {"metric": "public_entries", "spike": 14298, "rerun": meta["unique_entries"]},
        {"metric": "oldest_entry_date", "spike": None, "rerun": meta["api_meta"]["oldest"][:10]},
        {"metric": "newest_entry_date", "spike": None, "rerun": meta["api_meta"]["newest"][:10]},
        {"metric": "n_fixed_broward_sites", "spike": 8, "rerun": int(rep.site.nunique())},
        {"metric": "reports_assigned_to_the_8_sites", "spike": None, "rerun": int(rep.site.notna().sum())},
        {"metric": "first_season_with_reports", "spike": 2019, "rerun": int(s.season.min())},
        {"metric": "last_season_with_reports", "spike": 2026, "rerun": int(s.season.max())},
        {
            "metric": "mean_share_of_season_days_reported_per_site",
            "spike": None,
            "rerun": float(coverage.mean()),
        },
    ]
    write(
        "s05_fiu_api",
        "FIU Sargassum Watch API",
        "Latest local snapshot of the Epicollect5 export; sites assigned by pipeline.labels.fiu_labels.",
        results,
        notes=[
            f"snapshot {snap.name}",
            "per-site mean share of Mar–Oct days with ≥1 report: "
            + json.dumps({k: round(v, 3) for k, v in coverage.items()}),
            "fields used: date, time, GPS, site name, condition, water colour, smell; photos never fetched",
            f"site list: {[x.name for x in SITES]}",
        ],
        extra={
            "oldest_raw": meta["api_meta"]["oldest"],
            "newest_raw": meta["api_meta"]["newest"],
            "unassigned_reports": int(rep.site.isna().sum()),
            "unassigned_top_names": rep[rep.site.isna()].site_name.value_counts().head(10).to_dict(),
            "non_season_site_days": int((~sd.in_season).sum()),
        },
    )
    _ = pd  # pandas imported for parquet engine side effects


if __name__ == "__main__":
    main()
