"""Arrival index per site and lead (SPEC P1: "arrivals counted within 5 km of each site, per lead").

Times are hours since the seed time, which is 18:00 UTC on day I−1 (MODIS afternoon passes). A
particle "arrives" at a site the first hour it is within ``RADIUS_KM`` of the site. A particle that strands on
land within the radius counts at its stranding hour (its last valid position).

Lead window for target day D = I + L: the 24 h before the morning report, (D−1 12:00, D 12:00] UTC, i.e.
hours (24·L − 6, 24·L + 18] after the seed. ``cum`` counts every first arrival up to the window end.
Index = arrivals / particles in the windage group × total seeded weight.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline.sites import SITES, distance_km

RADIUS_KM = 5.0
SEED_HOUR_UTC = 18  # on day I−1
LEADS = (1, 2, 3, 5, 7)
RUN_HOURS = 24 * max(LEADS) + 18  # 186 h: seed (I−1 18:00) → D_max 12:00


def lead_window(lead: int) -> tuple[int, int]:
    """(exclusive start, inclusive end) in hours after the seed time."""
    return 24 * lead - 6, 24 * lead + 18


def first_arrival_hours(lon: np.ndarray, lat: np.ndarray, hours: np.ndarray) -> dict[str, np.ndarray]:
    """``lon``/``lat``: (particles, times) with NaN after deactivation. Returns per site the first hour each
    particle is within the radius (NaN = never), using each particle's last valid position for stranded ones
    (they are already in that array as the last non-NaN entry)."""
    out: dict[str, np.ndarray] = {}
    for s in SITES:
        d = distance_km(lat, lon, s.lat, s.lon)
        inside = d <= RADIUS_KM  # NaN compares False
        any_in = inside.any(axis=1)
        first = np.where(any_in, hours[np.argmax(inside, axis=1)], np.nan)
        out[s.id] = first.astype(float)
    return out


def arrival_table(
    lon: np.ndarray, lat: np.ndarray, hours: np.ndarray, windage: np.ndarray, total_weight: float
) -> pd.DataFrame:
    """Rows: site × lead × windage with window and cumulative arrival counts and the weighted index."""
    first = first_arrival_hours(lon, lat, hours)
    rows = []
    for w in np.unique(windage):
        g = windage == w
        n = int(g.sum())
        for site, fh in first.items():
            f = fh[g]
            for L in LEADS:
                a, b = lead_window(L)
                win = int(((f > a) & (f <= b)).sum())
                cum = int((f <= b).sum())
                rows.append(
                    {
                        "site": site,
                        "lead": L,
                        "windage": float(w),
                        "n_particles": n,
                        "arr_window": win,
                        "arr_cum": cum,
                        "idx_window": win / n * total_weight if n else 0.0,
                        "idx_cum": cum / n * total_weight if n else 0.0,
                    }
                )
    return pd.DataFrame(rows)
