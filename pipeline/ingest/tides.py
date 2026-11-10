"""NOAA CO-OPS tide predictions (high/low) for South Port Everglades (station 8722956).

Predictions are deterministic harmonic forecasts, so they are known at any issue time
(``available_at`` = -inf in the feature store). Public domain; credit NOAA CO-OPS.

Usage:  uv run python -m pipeline.ingest.tides --start 2019-01-01 --end 2026-12-31
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests

API = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
STATION = "8722956"  # South Port Everglades, 26.0817N 80.1167W (central Broward)
USER_AGENT = "sargassum-forecast/0.1 (research; github.com/nareshrajesh787/sargassum-forecast)"


def fetch_year(year: int, root: Path) -> Path:
    dest = root / STATION / f"hilo_{year}.json"
    if dest.exists():
        return dest
    params: dict[str, str] = {
        "product": "predictions",
        "station": STATION,
        "begin_date": f"{year}0101",
        "end_date": f"{year}1231",
        "datum": "MLLW",
        "interval": "hilo",
        "units": "metric",
        "time_zone": "gmt",
        "format": "json",
        "application": "sargassum-forecast",
    }
    r = requests.get(API, params=params, headers={"User-Agent": USER_AGENT}, timeout=120)
    r.raise_for_status()
    payload = r.json()
    if "predictions" not in payload:
        raise RuntimeError(f"CO-OPS {year}: {payload}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload))
    return dest


def load(root: Path) -> pd.DataFrame:
    rows = []
    for p in sorted((root / STATION).glob("hilo_*.json")):
        rows += json.loads(p.read_text())["predictions"]
    df = pd.DataFrame(rows)
    df["time"] = pd.to_datetime(df["t"], utc=True)
    df["height_m"] = df["v"].astype(float)
    return df[["time", "height_m", "type"]].sort_values("time").reset_index(drop=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=date.fromisoformat, default=date(2019, 1, 1))
    ap.add_argument("--end", type=date.fromisoformat, default=date(2026, 12, 31))
    ap.add_argument("--root", type=Path, default=Path("data/raw/tides"))
    a = ap.parse_args()
    for y in range(a.start.year, a.end.year + 1):
        fetch_year(y, a.root)
        time.sleep(1)
    print(f"tides: {len(load(a.root))} high/low predictions")


if __name__ == "__main__":
    main()
