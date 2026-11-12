"""Live inputs and feature rows for one issue day I (Phase 6 daily job).

Each live input is written in the same on-disk layout as the historical cache, under ``data/live/<I>/``.
Feature rows are then built by the same functions as the frozen feature store (``pipeline.features.build``).

Live differences, all by construction:
- Target-day drivers (winds, waves, currents) and P1 forcing are true forecasts issued around I (Open-Meteo GFS /
  Météo-France; Copernicus SMOC forecast; Open-Meteo GFS winds on a 0.5° grid for OpenDrift). In training they were
  analyses ("perfect-prog"), so live skill is expected to be at or below the test-season upper bound.
- Lead-L forecast winds (``wind_fc``) are the same live forecast (it *is* a lead-L forecast).
- Beach reports come from the first 2,000 FIU entries (newest first), which covers the last 7 days.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests
import xarray as xr

from pipeline.features import build as fb
from pipeline.features.afai_grid import background, region_masks, region_stats
from pipeline.ingest import afai, fiu, tides
from pipeline.ingest.openmeteo import FEEDS, LEADS, MARINE_LON_OFFSET, USER_AGENT
from pipeline.labels import fiu_labels
from pipeline.sites import SITES

LIVE = Path("data/live")
LAT_GRID = np.arange(22.5, 28.51, 0.5)
LON_GRID = np.arange(-82.5, -76.49, 0.5)
log = logging.getLogger("live")


@dataclass
class LiveInputs:
    issue: pd.Timestamp
    root: Path
    labels: pd.DataFrame
    afai_dir: Path
    om_root: Path
    seed_anom: xr.DataArray | None
    status: dict[str, Any]


def _get(url: str, params: dict[str, Any], tries: int = 4) -> dict[str, Any]:
    last: Exception | None = None
    for k in range(tries):
        try:
            r = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=120)
            r.raise_for_status()
            out: dict[str, Any] = r.json()
            return out
        except requests.RequestException as e:
            last = e
            time.sleep(5 * 2**k)
    raise RuntimeError(f"GET {url} failed: {last}")


# ----------------------------------------------------------------------------------------------- FIU
def fiu_recent(root: Path, pages: int = 2) -> tuple[pd.DataFrame, str]:
    d = root / "fiu"
    d.mkdir(parents=True, exist_ok=True)
    newest = ""
    for p in range(1, pages + 1):
        payload = fiu.fetch_page(p)
        newest = newest or payload["meta"]["newest"]
        (d / f"page_{p:03d}.json").write_text(json.dumps(payload))
        time.sleep(13)
    reports = fiu_labels.label_reports(fiu_labels.parse_reports(fiu.load_entries(d)))
    return fiu_labels.site_days(reports), newest


# ----------------------------------------------------------------------------------------------- AFAI
def afai_recent(issue: pd.Timestamp, root: Path) -> tuple[Path, xr.DataArray | None, str]:
    """AFAI 1D and 3D for [I−45, I−1]: region stats (same code as the store) and the 3D anomaly of I−1 for seeding."""
    out = root / "afai"
    out.mkdir(parents=True, exist_ok=True)
    t0, t1 = (issue - pd.Timedelta(days=45)).date(), (issue - pd.Timedelta(days=1)).date()
    seed: xr.DataArray | None = None
    last_step = ""
    for key in ("1D", "3D"):
        nc = out / f"{key}.nc"
        rec = afai.fetch(afai.DATASETS[key], t0, t1, afai.BROWARD_UPSTREAM, nc)
        if rec["status"] != "ok":
            raise RuntimeError(f"AFAI {key}: no data for {t0}..{t1}")
        ds = xr.open_dataset(nc).load()
        ds["time"] = ds.time.dt.floor("D")
        ds = ds.sel(time=~pd.DatetimeIndex(ds.time.values).duplicated())
        a = ds.AFAI.values.astype(np.float32)
        anom = (a - background(a)).astype(np.float32)
        masks = region_masks(ds.latitude.values, ds.longitude.values)
        st = pd.concat(region_stats(pd.DatetimeIndex(ds.time.values), anom, masks), ignore_index=True)
        st["product"] = key
        st["available_at"] = st["date"].dt.tz_localize("UTC") + pd.Timedelta(days=1, hours=12)
        st.to_parquet(out / f"stats_{key}.parquet", index=False)
        if key == "3D":
            last_step = str(pd.DatetimeIndex(ds.time.values).max().date())
            want = issue.normalize() - pd.Timedelta(days=1)
            if want in pd.DatetimeIndex(ds.time.values):
                i = list(pd.DatetimeIndex(ds.time.values)).index(want)
                seed = xr.DataArray(
                    anom[i],
                    coords={"latitude": ds.latitude.values, "longitude": ds.longitude.values},
                    dims=("latitude", "longitude"),
                )
    return out, seed, last_step


# ----------------------------------------------------------------------------------------------- Open-Meteo
def openmeteo_live(issue: pd.Timestamp, root: Path) -> tuple[Path, dict[str, str]]:
    """Forecast-API equivalents of the historical feeds, written as feed/site/live.json (hourly_frame layout)."""
    om = root / "openmeteo"
    first: dict[str, str] = {}
    urls = {
        "marine_currents": "https://marine-api.open-meteo.com/v1/marine",
        "marine_waves": "https://marine-api.open-meteo.com/v1/marine",
        "wind_hf": "https://api.open-meteo.com/v1/forecast",
    }
    for s in SITES:
        for name, url in urls.items():
            feed = FEEDS[name]
            params: dict[str, Any] = {
                "latitude": s.lat,
                "longitude": round(s.lon + feed.lon_offset, 4),
                "hourly": ",".join(feed.hourly),
                "past_days": 4,
                "forecast_days": 9,
                "timezone": "UTC",
                **dict(feed.params),
            }
            payload = _get(url, params)
            d = om / name / s.id
            d.mkdir(parents=True, exist_ok=True)
            (d / "live.json").write_text(json.dumps(payload))
            first.setdefault(name, payload["hourly"]["time"][-1])
            if name == "wind_hf":  # live lead-L forecast winds are this same forecast
                h = payload["hourly"]
                prev = {"time": h["time"]}
                for L in LEADS:
                    prev[f"wind_speed_10m_previous_day{L}"] = h["wind_speed_10m"]
                    prev[f"wind_direction_10m_previous_day{L}"] = h["wind_direction_10m"]
                dp = om / "wind_prev" / s.id
                dp.mkdir(parents=True, exist_ok=True)
                (dp / "live.json").write_text(json.dumps({**payload, "hourly": prev}))
            time.sleep(0.5)
    _ = MARINE_LON_OFFSET
    return om, first


def wind_grid(issue: pd.Timestamp, root: Path) -> Path:
    """GFS 10 m wind on a 0.5° grid over the drift domain (169 points, one multi-location call) → CF NetCDF."""
    LON, LAT = np.meshgrid(LON_GRID, LAT_GRID)
    params: dict[str, Any] = {
        "latitude": ",".join(f"{v:.2f}" for v in LAT.ravel()),
        "longitude": ",".join(f"{v:.2f}" for v in LON.ravel()),
        "hourly": "wind_speed_10m,wind_direction_10m",
        "models": "gfs_seamless",
        "wind_speed_unit": "ms",
        "past_days": 2,
        "forecast_days": 9,
        "timezone": "UTC",
    }
    r = requests.get(
        "https://api.open-meteo.com/v1/forecast", params=params, headers={"User-Agent": USER_AGENT}, timeout=300
    )
    r.raise_for_status()
    locs = r.json()
    t = pd.to_datetime(locs[0]["hourly"]["time"])
    sp = np.stack([np.asarray(x["hourly"]["wind_speed_10m"], float) for x in locs]).reshape(*LAT.shape, len(t))
    dr = np.stack([np.asarray(x["hourly"]["wind_direction_10m"], float) for x in locs]).reshape(*LAT.shape, len(t))
    u = -sp * np.sin(np.radians(dr))  # meteorological "from" direction → eastward component
    v = -sp * np.cos(np.radians(dr))
    ds = xr.Dataset(
        {
            "x_wind": (("time", "lat", "lon"), np.moveaxis(u, -1, 0).astype("float32")),
            "y_wind": (("time", "lat", "lon"), np.moveaxis(v, -1, 0).astype("float32")),
        },
        coords={"time": t, "lat": LAT_GRID, "lon": LON_GRID},
    )
    for k in ("x_wind", "y_wind"):
        ds[k].attrs = {"standard_name": k, "units": "m s-1"}
    ds["lat"].attrs.update(standard_name="latitude", units="degrees_north")
    ds["lon"].attrs.update(standard_name="longitude", units="degrees_east")
    path = root / "forcing" / "wind_grid.nc"
    path.parent.mkdir(parents=True, exist_ok=True)
    ds.to_netcdf(path)
    return path


def smoc_forecast(issue: pd.Timestamp, root: Path) -> Path:
    """SMOC currents (uo + utide, the frozen ``no_stokes`` mode) for seed time → last lead window end."""
    import copernicusmarine as cm

    from physics.forcing import DOMAIN, currents_cf
    from pipeline.ingest.copernicus import SMOC

    lat0, lat1, lon0, lon1 = DOMAIN
    raw = root / "forcing" / "smoc.nc"
    raw.parent.mkdir(parents=True, exist_ok=True)
    start = (issue.normalize() - pd.Timedelta(days=1) + pd.Timedelta(hours=18)).strftime("%Y-%m-%dT%H:%M:%S")
    end = (issue.normalize() + pd.Timedelta(days=7, hours=13)).strftime("%Y-%m-%dT%H:%M:%S")
    cm.subset(
        dataset_id=SMOC,
        variables=["uo", "vo", "utide", "vtide"],
        minimum_latitude=lat0,
        maximum_latitude=lat1,
        minimum_longitude=lon0,
        maximum_longitude=lon1,
        start_datetime=start,
        end_datetime=end,
        output_directory=str(raw.parent),
        output_filename=raw.name,
        overwrite=True,
        disable_progress_bar=True,
        service="arco-time-series",
    )
    cf = currents_cf(xr.open_dataset(raw), "no_stokes")
    path = root / "forcing" / "cur_no_stokes.nc"
    cf.to_netcdf(path)
    return path


# ----------------------------------------------------------------------------------------------- features
def skeleton_live(issue: pd.Timestamp) -> pd.DataFrame:
    rows = []
    for s in SITES:
        for L in LEADS:
            D = issue.normalize() + pd.Timedelta(days=L)
            rows.append({"site": s.id, "date": D, "season": D.year, "lead": L, "issue_date": issue.normalize()})
    df = pd.DataFrame(rows)
    df["issue_time"] = df["issue_date"].dt.tz_localize("UTC") + pd.Timedelta(hours=fb.ISSUE_HOUR)
    return df


def build_rows(inp: LiveInputs) -> pd.DataFrame:
    for y in sorted({inp.issue.year, (inp.issue + pd.Timedelta(days=8)).year}):
        tides.fetch_year(y, fb.TIDE_ROOT)
    df = skeleton_live(inp.issue)
    df = fb.add_calendar(df)
    df = fb.add_tide(df)
    df = fb.add_persist(df, inp.labels)
    df = fb.add_afai(df, "1D", inp.afai_dir)
    df = fb.add_afai(df, "3D", inp.afai_dir)
    df = fb.add_openmeteo(df, inp.om_root)
    return df


def gather(issue: pd.Timestamp, root: Path = LIVE) -> LiveInputs:
    r = root / f"{issue:%Y-%m-%d}"
    r.mkdir(parents=True, exist_ok=True)
    status: dict[str, Any] = {}
    labels, newest = fiu_recent(r)
    status["fiu_newest_entry"] = newest
    afai_dir, seed, last_afai = afai_recent(issue, r)
    status["afai_last_step"] = last_afai
    om_root, last_om = openmeteo_live(issue, r)
    status["openmeteo_last_hour"] = last_om
    return LiveInputs(issue, r, labels, afai_dir, om_root, seed, status)


_ = (date, timedelta)
