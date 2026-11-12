"""NOAA AOML / USF AFAI adapter (ERDDAP griddap, netCDF).

Pulls ``noaa_aoml_atlantic_oceanwatch_AFAI_1D`` (or ``_3D``/``_7D``) month by month for a lat/lon
box and caches each month as ``data/raw/afai/<dataset>/<box>/<YYYY-MM>.nc``. Idempotent: months
already cached (and readable) are skipped. Each request is logged with bytes, values and seconds to
``<cache>/_throughput.csv`` so feasibility numbers come from real pulls.

AFAI is a reflectance-unit index; NaN = cloud/glint/land/no data. The 1D product's time stamps are
12:00Z of the observation day; it is published with about one day of latency, so a value for day D is
treated as available at D+1 12:00Z (the conservative ``available_at`` used downstream).

Credit: NOAA AOML Atlantic OceanWatch; USF Optical Oceanography Lab (Hu et al. 2015).

Usage:  uv run python -m pipeline.ingest.afai --dataset 1D --start 2024-03 --end 2024-10
"""

from __future__ import annotations

import argparse
import csv
import logging
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np
import requests
import xarray as xr

ERDDAP = "https://cwcgom.aoml.noaa.gov/erddap/griddap/"
DATASETS = {
    "1D": "noaa_aoml_atlantic_oceanwatch_AFAI_1D",
    "3D": "noaa_aoml_atlantic_oceanwatch_AFAI_3D",
    "7D": "noaa_aoml_atlantic_oceanwatch_AFAI_7D",
}
USER_AGENT = "sargassum-forecast/0.1 (research; github.com/nareshrajesh787/sargassum-forecast)"
LATENCY = timedelta(days=1)  # conservative publication latency for available_at
log = logging.getLogger("afai")


@dataclass(frozen=True)
class Box:
    lat0: float
    lat1: float
    lon0: float
    lon1: float
    stride: int = 1

    @property
    def tag(self) -> str:
        return f"{self.lat0:g}_{self.lat1:g}N_{self.lon0:g}_{self.lon1:g}E_s{self.stride}"


BROWARD_UPSTREAM = Box(23.0, 28.0, -82.0, -78.0)  # SPEC "Volume": Broward plus upstream corridor


def griddap_url(dataset: str, t0: date, t1: date, box: Box) -> str:
    s = box.stride
    return (
        f"{ERDDAP}{dataset}.nc?AFAI"
        f"%5B({t0.isoformat()}T00:00:00Z):1:({t1.isoformat()}T23:59:59Z)%5D"
        f"%5B({box.lat0:g}):{s}:({box.lat1:g})%5D"
        f"%5B({box.lon0:g}):{s}:({box.lon1:g})%5D"
    )


def month_range(start: str, end: str) -> list[tuple[date, date]]:
    """Inclusive list of (first_day, last_day) for months ``YYYY-MM`` .. ``YYYY-MM``."""
    y, m = map(int, start.split("-"))
    ye, me = map(int, end.split("-"))
    out = []
    while (y, m) <= (ye, me):
        first = date(y, m, 1)
        nxt = date(y + (m == 12), m % 12 + 1, 1)
        out.append((first, nxt - timedelta(days=1)))
        y, m = nxt.year, nxt.month
    return out


def _readable(p: Path) -> bool:
    try:
        with xr.open_dataset(p) as ds:
            return "AFAI" in ds
    except Exception:
        return False


def fetch(dataset: str, t0: date, t1: date, box: Box, dest: Path, retries: int = 4, timeout: int = 900) -> dict:
    """Download one request to ``dest``. Returns a throughput record. ERDDAP returns 404 when no time
    steps fall in the window (e.g. a month with no data); that is recorded, not raised."""
    url = griddap_url(dataset, t0, t1, box)
    last: Exception | str | None = None
    for attempt in range(retries):
        t_start = time.monotonic()
        try:
            r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
        except requests.RequestException as e:
            last = e
            time.sleep(10 * 2**attempt)
            continue
        secs = time.monotonic() - t_start
        if r.status_code == 404:
            return {"status": "no_data", "seconds": secs, "bytes": 0, "values": 0, "steps": 0}
        if r.status_code != 200 or r.content[:3] not in (b"CDF", b"\x89HD"):
            last = f"HTTP {r.status_code}: {r.text[:200]!r}"
            time.sleep(10 * 2**attempt)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".part")
        tmp.write_bytes(r.content)
        tmp.rename(dest)
        trim(dest, t0, t1)
        with xr.open_dataset(dest) as ds:
            sizes = dict(ds.AFAI.sizes)
        values = sizes["time"] * sizes["latitude"] * sizes["longitude"]
        return {
            "status": "ok",
            "seconds": secs,
            "bytes": len(r.content),
            "values": values,
            "steps": sizes["time"],
        }
    raise RuntimeError(f"AFAI fetch failed {dataset} {t0}..{t1}: {last}")


def trim(path: Path, t0: date, t1: date) -> int:
    """Drop time steps outside [t0, t1]. ERDDAP snaps request bounds to the *nearest* existing time, so a
    month whose last (or first) day is missing returns a step from the neighbouring month (seen for
    2024-07-01 inside 2024-06.nc). Returns the number of steps removed."""
    with xr.open_dataset(path) as ds:
        days = ds.time.dt.floor("D")
        keep = (days >= np.datetime64(t0)) & (days <= np.datetime64(t1))
        n_drop = int((~keep).sum())
        if n_drop == 0:
            return 0
        sub = None if int(keep.sum()) == 0 else ds.isel(time=np.flatnonzero(keep.values)).load()
    if sub is None:
        path.unlink()
    else:
        tmp = path.with_suffix(".trim")
        sub.to_netcdf(tmp)
        tmp.replace(path)
    log.info("trimmed %d out-of-window step(s) from %s", n_drop, path)
    return n_drop


def trim_cache(root: Path) -> int:
    """Apply ``trim`` to every cached ``YYYY-MM.nc`` under ``root`` (one-off repair of older pulls)."""
    n = 0
    for p in sorted(root.glob("*/*/????-??.nc")):
        first, last = month_range(p.stem, p.stem)[0]
        n += trim(p, first, last)
    return n


def pull(key: str, start: str, end: str, box: Box, root: Path, months: tuple[int, ...] | None = None) -> list[dict]:
    dataset = DATASETS[key]
    cache = root / dataset / box.tag
    tlog = cache / "_throughput.csv"
    recs = []
    for first, last in month_range(start, end):
        if months and first.month not in months:
            continue
        dest = cache / f"{first:%Y-%m}.nc"
        if dest.exists() and _readable(dest):
            log.info("cached %s", dest)
            continue
        rec = fetch(dataset, first, last, box, dest)
        rec |= {
            "dataset": dataset,
            "box": box.tag,
            "month": f"{first:%Y-%m}",
            "at_utc": datetime.now(UTC).isoformat(),
        }
        log.info(
            "%s %s: %s %d steps %.1fs %.0f values/s",
            dataset,
            rec["month"],
            rec["status"],
            rec["steps"],
            rec["seconds"],
            rec["values"] / rec["seconds"] if rec["seconds"] else 0,
        )
        new = not tlog.exists()
        cache.mkdir(parents=True, exist_ok=True)
        with tlog.open("a", newline="") as f:
            w = csv.DictWriter(
                f,
                fieldnames=[
                    "at_utc",
                    "dataset",
                    "box",
                    "month",
                    "status",
                    "steps",
                    "values",
                    "bytes",
                    "seconds",
                ],
            )
            if new:
                w.writeheader()
            w.writerow({k: rec[k] for k in w.fieldnames})
        recs.append(rec)
    return recs


def open_cached(key: str, box: Box, root: Path, start: str, end: str) -> xr.Dataset:
    """Open cached months [start, end] as one dataset (time-sorted)."""
    cache = root / DATASETS[key] / box.tag
    files = [cache / f"{f:%Y-%m}.nc" for f, _ in month_range(start, end)]
    files = [p for p in files if p.exists()]
    if not files:
        raise FileNotFoundError(f"no cached AFAI months in {cache} for {start}..{end}")
    return xr.open_mfdataset(files, combine="by_coords").sortby("time")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", choices=sorted(DATASETS), default="1D")
    ap.add_argument("--start", required=True, help="YYYY-MM")
    ap.add_argument("--end", required=True, help="YYYY-MM")
    ap.add_argument("--season-only", action="store_true", help="only March–October")
    ap.add_argument("--box", type=float, nargs=4, metavar=("LAT0", "LAT1", "LON0", "LON1"))
    ap.add_argument("--stride", type=int, default=1)
    ap.add_argument("--root", type=Path, default=Path("data/raw/afai"))
    a = ap.parse_args()
    b = BROWARD_UPSTREAM
    lat0, lat1, lon0, lon1 = a.box if a.box else (b.lat0, b.lat1, b.lon0, b.lon1)
    box = Box(lat0, lat1, lon0, lon1, stride=a.stride)
    pull(a.dataset, a.start, a.end, box, a.root, months=tuple(range(3, 11)) if a.season_only else None)


if __name__ == "__main__":
    main()
