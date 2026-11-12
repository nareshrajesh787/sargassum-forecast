"""Feasibility: FIU site-day label statistics per season, 2019–2026 (descriptive; nothing is scored).

Missing-day rate = 1 − labeled site-days / (8 sites × 245 Mar–Oct days). A site-day with reports but
unknown severity counts as missing. Severity shares are over labeled site-days.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from pipeline.labels.fiu_labels import PRECEDENCE
from pipeline.sites import SITE_IDS
from spike.common import load_reports, load_site_days

OUT = Path("outputs/feasibility")
SEASON_DAYS = 245


def table(sd: pd.DataFrame, keys: list[str], n_sites: int) -> pd.DataFrame:
    lab = sd[sd.severity.notna()]
    g = lab.groupby(keys)
    t = g.size().rename("labeled_site_days").to_frame()
    for k, name in enumerate(["none", "present", "moderate", "heavy"]):
        t[f"n_{name}"] = (lab.severity == k).groupby([lab[c] for c in keys]).sum().astype(int)
    for name in ["none", "present", "moderate", "heavy"]:
        t[f"share_{name}"] = t[f"n_{name}"] / t.labeled_site_days
    t["event_rate"] = (t.n_moderate + t.n_heavy) / t.labeled_site_days
    t["heavy_rate"] = t.n_heavy / t.labeled_site_days
    t["possible_site_days"] = n_sites * SEASON_DAYS
    t["missing_day_rate"] = 1 - t.labeled_site_days / t.possible_site_days
    t["site_days_unknown_severity"] = sd[sd.severity.isna()].groupby(keys).size().reindex(t.index).fillna(0).astype(int)
    return t.round(4).reset_index()


def main() -> None:
    sd = load_site_days()
    rep = load_reports()
    s = sd[sd.in_season]
    season = table(s, ["season"], len(SITE_IDS))
    site_season = table(s, ["season", "site"], 1)
    pooled = table(s.assign(all="2019-2026"), ["all"], len(SITE_IDS) * s.season.nunique())
    OUT.mkdir(parents=True, exist_ok=True)
    season.to_csv(OUT / "fiu_season_stats.csv", index=False)
    site_season.to_csv(OUT / "fiu_site_season_stats.csv", index=False)
    a = rep
    meta = {
        "precedence": PRECEDENCE,
        "reports_total": int(len(a)),
        "reports_assigned": int(a.site.notna().sum()),
        "reports_unassigned": int(a.site.isna().sum()),
        "reports_assigned_dropped_implausible_date": int((a.site.notna() & a.obs_implausible).sum()),
        "site_days_total": int(len(sd)),
        "site_days_in_season": int(len(s)),
        "site_days_out_of_season": int((~sd.in_season).sum()),
        "site_days_with_multiple_reports": int((sd.n_reports > 1).sum()),
        "upload_lag_days_quantiles_assigned": {
            str(q): float(v)
            for q, v in (
                (
                    a[a.site.notna()].uploaded_at.dt.tz_convert("America/New_York").dt.tz_localize(None).dt.normalize()
                    - a[a.site.notna()].obs_date
                )
                .dt.days.quantile([0.5, 0.9, 0.99])
                .items()
            )
        },
        "pooled": pooled.to_dict(orient="records")[0],
        "form_check_by_obs_year_assigned_reports": {
            int(y): {
                "reports": int(len(g)),
                "water_blank": int((g.water == "").sum()),
                "condition_no_sargassum": int((g.condition == "No Sargassum Present").sum()),
                "water_very_brown": int((g.water == "Very Brown").sum()),
            }
            for y, g in a[a.site.notna() & ~a.obs_implausible].groupby(a.obs_date.dt.year)
        },
    }
    (OUT / "fiu_label_summary.json").write_text(json.dumps(meta, indent=1, default=str) + "\n")
    print(
        season[
            [
                "season",
                "labeled_site_days",
                "missing_day_rate",
                "share_none",
                "share_present",
                "share_moderate",
                "share_heavy",
                "event_rate",
            ]
        ].to_string(index=False)
    )
    print(json.dumps({k: v for k, v in meta.items() if k != "pooled"}, indent=1, default=str))


if __name__ == "__main__":
    main()
