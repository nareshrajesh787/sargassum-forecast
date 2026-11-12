"""Spike row 1: AFAI 1-day product metadata (coverage, steps, grid) from the live ERDDAP info page."""

from __future__ import annotations

import csv
import io
from datetime import UTC, date, datetime
from typing import Any

import requests

from pipeline.ingest.afai import DATASETS, ERDDAP
from spike.common import write


def info(dataset: str) -> dict[str, str]:
    url = ERDDAP.replace("griddap/", "info/") + f"{dataset}/index.csv"
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    out = {}
    for row in csv.DictReader(io.StringIO(r.text)):
        key = f"{row['Variable Name']}.{row['Attribute Name']}" if row["Attribute Name"] else row["Variable Name"]
        out[key] = row["Value"]
    return out


def main() -> None:
    m = info(DATASETS["1D"])
    n_time = int(m["time"].split("nValues=")[1].split(",")[0])
    start = m["NC_GLOBAL.time_coverage_start"][:10]
    end = m["NC_GLOBAL.time_coverage_end"][:10]
    today = datetime.now(UTC).date()
    latency = (today - date.fromisoformat(end)).days
    span_days = (date.fromisoformat(end) - date.fromisoformat(start)).days + 1
    results: list[dict[str, Any]] = [
        {"metric": "time_coverage_start", "spike": "2016-06-18", "rerun": start},
        {"metric": "time_coverage_end (as of run date)", "spike": "2026-11-09", "rerun": end},
        {"metric": "latency_days (run date - last step)", "spike": 1, "rerun": latency},
        {"metric": "n_daily_steps", "spike": 3545, "rerun": n_time},
        {"metric": "share_of_calendar_days_with_a_step", "spike": None, "rerun": n_time / span_days},
        {
            "metric": "lon_resolution_deg",
            "spike": 0.015,
            "rerun": float(m["NC_GLOBAL.geospatial_lon_resolution"]),
        },
        {"metric": "lat_min", "spike": 0.0, "rerun": float(m["NC_GLOBAL.geospatial_lat_min"])},
        {"metric": "lat_max", "spike": 38.0, "rerun": float(m["NC_GLOBAL.geospatial_lat_max"])},
        {"metric": "lon_min", "spike": -98.0, "rerun": float(m["NC_GLOBAL.geospatial_lon_min"])},
        {"metric": "lon_max", "spike": -38.0, "rerun": float(m["NC_GLOBAL.geospatial_lon_max"])},
    ]
    write(
        "s01_afai_metadata",
        "AFAI 1-day product metadata",
        "ERDDAP info/index.csv for noaa_aoml_atlantic_oceanwatch_AFAI_1D, read on the run date. "
        "time_coverage_end and n_daily_steps change daily, so they match the spike only on 2026-11-10.",
        results,
        notes=[f"license: {m['NC_GLOBAL.license']}", f"run date (UTC): {today}"],
    )


if __name__ == "__main__":
    main()
