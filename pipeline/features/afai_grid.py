"""AFAI grid processing → compressed Zarr + daily region statistics.

For each product (1D, and 3D = trailing 3-day composite of days d-2..d, verified in Phase 2 against
the 1D masks) and each season (Feb–Oct, Feb only feeds the 30-day baselines):

  background(d) = nan-median of AFAI over 0.3° blocks (20 × 20 pixels) on day d (needs ≥ 50 valid
                  pixels in the block, else the day's whole-box median)
  anom(d)       = AFAI(d) − background(d)
  detected(d)   = anom(d) > DETECT_THRESHOLD  (valid pixels only)

DETECT_THRESHOLD = 1.79e-4 is the AFAI-difference threshold of Wang & Hu (2016, Remote Sensing of
Environment 183:350–367) for Sargassum-containing pixels. It is a published constant, not tuned here.

Region statistics per day (``data/interim/afai/stats_<product>.parquet``):
  n_valid, valid_frac, det_frac (= detected / valid), mean_anom (over valid).
Regions:
  band_<site>   ocean pixels 1.5–10 km from the coast, within ±15 km alongshore of the site
  r50_<site>    ocean pixels ≥ 1.5 km from the coast within 50 km of the site (B2, SIR-style)
  offshore      10–50 km from the coast, 25.6–26.6°N (water directly off Broward)
  south         ocean, 24.4–25.6°N, 81.0–79.5°W (Florida Straits; upstream in the Florida Current)
  east          ocean, 25.4–27.2°N, 79.2–78.0°W (Bahamas edge; upstream for onshore winds)

``available_at`` for a value stamped day d = d + 1 day + 12 h (UTC), i.e. 1-day latency as the SPEC
states. Not independently verified against ERDDAP publication times (FEASIBILITY / WORKLOG).
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from pipeline.geo import grid_coast_distance
from pipeline.ingest.afai import BROWARD_UPSTREAM, DATASETS, month_range
from pipeline.sites import SITES, distance_km

DETECT_THRESHOLD = 1.79e-4
BLOCK = 20
MIN_BLOCK_VALID = 50
RAW = Path("data/raw/afai")
OUT = Path("data/interim/afai")
LATENCY = pd.Timedelta(days=1, hours=12)  # from the 00:00 UTC of day d
log = logging.getLogger("afai_grid")


def background(a: np.ndarray) -> np.ndarray:
    """Block nan-median background for a (time, lat, lon) array."""
    t, ny, nx = a.shape
    py, px = (-ny) % BLOCK, (-nx) % BLOCK
    p = np.pad(a, ((0, 0), (0, py), (0, px)), constant_values=np.nan)
    blk = p.reshape(t, (ny + py) // BLOCK, BLOCK, (nx + px) // BLOCK, BLOCK).transpose(0, 1, 3, 2, 4)
    blk = blk.reshape(t, blk.shape[1], blk.shape[2], BLOCK * BLOCK)
    nvalid = np.isfinite(blk).sum(-1)
    with np.errstate(all="ignore"):
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            med = np.nanmedian(blk, axis=-1)
            day_med = np.nanmedian(a.reshape(t, -1), axis=1)
    med = np.where(nvalid >= MIN_BLOCK_VALID, med, day_med[:, None, None])
    full = np.repeat(np.repeat(med, BLOCK, axis=1), BLOCK, axis=2)
    return full[:, :ny, :nx]


def region_masks(lat: np.ndarray, lon: np.ndarray) -> dict[str, np.ndarray]:
    dist, land = grid_coast_distance(lat, lon)
    ocean = ~land
    LON, LAT = np.meshgrid(lon, lat)
    m: dict[str, np.ndarray] = {}
    for s in SITES:
        d_site = distance_km(LAT, LON, s.lat, s.lon)
        along = np.abs(LAT - s.lat) * 111.195
        m[f"band_{s.id}"] = ocean & (dist >= 1.5) & (dist <= 10) & (along <= 15) & (s.lon - 0.05 < LON)
        m[f"r50_{s.id}"] = ocean & (dist >= 1.5) & (d_site <= 50)
    m["offshore"] = ocean & (dist > 10) & (dist <= 50) & (LAT >= 25.6) & (LAT <= 26.6) & (LON > -80.2)
    m["south"] = ocean & (LAT >= 24.4) & (LAT <= 25.6) & (LON >= -81.0) & (LON <= -79.5)
    m["east"] = ocean & (LAT >= 25.4) & (LAT <= 27.2) & (LON >= -79.2) & (LON <= -78.0)
    return m


def load_season(key: str, season: int) -> xr.Dataset:
    cache = RAW / DATASETS[key] / BROWARD_UPSTREAM.tag
    files = [cache / f"{f:%Y-%m}.nc" for f, _ in month_range(f"{season}-02", f"{season}-10")]
    missing = [p for p in files if not p.exists()]
    if missing:
        raise FileNotFoundError(f"missing AFAI months: {missing}")
    ds = xr.open_mfdataset(files, combine="by_coords").sortby("time").load()
    ds["time"] = ds.time.dt.floor("D")
    return ds


def region_stats(times: pd.DatetimeIndex, anom: np.ndarray, masks: dict[str, np.ndarray]) -> list[pd.DataFrame]:
    """Daily per-region stats (n_valid, valid_frac, det_frac, mean_anom) for an anomaly cube (time, lat, lon).
    Shared by the historical store (``process``) and the live daily job (``ops.live``)."""
    valid = np.isfinite(anom)
    det = valid & (anom > DETECT_THRESHOLD)
    out = []
    for name, mk in masks.items():
        n = int(mk.sum())
        nv = valid[:, mk].sum(1)
        nd = det[:, mk].sum(1)
        with np.errstate(all="ignore"):
            mean_anom = np.where(
                nv > 0, np.nansum(np.where(valid[:, mk], anom[:, mk], 0), 1) / np.maximum(nv, 1), np.nan
            )
        out.append(
            pd.DataFrame(
                {
                    "date": times,
                    "region": name,
                    "n_pixels": n,
                    "n_valid": nv,
                    "valid_frac": nv / max(n, 1),
                    "det_frac": np.where(nv > 0, nd / np.maximum(nv, 1), np.nan),
                    "mean_anom": mean_anom,
                }
            )
        )
    return out


def process(key: str, seasons: list[int], out: Path = OUT) -> pd.DataFrame:
    out.mkdir(parents=True, exist_ok=True)
    store = out / f"{key}.zarr"
    stats = []
    masks: dict[str, np.ndarray] | None = None
    for i, season in enumerate(seasons):
        ds = load_season(key, season)
        a = ds.AFAI.values.astype(np.float32)
        anom = (a - background(a)).astype(np.float32)
        lat, lon = ds.latitude.values, ds.longitude.values
        if masks is None:
            masks = region_masks(lat, lon)
        z = xr.Dataset(
            {"anom": (("time", "latitude", "longitude"), anom)},
            coords={"time": ds.time.values, "latitude": lat, "longitude": lon},
            attrs={"detect_threshold": DETECT_THRESHOLD, "source": DATASETS[key], "block_px": BLOCK},
        )
        z.to_zarr(store, mode="w" if i == 0 else "a", append_dim=None if i == 0 else "time", consolidated=False)
        stats.extend(region_stats(pd.DatetimeIndex(ds.time.values), anom, masks))
        log.info("%s %d: %d days", key, season, len(ds.time))
    df = pd.concat(stats, ignore_index=True)
    df["product"] = key
    df["available_at"] = df["date"].dt.tz_localize("UTC") + LATENCY
    df.to_parquet(out / f"stats_{key}.parquet", index=False)
    if masks is not None:
        np.savez_compressed(out / "region_masks.npz", **masks)  # type: ignore[arg-type]
    return df


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--products", nargs="+", default=["1D", "3D"])
    ap.add_argument(
        "--seasons", nargs="+", type=int, default=list(range(2019, 2025))
    )  # test seasons 2025–2026 only after G4
    a = ap.parse_args()
    for key in a.products:
        process(key, a.seasons)


if __name__ == "__main__":
    main()
