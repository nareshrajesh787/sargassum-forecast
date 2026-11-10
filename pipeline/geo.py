"""Coastline geometry: distance-to-coast for grid points.

Uses Natural Earth 10 m land polygons (public domain; nominal 1:10M scale, so coastline position
is good to roughly 0.5–1 km). Good enough for the 1.5–10 km and 3–8 km offshore bands in the spike;
Phase 2 may swap in a finer coastline if the band edges matter.

Distances use a local equirectangular projection centred on the query box (error < 0.5% over a few
hundred km at these latitudes).
"""

from __future__ import annotations

import io
import zipfile
from functools import lru_cache
from pathlib import Path

import numpy as np
import requests
import shapefile  # pyshp
import shapely
from shapely.geometry import box as sbox
from shapely.geometry import shape

NE_URL = "https://naciscdn.org/naturalearth/10m/physical/ne_10m_land.zip"
NE_DIR = Path("data/raw/naturalearth")
KM_PER_DEG = 111.195


def _ensure_ne(root: Path = NE_DIR) -> Path:
    shp = root / "ne_10m_land.shp"
    if not shp.exists():
        root.mkdir(parents=True, exist_ok=True)
        r = requests.get(NE_URL, timeout=120)
        r.raise_for_status()
        zipfile.ZipFile(io.BytesIO(r.content)).extractall(root)
    return shp


@lru_cache(maxsize=8)
def land_in_box(lat0: float, lat1: float, lon0: float, lon1: float, pad: float = 0.5) -> shapely.Geometry:
    """Union of Natural Earth land polygons intersecting the padded box (lon/lat degrees)."""
    rd = shapefile.Reader(str(_ensure_ne()))
    b = sbox(lon0 - pad, lat0 - pad, lon1 + pad, lat1 + pad)
    geoms = [shape(s.__geo_interface__) for s in rd.shapes()]
    hits = [g.intersection(b) for g in geoms if g.intersects(b)]
    return shapely.union_all(hits) if hits else shapely.Polygon()


def coast_distance_km(lat: np.ndarray, lon: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return (distance to the coastline in km, is_land) for arrays of points."""
    lat = np.asarray(lat, dtype=float)
    lon = np.asarray(lon, dtype=float)
    lat0, lat1, lon0, lon1 = float(lat.min()), float(lat.max()), float(lon.min()), float(lon.max())
    land = land_in_box(round(lat0, 3), round(lat1, 3), round(lon0, 3), round(lon1, 3))
    latc = (lat0 + lat1) / 2
    kx, ky = KM_PER_DEG * np.cos(np.radians(latc)), KM_PER_DEG
    land_km = shapely.transform(land, lambda xy: np.column_stack([xy[:, 0] * kx, xy[:, 1] * ky]))
    pts = shapely.points(lon.ravel() * kx, lat.ravel() * ky)
    is_land = shapely.contains(land_km, pts)
    dist = shapely.distance(land_km.boundary, pts)
    return dist.reshape(lat.shape), is_land.reshape(lat.shape)


def grid_coast_distance(lats: np.ndarray, lons: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Distance-to-coast (km) and land mask on a lat × lon grid."""
    LON, LAT = np.meshgrid(np.asarray(lons, float), np.asarray(lats, float))
    return coast_distance_km(LAT, LON)
