"""P1 Lagrangian drift with OpenDrift ``OceanDrift`` (SPEC "Physics details").

One run per (issue day, current mode). Every run carries all windage groups (``WINDAGES``: 0–3% of the
10 m wind) as separate particle groups, because OpenDrift applies ``wind_drift_factor`` per particle. Particles
start at 18:00 UTC on day I−1 from AFAI seeds (``physics.seed``) and run 186 h, which covers every lead to
target-day 12:00 UTC. ``general:coastline_action = stranding`` (GSHHG landmask via roaring-landmask), and
stranded particles count as arrivals at their stranding point. Horizontal diffusivity is a fixed 10 m²/s,
not tuned.

Each run's arrival table is cached at ``data/interim/p1/<mode>/<YYYY-MM-DD>.parquet`` (small), so a
sweep is resumable and the daily job only runs today's issue.

Usage:
  uv run python -m physics.drift --season 2024 --modes total no_stokes        # validation sweep
  uv run python -m physics.drift --season 2023 --modes total --windages 0.02  # chosen config, train seasons
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from physics.arrivals import LEADS, RUN_HOURS, SEED_HOUR_UTC, arrival_table
from physics.forcing import MODES, Mode, currents_cf, fetch_season, wind_cf, write_cf
from physics.seed import Seeds, seeds_for_issue
from pipeline.sites import SITES

WINDAGES = (0.0, 0.01, 0.02, 0.03)
N_PER_GROUP = 2000
DIFFUSIVITY = 10.0
OUT = Path("data/interim/p1")
log = logging.getLogger("drift")


def simulate(
    seeds: Seeds,
    current_nc: Path,
    wind_nc: Path,
    windages: tuple[float, ...] = WINDAGES,
    n_per_group: int = N_PER_GROUP,
    hours: int = RUN_HOURS,
) -> pd.DataFrame:
    """Run OpenDrift for one issue and return its arrival table (empty frame if nothing to seed)."""
    from opendrift.models.oceandrift import OceanDrift
    from opendrift.readers import reader_netCDF_CF_generic

    if len(seeds.lon) == 0:
        return pd.DataFrame()
    t0 = (seeds.field_day + pd.Timedelta(hours=SEED_HOUR_UTC)).to_pydatetime()
    k = len(windages)
    idx = np.arange(min(len(seeds.lon), n_per_group))
    lon = np.tile(seeds.lon[idx], k)
    lat = np.tile(seeds.lat[idx], k)
    wdf = np.repeat(np.asarray(windages, float), len(idx))
    o = OceanDrift(loglevel=50)
    o.add_reader([reader_netCDF_CF_generic.Reader(str(current_nc)), reader_netCDF_CF_generic.Reader(str(wind_nc))])
    o.set_config("general:coastline_action", "stranding")
    o.set_config("environment:constant:horizontal_diffusivity", DIFFUSIVITY)
    o.set_config("drift:stokes_drift", False)  # Stokes handled by the current mode
    o.seed_elements(lon=lon, lat=lat, time=t0, wind_drift_factor=wdf, z=0)
    o.run(duration=timedelta(hours=hours), time_step=timedelta(hours=1), time_step_output=timedelta(hours=1))
    r = o.result
    rlon = r["lon"].values
    rlat = r["lat"].values
    if rlon.shape[0] != len(wdf):  # (time, trajectory) layout
        rlon, rlat = rlon.T, rlat.T
    hrs = (pd.DatetimeIndex(r["time"].values) - pd.Timestamp(t0)).total_seconds().to_numpy() / 3600
    w = r["wind_drift_factor"].values
    w = np.nanmax(w, axis=1) if w.ndim == 2 and w.shape[0] == len(wdf) else (np.nanmax(w, axis=0) if w.ndim == 2 else w)
    return arrival_table(rlon, rlat, hrs, np.round(np.asarray(w, dtype=np.float64), 4), seeds.total_weight)


def zero_table(windages: tuple[float, ...]) -> pd.DataFrame:
    rows = [
        {
            "site": s.id,
            "lead": L,
            "windage": float(w),
            "n_particles": 0,
            "arr_window": 0,
            "arr_cum": 0,
            "idx_window": 0.0,
            "idx_cum": 0.0,
        }
        for s in SITES
        for L in LEADS
        for w in windages
    ]
    return pd.DataFrame(rows)


def issue_dates(season: int) -> pd.DatetimeIndex:
    return pd.date_range(f"{season}-02-22", f"{season}-10-30", freq="D")


def run_season(season: int, modes: tuple[Mode, ...], windages: tuple[float, ...], out: Path = OUT) -> dict:
    cur_raw, wind_raw = fetch_season(season)
    smoc = xr.open_mfdataset(cur_raw, combine="by_coords")
    wind = xr.open_mfdataset(wind_raw, combine="by_coords")
    wind_nc = write_cf(wind_cf(wind), out / "forcing" / f"wind_{season}.nc")
    stats = {"runs": 0, "seconds": 0.0, "empty": 0}
    for mode in modes:
        cur_nc = write_cf(currents_cf(smoc, mode), out / "forcing" / f"cur_{mode}_{season}.nc")
        for issue in issue_dates(season):
            dest = out / mode / f"{issue:%Y-%m-%d}.parquet"
            if dest.exists():
                continue
            seeds = seeds_for_issue(issue, N_PER_GROUP)
            t = time.monotonic()
            tab = simulate(seeds, cur_nc, wind_nc, windages)
            secs = time.monotonic() - t
            if tab.empty:
                stats["empty"] += 1
                tab = zero_table(windages)  # no detections → explicit zero arrivals, not missing rows
            tab = tab.assign(
                issue_date=issue, mode=mode, total_weight=seeds.total_weight, n_pixels=seeds.n_pixels, seconds=secs
            )
            dest.parent.mkdir(parents=True, exist_ok=True)
            tab.to_parquet(dest, index=False)
            stats["runs"] += 1
            stats["seconds"] += secs
            log.info("%s %s: %d pixels, %.1fs", mode, issue.date(), seeds.n_pixels, secs)
    return stats


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--modes", nargs="+", default=list(MODES), choices=list(MODES))
    ap.add_argument("--windages", nargs="+", type=float, default=list(WINDAGES))
    a = ap.parse_args()
    if a.season in (2025, 2026):
        raise SystemExit("test seasons are locked until Gate 4")
    s = run_season(a.season, tuple(a.modes), tuple(a.windages))
    print(json.dumps(s))


if __name__ == "__main__":
    main()
