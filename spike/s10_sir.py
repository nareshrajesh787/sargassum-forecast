"""Spike row 10: SIR archive — today's KMZ size; dated KMZ for June 15 2022–2025; earliest available day."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import requests

from spike.common import write

BASE = "https://cwcgom.aoml.noaa.gov/SIR/KMZ/sargassum_risk_{d}.kmz"


def status(d: date) -> tuple[int, int]:
    r = requests.get(BASE.format(d=d.strftime("%Y%m%d")), timeout=60)
    return r.status_code, len(r.content)


def earliest(lo: date, hi: date) -> date:
    """Binary search for the first available day, assuming availability is contiguous up to `hi`."""
    while (hi - lo).days > 1:
        mid = lo + (hi - lo) // 2
        if requests.head(BASE.format(d=mid.strftime("%Y%m%d")), timeout=60).status_code == 200:
            hi = mid
        else:
            lo = mid
    return hi


def main() -> None:
    today = datetime.now(UTC).date()
    latest, (code, size) = today, status(today)
    back = 0
    while code != 200 and back < 5:
        back += 1
        latest = today - timedelta(days=back)
        code, size = status(latest)
    june = {y: status(date(y, 6, 15))[0] for y in (2022, 2023, 2024, 2025)}
    first = earliest(date(2020, 1, 1), latest)
    results: list[dict[str, Any]] = [
        {"metric": "latest_kmz_MB", "spike": 1.56, "rerun": size / 1e6},
        {
            "metric": "june15_2022_2025_http404_count",
            "spike": 4,
            "rerun": sum(v == 404 for v in june.values()),
        },
        {"metric": "earliest_available_kmz_date", "spike": "none (no history)", "rerun": first.isoformat()},
    ]
    write(
        "s10_sir",
        "SIR archive",
        "HTTP GET of KMZ/sargassum_risk_YYYYMMDD.kmz; earliest day by binary search between 2020-01-01 and the "
        "latest available day (assumes contiguous availability; spot-checked weekly in Phase 0, 0 gaps).",
        results,
        notes=[f"latest available day: {latest}", f"June 15 statuses: {june}"],
    )


if __name__ == "__main__":
    main()
