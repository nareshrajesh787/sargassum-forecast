"""Spike row 9: Open-Meteo currents and winds at Broward — a live 10-day current forecast, cached currents
for June 2022 and cached archived (historical-forecast) winds for 2022."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import requests

from pipeline.ingest.openmeteo import FEEDS, USER_AGENT, hourly_frame
from pipeline.sites import SITES
from spike.common import write

ROOT = Path("data/raw/openmeteo")


def main() -> None:
    site = SITES[2]  # The Palms
    feed = FEEDS["marine_currents"]
    params: dict[str, Any] = {
        "latitude": site.lat,
        "longitude": round(site.lon + feed.lon_offset, 4),
        "hourly": "ocean_current_velocity",
        "forecast_days": 10,
        "timezone": "UTC",
        **dict(feed.params),
    }
    r = requests.get(feed.url, params=params, headers={"User-Agent": USER_AGENT}, timeout=60)
    r.raise_for_status()
    fc = [v for v in r.json()["hourly"]["ocean_current_velocity"] if v is not None]
    cur = hourly_frame(ROOT, "marine_currents", site.id)
    june22 = cur.loc["2022-06-01":"2022-06-30", "ocean_current_velocity"]
    wind = hourly_frame(ROOT, "wind_hf", site.id).loc["2022-01-01":"2022-12-31", "wind_speed_10m"]
    results = [
        {"metric": "forecast_current_hours_returned_(10_days)", "spike": 240, "rerun": len(fc)},
        {"metric": "june_2022_current_non_null_share", "spike": 1.0, "rerun": float(june22.notna().mean())},
        {"metric": "2022_archived_wind_non_null_share", "spike": 1.0, "rerun": float(wind.notna().mean())},
    ]
    write(
        "s09_openmeteo",
        "Open-Meteo currents and winds at Broward",
        "The spike reported these as 'returned' (yes/no); encoded here as 240 forecast hours and 100% non-null.",
        results,
        notes=[f"site: {site.name}", "no key used"],
    )


if __name__ == "__main__":
    main()
