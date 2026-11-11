"""Drift forcing: Copernicus SMOC hourly currents + Copernicus L4 hourly winds → CF-named NetCDF for OpenDrift.

Modes (the SPEC's "with/without explicit Stokes drift"; SMOC already contains Stokes in ``utotal``):
  total      currents = utotal, vtotal  (Eulerian + tides + Stokes; windage then risks double-counting waves)
  no_stokes  currents = uo + utide, vo + vtide  (Eulerian + tides, Stokes removed)

Both drivers are analyses for historical seasons (Copernicus keeps no past forecast runs), so P1 is a
perfect-prognosis feature, FEASIBILITY §7. Downloading needs Copernicus Marine credentials.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Literal

import pandas as pd
import xarray as xr

from pipeline.ingest.copernicus import SMOC, has_credentials

Mode = Literal["total", "no_stokes"]
MODES: tuple[Mode, ...] = ("total", "no_stokes")
WIND = "cmems_obs-wind_glo_phy_my_l4_0.125deg_PT1H"  # 2007 → ~5 months behind present
WIND_NRT = "cmems_obs-wind_glo_phy_nrt_l4_0.125deg_PT1H"  # 2024-06-13 → present
DOMAIN = (22.5, 28.5, -82.5, -76.5)  # lat0, lat1, lon0, lon1: AFAI box + 0.5° margin
RAW = Path("data/raw/copernicus")


def season_window(season: int) -> tuple[str, str]:
    """Issue days run from Feb 22 (lead 7 → Mar 1) to Oct 30; seeds start the day before, runs end ≤ Nov 8."""
    return f"{season}-02-20T00:00:00", f"{season}-11-08T23:00:00"


SMOC_VARS = ["uo", "vo", "utide", "vtide", "vsdx", "vsdy", "utotal", "vtotal"]
WIND_VARS = ["eastward_wind", "northward_wind"]


def _month_chunks(start: str, end: str) -> list[tuple[str, str]]:
    a, b = pd.Timestamp(start), pd.Timestamp(end)
    out = []
    cur = a
    while cur <= b:
        nxt = (cur + pd.offsets.MonthBegin(1)).normalize()
        stop = min(b, nxt - pd.Timedelta(hours=1))
        out.append((cur.strftime("%Y-%m-%dT%H:%M:%S"), stop.strftime("%Y-%m-%dT%H:%M:%S")))
        cur = nxt
    return out


def _subset_monthly(dataset_id: str, variables: list[str], prefix: str, season: int, root: Path) -> list[Path]:
    """Whole-season subset via the ARCO *time-series* store. Measured on 2026-11-11: 30 days of SMOC over DOMAIN
    took 1,771 s this way vs 1,360 s for 2 days via the default map (geo-series) store, whose chunks are one hour
    × 512 × 2048 cells. Idempotent: an existing season file is skipped."""
    import copernicusmarine as cm

    lat0, lat1, lon0, lon1 = DOMAIN
    files = []
    # One request per season: the time-series store's chunks are 4,272 h × 16 × 8 cells, so month-sized requests
    # re-download the same ~178-day chunks (measured 2026-11-11; see WORKLOG). Kept as a list for open_mfdataset.
    for a, b in [season_window(season)]:
        dest = root / f"{prefix}_{season}.nc"
        if not dest.exists():
            tmp = f"{dest.stem}.part.nc"
            cm.subset(
                dataset_id=dataset_id,
                variables=variables,
                minimum_latitude=lat0,
                maximum_latitude=lat1,
                minimum_longitude=lon0,
                maximum_longitude=lon1,
                start_datetime=a,
                end_datetime=b,
                output_directory=str(root),
                output_filename=tmp,
                disable_progress_bar=True,
                overwrite=True,
                service="arco-time-series",
            )
            (root / tmp).rename(dest)
        files.append(dest)
    return files


def fetch_season(season: int, root: Path = RAW) -> tuple[list[Path], list[Path]]:
    """Download one season of SMOC and L4 wind over ``DOMAIN`` (idempotent, monthly files). Needs credentials."""
    if not has_credentials():
        raise PermissionError("Copernicus Marine credentials not set (see .env.example / `copernicusmarine login`)")
    root.mkdir(parents=True, exist_ok=True)
    end = season_window(season)[1]
    wind_id = WIND if date.fromisoformat(end[:10]) < date.today() - timedelta(days=150) else WIND_NRT
    return (
        _subset_monthly(SMOC, SMOC_VARS, "smoc", season, root),
        _subset_monthly(wind_id, WIND_VARS, "wind", season, root),
    )


def _cf(ds: xr.Dataset, u: xr.DataArray, v: xr.DataArray, xname: str, yname: str) -> xr.Dataset:
    if "depth" in u.dims:
        u, v = u.isel(depth=0, drop=True), v.isel(depth=0, drop=True)
    out = xr.Dataset({xname: u.astype("float32"), yname: v.astype("float32")})
    out[xname].attrs = {"standard_name": xname, "units": "m s-1"}
    out[yname].attrs = {"standard_name": yname, "units": "m s-1"}
    out = out.rename({k: n for k, n in (("latitude", "lat"), ("longitude", "lon")) if k in out.dims})
    out["lat"].attrs.update(standard_name="latitude", units="degrees_north")
    out["lon"].attrs.update(standard_name="longitude", units="degrees_east")
    return out


def currents_cf(smoc: xr.Dataset, mode: Mode) -> xr.Dataset:
    if mode == "total":
        u, v = smoc["utotal"], smoc["vtotal"]
    elif mode == "no_stokes":
        u, v = smoc["uo"] + smoc["utide"], smoc["vo"] + smoc["vtide"]
    else:
        raise ValueError(mode)
    return _cf(smoc, u, v, "x_sea_water_velocity", "y_sea_water_velocity")


def wind_cf(wind: xr.Dataset) -> xr.Dataset:
    return _cf(wind, wind["eastward_wind"], wind["northward_wind"], "x_wind", "y_wind")


def write_cf(ds: xr.Dataset, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        ds.to_netcdf(path)
    return path
