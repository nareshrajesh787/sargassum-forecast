"""Open-Meteo adapter: point currents, waves (Marine API) and winds (Historical Forecast and
Previous Runs APIs) for each Broward site.

Feeds (all hourly, UTC):
  marine_currents  Marine API, model ``meteofrance_currents`` (Météo-France SMOC): current velocity and
                   direction, plus SST.
  marine_waves     Marine API, model ``meteofrance_wave`` (MFWAM): wave height, direction, period.
  wind_hf          Historical Forecast API, model ``gfs_seamless``: 10 m wind. This is a *stitched
                   short-lead* forecast series (each hour comes from the most recent run), close to an
                   analysis. It is not a lead-L forecast.
  wind_prev        Previous Runs API, ``gfs_seamless``: 10 m wind as forecast 1, 2, 3, 5 and 7 days
                   earlier (``*_previous_dayN``). This is the leakage-safe lead-L wind and exists only
                   from 2024-01-19 (measured in Phase 1).

Marine requests use a point ``MARINE_LON_OFFSET`` east of the beach with ``cell_selection=sea``; Open-Meteo
then snaps to the nearest sea cell, which can be several km away. The snapped coordinate is stored with every pull.

Terms: CC BY 4.0, non-commercial use, < 10,000 calls/day. Long requests count as several calls
(weight ≈ max(1, n_vars/10) × max(1, n_days/14)). ``estimate_weight`` tracks the daily budget.
Credit: Open-Meteo.com; Météo-France (SMOC, MFWAM); NOAA NCEP (GFS).

Usage:  uv run python -m pipeline.ingest.openmeteo --start 2022-01-01 --end 2026-10-31
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import requests

from pipeline.sites import SITES, Site

USER_AGENT = "sargassum-forecast/0.1 (research; github.com/nareshrajesh787/sargassum-forecast)"
DAILY_CALL_BUDGET = 10_000
LEADS = (1, 2, 3, 5, 7)
# Marine feeds are queried 0.025° (~2.5 km) east of the beach point: from the beach point itself,
# ``cell_selection=sea`` snapped 3 sites to a cell west of the shoreline that returns only nulls (Phase 1).
MARINE_LON_OFFSET = 0.025
log = logging.getLogger("openmeteo")


@dataclass(frozen=True)
class Feed:
    name: str
    url: str
    hourly: tuple[str, ...]
    params: tuple[tuple[str, str], ...]
    lon_offset: float = 0.0  # degrees east of the beach point (marine feeds query offshore)


FEEDS: dict[str, Feed] = {
    "marine_currents": Feed(
        "marine_currents",
        "https://marine-api.open-meteo.com/v1/marine",
        ("ocean_current_velocity", "ocean_current_direction", "sea_surface_temperature"),
        (("models", "meteofrance_currents"), ("cell_selection", "sea")),
        MARINE_LON_OFFSET,
    ),
    "marine_waves": Feed(
        "marine_waves",
        "https://marine-api.open-meteo.com/v1/marine",
        ("wave_height", "wave_direction", "wave_period"),
        (("models", "meteofrance_wave"), ("cell_selection", "sea")),
        MARINE_LON_OFFSET,
    ),
    "wind_hf": Feed(
        "wind_hf",
        "https://historical-forecast-api.open-meteo.com/v1/forecast",
        ("wind_speed_10m", "wind_direction_10m"),
        (("models", "gfs_seamless"), ("wind_speed_unit", "ms")),
    ),
    "wind_prev": Feed(
        "wind_prev",
        "https://previous-runs-api.open-meteo.com/v1/forecast",
        tuple(f"{v}_previous_day{d}" for d in LEADS for v in ("wind_speed_10m", "wind_direction_10m")),
        (("models", "gfs_seamless"), ("wind_speed_unit", "ms")),
    ),
}


def estimate_weight(n_vars: int, start: date, end: date) -> float:
    days = (end - start).days + 1
    return max(1.0, n_vars / 10) * max(1.0, days / 14)


def fetch(feed: Feed, site: Site, start: date, end: date, retries: int = 5) -> dict[str, Any]:
    params: dict[str, str | float] = {
        "latitude": site.lat,
        "longitude": round(site.lon + feed.lon_offset, 4),
        "hourly": ",".join(feed.hourly),
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "timezone": "UTC",
        **dict(feed.params),
    }
    last: Exception | str | None = None
    for attempt in range(retries):
        try:
            r = requests.get(feed.url, params=params, headers={"User-Agent": USER_AGENT}, timeout=180)
        except requests.RequestException as e:
            last = e
            time.sleep(5 * 2**attempt)
            continue
        if r.status_code == 429:
            last = "HTTP 429"
            time.sleep(60)
            continue
        if r.status_code != 200:
            last = f"HTTP {r.status_code}: {r.text[:200]}"
            if r.status_code == 400:  # bad request will not fix itself
                break
            time.sleep(5 * 2**attempt)
            continue
        payload: dict[str, Any] = r.json()
        return payload
    raise RuntimeError(f"Open-Meteo {feed.name} {site.id} {start}..{end}: {last}")


def year_chunks(start: date, end: date) -> list[tuple[date, date]]:
    out = []
    y = start.year
    while y <= end.year:
        a = max(start, date(y, 1, 1))
        b = min(end, date(y, 12, 31))
        out.append((a, b))
        y += 1
    return out


def pull(feeds: list[str], start: date, end: date, root: Path, pause_s: float = 1.0) -> dict[str, Any]:
    """Pull every feed × site × year chunk not already cached. Returns a run summary."""
    summary: dict[str, Any] = {"calls_weighted": 0.0, "requests": 0, "seconds": 0.0, "items": []}
    for fname in feeds:
        feed = FEEDS[fname]
        for site in SITES:
            for a, b in year_chunks(start, end):
                dest = root / feed.name / site.id / f"{a:%Y%m%d}_{b:%Y%m%d}.json"
                if dest.exists():
                    continue
                w = estimate_weight(len(feed.hourly), a, b)
                if summary["calls_weighted"] + w > DAILY_CALL_BUDGET * 0.8:
                    raise RuntimeError("would exceed 80% of Open-Meteo's daily call budget; resume tomorrow")
                t0 = time.monotonic()
                payload = fetch(feed, site, a, b)
                secs = time.monotonic() - t0
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(json.dumps(payload))
                nonnull = {
                    v: sum(x is not None for x in payload["hourly"][v]) / max(1, len(payload["hourly"][v]))
                    for v in feed.hourly
                }
                if any(share == 0 for share in nonnull.values()) and feed.name != "wind_prev":
                    log.warning(
                        "%s %s %s..%s: all-null variables %s",
                        feed.name,
                        site.id,
                        a,
                        b,
                        [v for v, sh in nonnull.items() if sh == 0],
                    )
                summary["calls_weighted"] += w
                summary["requests"] += 1
                summary["seconds"] += secs
                summary["items"].append(
                    {
                        "feed": feed.name,
                        "site": site.id,
                        "start": a.isoformat(),
                        "end": b.isoformat(),
                        "grid_lat": payload.get("latitude"),
                        "grid_lon": payload.get("longitude"),
                        "seconds": round(secs, 2),
                        "weight": round(w, 1),
                        "non_null_share": {k: round(v, 4) for k, v in nonnull.items()},
                    }
                )
                log.info(
                    "%s %s %s..%s %.1fs grid=(%s,%s)",
                    feed.name,
                    site.id,
                    a,
                    b,
                    secs,
                    payload.get("latitude"),
                    payload.get("longitude"),
                )
                time.sleep(pause_s)
    return summary


def hourly_frame(root: Path, feed: str, site_id: str) -> Any:
    """Concatenate cached chunks for one feed/site into a DataFrame indexed by UTC hour."""
    import pandas as pd

    frames = []
    for p in sorted((root / feed / site_id).glob("*.json")):
        d = json.loads(p.read_text())
        h = d["hourly"]
        f = pd.DataFrame(h)
        f["time"] = pd.to_datetime(f["time"], utc=True)
        f["grid_lat"], f["grid_lon"] = d.get("latitude"), d.get("longitude")
        frames.append(f.set_index("time"))
    if not frames:
        raise FileNotFoundError(f"no cached {feed} for {site_id}")
    out = pd.concat(frames).sort_index()
    return out[~out.index.duplicated(keep="last")]


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--feeds", nargs="+", default=list(FEEDS), choices=list(FEEDS))
    ap.add_argument("--start", type=date.fromisoformat, default=date(2022, 1, 1))
    ap.add_argument("--end", type=date.fromisoformat, default=date(2026, 10, 31))
    ap.add_argument("--root", type=Path, default=Path("data/raw/openmeteo"))
    a = ap.parse_args()
    s = pull(a.feeds, a.start, a.end, a.root)
    a.root.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    (a.root / f"_run_{stamp}.json").write_text(json.dumps(s, indent=1))
    print(f"requests={s['requests']} weighted_calls≈{math.ceil(s['calls_weighted'])} seconds={s['seconds']:.0f}")


if __name__ == "__main__":
    main()
