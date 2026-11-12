"""Feature store: one row per (site, target date D, lead L) with a label, for seasons ≤ 2024.

Issue time for a row = 12:00 UTC on issue day I = D − L. Every feature belongs to a *group*, and every
group has an ``avail_<group>`` column = the latest ``available_at`` of any input the group used.
``tests/test_features.py`` asserts ``avail_<group> <= issue_time`` for every group except the
perfect-prognosis groups in ``PERFECT_PROG`` (G1 default, FEASIBILITY §7). Those use analysed or
short-lead drivers valid on the target day. Their ``avail_*`` is honestly *after* the issue time, and models
that use them are labelled "perfect-prog (upper bound)" in every results table.

Groups
  calendar   site, lead, day of season (deterministic)
  tide       NOAA CO-OPS predictions for D (deterministic)
  persist    beach reports with date ≤ I − 1 and uploaded by the issue time ("up to the day before")
  afai1d/3d  AFAI region stats for days ≤ I − 1 (1-day latency, SPEC)
  wind_fc    GFS lead-L forecasts (Open-Meteo previous_dayL), 2024+ only, leakage-safe
  wind_pp    GFS stitched short-lead series (perfect-prog)
  waves_pp   MFWAM analysis/forecast series (perfect-prog)
  curr_pp    SMOC point currents (perfect-prog)

Driver window for target day D: [D−1 12:00, D 06:00] UTC (the night before a morning report). For
wind_fc, the value at hour h comes from the run ~24·L h earlier and is published ~6 h after its run time,
so h ≤ D 06:00 keeps it available by I 12:00.

Output: ``data/features/v<FEATURE_VERSION>/features.parquet`` + ``manifest.json``.
Test seasons (2025, 2026) are refused unless ``allow_test=True`` (Phase 4 only).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline.geo import onshore, shore_normal_deg
from pipeline.ingest import tides
from pipeline.ingest.openmeteo import LEADS, hourly_frame
from pipeline.sites import SITES

FEATURE_VERSION = 1
TEST_SEASONS = (2025, 2026)
LEADS_ALL = LEADS  # (1, 2, 3, 5, 7)
ISSUE_HOUR = 12
PERFECT_PROG = ("wind_pp", "waves_pp", "curr_pp")
GROUPS = ("calendar", "tide", "persist", "afai1d", "afai3d", "wind_fc", *PERFECT_PROG)
NEVER = pd.Timestamp("1970-01-01", tz="UTC")
LABELS = Path("data/interim/labels/site_day.parquet")
AFAI_STATS = Path("data/interim/afai")
OM_ROOT = Path("data/raw/openmeteo")
TIDE_ROOT = Path("data/raw/tides")
OUT = Path("data/features")
AFAI_REGIONS_SHARED = ("offshore", "south", "east")
MIN_VALID_FRAC = 0.10


class TestSeasonLocked(RuntimeError):
    pass


def check_seasons(seasons: list[int], allow_test: bool) -> None:
    bad = sorted(set(seasons) & set(TEST_SEASONS))
    if bad and not allow_test:
        raise TestSeasonLocked(f"test seasons {bad} are locked until Gate 4 (CLAUDE.md rule 4)")


# ---------------------------------------------------------------- skeleton
def skeleton(labels: pd.DataFrame, seasons: list[int]) -> pd.DataFrame:
    lab = labels[labels.season.isin(seasons) & labels.in_season & labels.event.notna()]
    lab = lab[["site", "date", "season", "severity", "event", "heavy"]].copy()
    rows = []
    for L in LEADS_ALL:
        r = lab.copy()
        r["lead"] = L
        rows.append(r)
    df = pd.concat(rows, ignore_index=True)
    df["issue_date"] = df["date"] - pd.to_timedelta(df["lead"], unit="D")
    df["issue_time"] = df["issue_date"].dt.tz_localize("UTC") + pd.Timedelta(hours=ISSUE_HOUR)
    df["event"] = df["event"].astype(int)
    df["heavy"] = df["heavy"].astype(int)
    return df.sort_values(["site", "date", "lead"]).reset_index(drop=True)


# ---------------------------------------------------------------- calendar + tide
def add_calendar(df: pd.DataFrame) -> pd.DataFrame:
    df["day_of_season"] = (df["date"] - pd.to_datetime(df["season"].astype(str) + "-03-01")).dt.days
    df["doy"] = df["date"].dt.day_of_year
    df["site_idx"] = df["site"].map({s.id: i for i, s in enumerate(SITES)})
    df["avail_calendar"] = NEVER
    return df


def tide_daily(root: Path = TIDE_ROOT) -> pd.DataFrame:
    t = tides.load(root)
    t["date"] = t["time"].dt.tz_convert(None).dt.normalize()
    g = t.groupby("date")
    d = pd.DataFrame({"tide_range_m": g.height_m.max() - g.height_m.min()})
    highs = t[t.type == "H"].reset_index(drop=True)
    rows = []
    for day in d.index:
        ref = pd.Timestamp(day, tz="UTC") + pd.Timedelta(hours=ISSUE_HOUR)  # 08:00 EDT, typical report time
        prev = highs[highs.time <= ref].tail(1)
        rows.append((ref - prev.time.iloc[0]).total_seconds() / 3600 if len(prev) else np.nan)
    d["tide_hours_since_high_12utc"] = rows
    d["tide_phase_12utc"] = (d["tide_hours_since_high_12utc"] / 12.42) % 1.0
    return d


def add_tide(df: pd.DataFrame) -> pd.DataFrame:
    d = tide_daily()
    df = df.merge(d, left_on="date", right_index=True, how="left")
    df["avail_tide"] = NEVER
    return df


# ---------------------------------------------------------------- persistence (beach reports)
def add_persist(df: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    """Latest report ≤ 3 days old (date ≤ I−1) uploaded by the issue time, plus 7-day and regional rates."""
    lab = labels[labels.severity.notna()][["site", "date", "severity", "event", "available_at"]].copy()
    lab["event"] = lab["event"].astype(float)
    out = []
    keys = df[["site", "issue_date", "issue_time"]].drop_duplicates()
    by_site = {s: g.sort_values("date") for s, g in lab.groupby("site")}
    all_lab = lab.sort_values("date")
    for row in keys.itertuples(index=False):
        iss, T = row.issue_date, row.issue_time
        g = by_site.get(row.site)
        rec: dict[str, object] = {"site": row.site, "issue_date": iss}
        avail = NEVER
        if g is not None:
            w7 = g[
                (g.date >= iss - pd.Timedelta(days=7)) & (g.date <= iss - pd.Timedelta(days=1)) & (g.available_at <= T)
            ]
            last = w7[w7.date >= iss - pd.Timedelta(days=3)].tail(1)
            if len(last):
                rec["last_sev"] = float(last.severity.iloc[0])
                rec["last_event"] = float(last.event.iloc[0])
                rec["last_age_days"] = float((iss - last.date.iloc[0]).days)
            rec["n_reports_7d"] = float(len(w7))
            rec["event_rate_7d"] = float(w7.event.mean()) if len(w7) else np.nan
            if len(w7):
                avail = max(avail, w7.available_at.max())
        r3 = all_lab[
            (all_lab.date >= iss - pd.Timedelta(days=3))
            & (all_lab.date <= iss - pd.Timedelta(days=1))
            & (all_lab.available_at <= T)
        ]
        rec["region_event_rate_3d"] = float(r3.event.mean()) if len(r3) else np.nan
        if len(r3):
            avail = max(avail, r3.available_at.max())
        rec["avail_persist"] = avail
        out.append(rec)
    p = pd.DataFrame(out)
    return df.merge(p, on=["site", "issue_date"], how="left")


# ---------------------------------------------------------------- AFAI
def afai_window_stats(stats: pd.DataFrame, region: str, issue_dates: pd.Series) -> pd.DataFrame:
    """For each issue day I: det_frac 7-day mean (days I−7..I−1, valid-weighted), 30-day baseline (I−37..I−8),
    anomaly, latest valid det_frac and its age, mean valid fraction over the last 7 days."""
    s = stats[stats.region == region].set_index("date").sort_index()
    s = s.reindex(pd.date_range(s.index.min(), s.index.max(), freq="D"))
    ok = s.valid_frac >= MIN_VALID_FRAC
    det = s.det_frac.where(ok)
    w = s.n_valid.where(ok).fillna(0)
    num7 = (det.fillna(0) * w).rolling(7, min_periods=1).sum()
    den7 = w.rolling(7, min_periods=1).sum()
    num30 = (det.fillna(0) * w).rolling(30, min_periods=1).sum()
    den30 = w.rolling(30, min_periods=1).sum()
    recent = (num7 / den7.replace(0, np.nan)).shift(1)  # window ends I−1
    base = (num30 / den30.replace(0, np.nan)).shift(8)  # window ends I−8
    last_valid_date = pd.Series(s.index.where(ok), index=s.index).ffill().shift(1)
    last_det = det.ffill().shift(1)
    vf7 = s.valid_frac.rolling(7, min_periods=1).mean().shift(1)
    out = pd.DataFrame(
        {
            "recent7": recent,
            "base30": base,
            "anom": recent - base,
            "last": last_det,
            "age": (s.index.to_series() - last_valid_date).dt.days,
            "valid7": vf7,
        }
    )
    return out.reindex(pd.DatetimeIndex(issue_dates))


def add_afai(df: pd.DataFrame, key: str, afai_dir: Path = AFAI_STATS) -> pd.DataFrame:
    stats = pd.read_parquet(afai_dir / f"stats_{key}.parquet")
    k = key.lower()
    issue = df["issue_date"]
    cols: dict[str, np.ndarray] = {}
    for region in AFAI_REGIONS_SHARED:
        w = afai_window_stats(stats, region, issue)
        for c in ("recent7", "anom", "valid7"):
            cols[f"afai{k}_{region}_{c}"] = w[c].to_numpy()
    for kind in ("band", "r50"):
        vals = {c: np.full(len(df), np.nan) for c in ("recent7", "anom", "last", "age", "valid7")}
        for s in SITES:
            m = (df["site"] == s.id).to_numpy()
            w = afai_window_stats(stats, f"{kind}_{s.id}", issue[m])
            for c in vals:
                vals[c][m] = w[c].to_numpy()
        for c, v in vals.items():
            cols[f"afai{k}_{kind}_{c}"] = v
    df = pd.concat([df, pd.DataFrame(cols, index=df.index)], axis=1)
    # inputs are days ≤ I−1, each available at day + 1.5 d  →  ≤ I 12:00 UTC
    df[f"avail_afai{k}"] = (df["issue_date"] - pd.Timedelta(days=1)).dt.tz_localize("UTC") + pd.Timedelta(days=1.5)
    return df


# ---------------------------------------------------------------- Open-Meteo drivers
def _window(D: pd.Series) -> tuple[pd.Series, pd.Series]:
    start = D.dt.tz_localize("UTC") - pd.Timedelta(hours=12)
    end = D.dt.tz_localize("UTC") + pd.Timedelta(hours=6)
    return start, end


def _window_mean(hourly: pd.Series, D: pd.Series) -> np.ndarray:
    """Mean of an hourly UTC series over [D−1 12:00, D 06:00] for each target date (vectorised by day)."""
    shifted = hourly.copy()
    shifted.index = shifted.index + pd.Timedelta(hours=12)  # hour D-1 12:00 → D 00:00
    shifted = shifted[shifted.index.hour <= 18]  # original ≤ D 06:00
    daily = shifted.groupby(shifted.index.normalize().tz_convert(None)).mean()
    return daily.reindex(pd.DatetimeIndex(D)).to_numpy()


def add_openmeteo(df: pd.DataFrame) -> pd.DataFrame:
    n = len(df)
    new: dict[str, np.ndarray] = {
        c: np.full(n, np.nan)
        for c in (
            "wind_pp_onshore",
            "wind_pp_speed",
            "wind_pp_onshore_3d",
            "wind_fc_onshore",
            "wind_fc_speed",
            "waves_pp_hs",
            "waves_pp_tp",
            "waves_pp_onshore",
            "curr_pp_onshore",
            "curr_pp_along",
        )
    }
    for s in SITES:
        m = (df["site"] == s.id).to_numpy()
        D = df.loc[m, "date"]
        nrm = shore_normal_deg(s.lat, s.lon)
        w = hourly_frame(OM_ROOT, "wind_hf", s.id)
        on = pd.Series(onshore(w.wind_speed_10m, w.wind_direction_10m, nrm), index=w.index)
        new["wind_pp_onshore"][m] = _window_mean(on, D)
        new["wind_pp_speed"][m] = _window_mean(w.wind_speed_10m, D)
        on3 = on.rolling(66, min_periods=24).mean()  # 66 h ending at the window end ≈ 3 days
        new["wind_pp_onshore_3d"][m] = on3.reindex(D.dt.tz_localize("UTC") + pd.Timedelta(hours=6)).to_numpy()
        prev = hourly_frame(OM_ROOT, "wind_prev", s.id)
        for L in LEADS_ALL:
            ml = m & (df["lead"] == L).to_numpy()
            if not ml.any():
                continue
            Dl = df.loc[ml, "date"]
            sp, dr = prev[f"wind_speed_10m_previous_day{L}"], prev[f"wind_direction_10m_previous_day{L}"]
            new["wind_fc_onshore"][ml] = _window_mean(pd.Series(onshore(sp, dr, nrm), index=prev.index), Dl)
            new["wind_fc_speed"][ml] = _window_mean(sp, Dl)
        wv = hourly_frame(OM_ROOT, "marine_waves", s.id)
        new["waves_pp_hs"][m] = _window_mean(wv.wave_height, D)
        new["waves_pp_tp"][m] = _window_mean(wv.wave_period, D)
        new["waves_pp_onshore"][m] = _window_mean(
            pd.Series(onshore(wv.wave_height, wv.wave_direction, nrm), index=wv.index), D
        )
        c = hourly_frame(OM_ROOT, "marine_currents", s.id)
        c["ocean_current_velocity"] = c["ocean_current_velocity"] / 3.6  # Open-Meteo serves km/h → m/s
        # currents: direction is where the flow goes TO → onshore = −cos(dir − normal)
        new["curr_pp_onshore"][m] = _window_mean(
            pd.Series(-onshore(c.ocean_current_velocity, c.ocean_current_direction, nrm), index=c.index), D
        )
        new["curr_pp_along"][m] = _window_mean(
            pd.Series(onshore(c.ocean_current_velocity, c.ocean_current_direction, nrm - 90), index=c.index), D
        )
    df = pd.concat([df, pd.DataFrame(new, index=df.index)], axis=1)
    start, end = _window(df["date"])
    for g in PERFECT_PROG:
        df[f"avail_{g}"] = end  # valid-time data: after the issue time by construction (perfect-prog)
    # wind_fc: hour h from the run ~24·L h earlier, published ≤ 6 h after run time
    df["avail_wind_fc"] = end - pd.to_timedelta(df["lead"] * 24, unit="h") + pd.Timedelta(hours=6)
    df.loc[df["wind_fc_onshore"].isna(), "avail_wind_fc"] = NEVER
    return df


# ---------------------------------------------------------------- driver
FEATURE_GROUPS: dict[str, list[str]] = {}


def feature_groups(df: pd.DataFrame) -> dict[str, list[str]]:
    g: dict[str, list[str]] = {
        "calendar": ["lead", "day_of_season", "doy", "site_idx"],
        "tide": ["tide_range_m", "tide_hours_since_high_12utc", "tide_phase_12utc"],
        "persist": ["last_sev", "last_event", "last_age_days", "n_reports_7d", "event_rate_7d", "region_event_rate_3d"],
        "afai1d": [c for c in df.columns if c.startswith("afai1d_")],
        "afai3d": [c for c in df.columns if c.startswith("afai3d_")],
        "wind_fc": ["wind_fc_onshore", "wind_fc_speed"],
        "wind_pp": ["wind_pp_onshore", "wind_pp_speed", "wind_pp_onshore_3d"],
        "waves_pp": ["waves_pp_hs", "waves_pp_tp", "waves_pp_onshore"],
        "curr_pp": ["curr_pp_onshore", "curr_pp_along"],
    }
    return g


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def build(seasons: list[int], allow_test: bool = False, afai_dir: Path = AFAI_STATS) -> pd.DataFrame:
    check_seasons(seasons, allow_test)
    labels = pd.read_parquet(LABELS)
    df = skeleton(labels, seasons)
    df = add_calendar(df)
    df = add_tide(df)
    df = add_persist(df, labels)
    df = add_afai(df, "1D", afai_dir)
    df = add_afai(df, "3D", afai_dir)
    df = add_openmeteo(df)
    for g in GROUPS:
        if f"avail_{g}" not in df.columns:
            raise AssertionError(f"group {g} has no avail column")
    return df


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", nargs="+", type=int, default=list(range(2019, 2025)))
    a = ap.parse_args()
    df = build(a.seasons)
    out = OUT / f"v{FEATURE_VERSION}"
    out.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out / "features.parquet", index=False)
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    except OSError:
        sha = ""
    manifest = {
        "feature_version": FEATURE_VERSION,
        "built_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_head": sha,
        "seasons": a.seasons,
        "rows": len(df),
        "groups": feature_groups(df),
        "perfect_prog_groups": list(PERFECT_PROG),
        "inputs": {
            "labels_sha": _sha(LABELS),
            "afai_stats_1D_sha": _sha(AFAI_STATS / "stats_1D.parquet"),
            "afai_stats_3D_sha": _sha(AFAI_STATS / "stats_3D.parquet"),
        },
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    print(f"features v{FEATURE_VERSION}: {len(df)} rows, {sum(len(v) for v in manifest['groups'].values())} features")


if __name__ == "__main__":
    main()
