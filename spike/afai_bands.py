"""AFAI helpers for spike scripts: open a cached box and attach distance-to-coast."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import xarray as xr

from pipeline.geo import grid_coast_distance
from pipeline.ingest.afai import Box, open_cached

ROOT = Path("data/raw/afai")


def open_box(key: str, box: Box, start: str, end: str) -> xr.Dataset:
    ds = open_cached(key, box, ROOT, start, end).load()
    dist, land = grid_coast_distance(ds.latitude.values, ds.longitude.values)
    ds["coast_km"] = (("latitude", "longitude"), dist)
    ds["land"] = (("latitude", "longitude"), land)
    ds["time"] = ds.time.dt.floor("D")
    return ds


def band_mask(
    ds: xr.Dataset, dmin: float, dmax: float, lat0: float, lat1: float, lon0: float = -180, lon1: float = 180
) -> xr.DataArray:
    m = (~ds.land) & (ds.coast_km >= dmin) & (ds.coast_km <= dmax)
    m = m & (ds.latitude >= lat0) & (ds.latitude <= lat1) & (ds.longitude >= lon0) & (ds.longitude <= lon1)
    return m


def valid_fraction_by_distance(ds: xr.Dataset, edges: list[float]) -> dict[str, float]:
    valid = ds.AFAI.notnull().mean("time")
    out = {}
    for a, b in zip(edges[:-1], edges[1:], strict=True):
        m = (~ds.land) & (ds.coast_km >= a) & (ds.coast_km < b)
        out[f"{a:g}-{b:g}km"] = float(valid.where(m).mean()) if bool(m.any()) else float("nan")
    return out


_ = np
