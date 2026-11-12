"""Site-day severity labels from FIU Sargassum Watch reports (frozen rules, SPEC "Targets, labels").

Severity per report:
    3 Heavy    water colour "Very Brown"
    2 Moderate water "Slightly brown" or the site smells
    0 None     condition "No Sargassum Present"
    1 Present  any other recorded condition (sargassum present, water unchanged, no smell)
    NaN        condition blank and nothing elevates it (presence unknown)

Precedence: ``PRECEDENCE`` decides whether a "No Sargassum Present" report with brown water or smell
is 0 ("none_first") or 2/3 ("water_first"). The SPEC table does not say. Phase 1 picks the order that
reproduces the spike's published counts (``spike/s06_label_base_rates.py``); it is a definition
clarification, not a tuned choice, and is frozen in ``PRECEDENCE`` below.

Site assignment (``assign_site``):
    (a) the reported name matches exactly one site's alias regex and the GPS is missing or within
        ``NAME_GPS_MAX_KM`` of that site; or
    (b) the name matches no alias and the GPS is within ``GPS_ONLY_MAX_KM`` of a site.
    Everything else is unassigned (other beaches, generic names far from a site, name/GPS conflicts).

Observation date = the observer's "Date of Observation" field, which is DD/MM/YYYY (checked against
``created_at``: 99% agree on the same local day). Reports dated after their own creation, or more than
``MAX_REPORT_LAG_DAYS`` before it (5 reports, all typos such as a 2018 date on a June 2021 entry), are dropped.

Form change: in 2019 the water-colour question was not asked (blank on ~99% of 2019 reports) and
"No Sargassum Present" was never chosen, so 2019 severity can reach 2 only through smell and never 3.
The rules are not changed for this (they are frozen); FEASIBILITY.md raises it for the owner.

Site-day label = worst severity among that site's reports that day (SPEC: "duplicates are merged by
taking the worst report"). ``available_at`` = latest ``uploaded_at`` among the merged reports (UTC):
the label is only fully known once its last report is in.

Outputs are written under ``data/`` (never committed): derived labels are published only if FIU agrees.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd

from pipeline.ingest import fiu
from pipeline.sites import SITES, distance_km

Precedence = Literal["none_first", "water_first"]
PRECEDENCE: Precedence = "none_first"  # frozen in Phase 1: reproduces the spike counts (FEASIBILITY.md)
NAME_GPS_MAX_KM = 2.0
GPS_ONLY_MAX_KM = 0.3
MAX_REPORT_LAG_DAYS = 30
SEASON_MONTHS = tuple(range(3, 11))  # March–October
NO_SARGASSUM = "No Sargassum Present"
_ALIAS = [re.compile(s.aliases) for s in SITES]


def _norm(name: str | None) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def parse_reports(entries: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for e in entries:
        gps = e.get("3_GPS_Coordinates_of") or {}
        rows.append(
            {
                "uuid": e["ec5_uuid"],
                "created_at": e["created_at"],
                "uploaded_at": e["uploaded_at"],
                "obs_date_raw": e.get("1_Date_of_Observatio") or "",
                "obs_time_raw": e.get("2_Time_of_Observatio") or "",
                "site_name": _norm(e.get("4_Site_Name_eg_Miami")),
                "lat": gps.get("latitude"),
                "lon": gps.get("longitude"),
                "condition": (e.get("12_Condition_of_the_") or "").strip(),
                "water": (e.get("14_Color_of_the_wate") or "").strip(),
                "smell": (e.get("15_Does_the_site_sme") or "").strip(),
            }
        )
    df = pd.DataFrame(rows)
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True)
    df["uploaded_at"] = pd.to_datetime(df["uploaded_at"], utc=True)
    df["obs_date"] = pd.to_datetime(df["obs_date_raw"], format="%d/%m/%Y", errors="coerce")
    return df


def severity(condition: str, water: str, smell: str, precedence: Precedence = PRECEDENCE) -> float:
    """Frozen severity rule for one report. Returns 0–3 or NaN (unknown)."""
    none = condition == NO_SARGASSUM
    if none and precedence == "none_first":
        return 0.0
    if water == "Very Brown":
        return 3.0
    if water == "Slightly brown" or smell == "Yes":
        return 2.0
    if none:
        return 0.0
    if condition:
        return 1.0
    return float("nan")


def assign_site(df: pd.DataFrame) -> pd.Series:
    names = df["site_name"].to_numpy()
    lat, lon = df["lat"].to_numpy(), df["lon"].to_numpy()
    dist = np.stack([distance_km(lat, lon, s.lat, s.lon) for s in SITES], axis=1)
    match = np.array([[bool(rx.search(n)) for rx in _ALIAS] for n in names]).reshape(len(df), len(SITES))
    out: list[str | None] = []
    for i in range(len(df)):
        hits = np.flatnonzero(match[i])
        if len(hits) == 1:
            j = hits[0]
            d = dist[i, j]
            out.append(SITES[j].id if (np.isnan(d) or d <= NAME_GPS_MAX_KM) else None)
        elif len(hits) == 0 and not np.isnan(dist[i]).all():
            j = int(np.nanargmin(dist[i]))
            out.append(SITES[j].id if dist[i, j] <= GPS_ONLY_MAX_KM else None)
        else:
            out.append(None)
    return pd.Series(out, index=df.index, name="site", dtype="object")


def label_reports(df: pd.DataFrame, precedence: Precedence = PRECEDENCE) -> pd.DataFrame:
    df = df.copy()
    df["site"] = assign_site(df)
    df["severity"] = [severity(c, w, s, precedence) for c, w, s in zip(df.condition, df.water, df.smell, strict=True)]
    created_local = df["created_at"].dt.tz_convert("America/New_York").dt.tz_localize(None).dt.normalize()
    lag = (created_local - df["obs_date"]).dt.days
    df["obs_after_upload"] = lag < 0
    df["obs_implausible"] = (lag < 0) | (lag > MAX_REPORT_LAG_DAYS)
    return df


def site_days(reports: pd.DataFrame) -> pd.DataFrame:
    """Merge assigned, dated, non-future reports to one row per site-day (worst severity)."""
    r = reports[reports["site"].notna() & reports["obs_date"].notna() & ~reports["obs_implausible"]]
    g = r.groupby(["site", "obs_date"])
    sd = g.agg(
        severity=("severity", "max"),  # max skips NaN; all-NaN → NaN
        n_reports=("uuid", "size"),
        available_at=("uploaded_at", "max"),
    ).reset_index()
    sd = sd.rename(columns={"obs_date": "date"})
    sd["season"] = sd["date"].dt.year
    sd["in_season"] = sd["date"].dt.month.isin(SEASON_MONTHS)
    sd["event"] = (sd["severity"] >= 2).where(sd["severity"].notna())
    sd["heavy"] = (sd["severity"] >= 3).where(sd["severity"].notna())
    return sd


def build(snapshot_dir: Path, precedence: Precedence = PRECEDENCE) -> tuple[pd.DataFrame, pd.DataFrame]:
    reports = label_reports(parse_reports(fiu.load_entries(snapshot_dir)), precedence)
    return reports, site_days(reports)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fiu-root", type=Path, default=Path("data/raw/fiu"))
    ap.add_argument("--out", type=Path, default=Path("data/interim/labels"))
    a = ap.parse_args()
    snap = fiu.latest_snapshot(a.fiu_root)
    reports, sd = build(snap)
    a.out.mkdir(parents=True, exist_ok=True)
    reports.to_parquet(a.out / "reports.parquet", index=False)
    sd.to_parquet(a.out / "site_day.parquet", index=False)
    print(f"{snap.name}: {len(reports)} reports, {reports.site.notna().sum()} assigned, {len(sd)} site-days")


if __name__ == "__main__":
    main()
