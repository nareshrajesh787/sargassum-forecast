"""Particle seeding from AFAI detections (SPEC P1: "seeded from AFAI detections, weighted by AFAI above background").

For issue day I the seed field is the 3D product (trailing composite of days I−3..I−1) on day I−1, the most
recent field available at the issue time (1-day latency). Seeded pixels: anomaly > ``DETECT_THRESHOLD``
(Wang & Hu 2016) and ≥ ``MIN_COAST_KM`` from the coast. Coastal-band detection rates are biased high
(Phase 2, WORKLOG), and particles that close to shore would 'arrive' trivially.

``n`` particles are drawn with probability ∝ (anomaly − threshold) and jittered uniformly within their pixel.
Each particle stands for ``total_weight / n`` units, so the arrival index scales with the amount of detected
sargassum, not only with its geometry.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from pipeline.features.afai_grid import DETECT_THRESHOLD
from pipeline.geo import grid_coast_distance

MIN_COAST_KM = 3.0
ZARR = Path("data/interim/afai/3D.zarr")


@dataclass
class Seeds:
    lon: np.ndarray
    lat: np.ndarray
    total_weight: float
    n_pixels: int
    field_day: pd.Timestamp


@lru_cache(maxsize=2)
def _coast(lat_key: tuple[float, ...], lon_key: tuple[float, ...]) -> tuple[np.ndarray, np.ndarray]:
    return grid_coast_distance(np.array(lat_key), np.array(lon_key))


def seeds_from_field(
    anom: np.ndarray,
    lat: np.ndarray,
    lon: np.ndarray,
    n: int,
    rng: np.random.Generator,
    field_day: pd.Timestamp,
    coast_km: np.ndarray,
    land: np.ndarray,
) -> Seeds:
    ok = np.isfinite(anom) & (anom > DETECT_THRESHOLD) & ~land & (coast_km >= MIN_COAST_KM)
    iy, ix = np.nonzero(ok)
    if len(iy) == 0:
        return Seeds(np.array([]), np.array([]), 0.0, 0, field_day)
    w = (anom[iy, ix] - DETECT_THRESHOLD).astype(float)
    pick = rng.choice(len(iy), size=n, replace=True, p=w / w.sum())
    dlat = float(np.abs(np.diff(lat[:2]))[0]) if len(lat) > 1 else 0.015
    dlon = float(np.abs(np.diff(lon[:2]))[0]) if len(lon) > 1 else 0.015
    la = lat[iy[pick]] + rng.uniform(-dlat / 2, dlat / 2, n)
    lo = lon[ix[pick]] + rng.uniform(-dlon / 2, dlon / 2, n)
    return Seeds(lo, la, float(w.sum()), int(len(iy)), field_day)


def seeds_for_issue(issue_date: pd.Timestamp, n: int, zarr: Path = ZARR) -> Seeds:
    """Seeds for issue day I from the 3D field of day I−1 (deterministic RNG keyed on the issue date)."""
    day = pd.Timestamp(issue_date).normalize() - pd.Timedelta(days=1)
    ds = xr.open_zarr(zarr, consolidated=False)
    if day not in pd.DatetimeIndex(ds.time.values):
        return Seeds(np.array([]), np.array([]), 0.0, 0, day)
    a = ds.anom.sel(time=day).values
    lat, lon = ds.latitude.values, ds.longitude.values
    coast_km, land = _coast(tuple(map(float, lat)), tuple(map(float, lon)))
    rng = np.random.default_rng(int(day.strftime("%Y%m%d")))
    return seeds_from_field(a, lat, lon, n, rng, day, coast_km, land)
