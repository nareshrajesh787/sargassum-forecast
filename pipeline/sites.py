"""The 8 fixed FIU Sargassum Watch sites in Broward County, FL.

Coordinates are the median GPS of reports whose site name matches the alias pattern, from the
FIU snapshot fetched 2026-11-10 (interquartile spread ≈ 0.0002°, i.e. ~20 m, for 7 of 8 sites;
Sea Ranch Lakes ≈ 0.002°). Ordered south → north.

``aliases`` are regexes over the lower-cased, whitespace-normalised reported site name. They were
written by reading every name variant with ≥ 1 report; see ``pipeline/labels/fiu_labels.py``
for how name and GPS are combined.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Site:
    id: str
    name: str
    lat: float
    lon: float
    aliases: str


SITES: tuple[Site, ...] = (
    Site(
        "bougainvillea_terrace",
        "Bougainvillea Terrace",
        26.0036,
        -80.1157,
        r"^bou?gai?n?vill?e?a?\s*(?:terr?(?:ace)?|ter)?\.?$",
    ),
    Site("mj_state_park", "MJ State Park", 26.0604, -80.1114, r"^mj'?s?\s*(?:state\.?\s*)?park"),
    Site(
        "the_palms",
        "The Palms",
        26.1562,
        -80.0996,
        r"^the\.?\s*palms?\b|^palms$|^thepalms|^fort lauderdale beach - the palms",
    ),
    Site(
        "commercial_pier",
        "Commercial Pier",
        26.1893,
        -80.0946,
        r"^(?:the\s+)?comm?er?i?c?i?al\s*(?:pier|peir|peer)",
    ),
    Site("sea_ranch_lakes", "Sea Ranch Lakes", 26.2004, -80.0933, r"^sea\.?\s*(?:ranch|lakes\s*ranch)"),
    Site(
        "atlantic_pier",
        "Atlantic Pier",
        26.2354,
        -80.0879,
        r"^at?l?an?tic\.?\s*pier|^pompano beach - atlantic pier",
    ),
    Site(
        "hillsboro_mile_1173",
        "1173 Hillsboro Mile",
        26.2963,
        -80.0774,
        r"^1173|^hillsboro\s*(?:mile|squares?)$",
    ),
    Site("county_line", "County Line", 26.3209, -80.0744, r"county\s*line"),
)
SITE_IDS = tuple(s.id for s in SITES)


def distance_km(lat: np.ndarray, lon: np.ndarray, lat0: float, lon0: float) -> np.ndarray:
    """Equirectangular distance in km (accurate to <0.1% at these scales)."""
    lat = np.asarray(lat, dtype=float)
    lon = np.asarray(lon, dtype=float)
    return np.hypot((lat - lat0) * 111.195, (lon - lon0) * 111.195 * np.cos(np.radians(lat0)))
