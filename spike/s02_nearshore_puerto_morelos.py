"""Spike row 2: near-shore AFAI availability at Puerto Morelos, June 2025.

Transect: the AFAI row nearest 20.85°N, running east from the coast. "First ocean pixel" = the first
pixel east of the Natural Earth coastline. Counts = days in June 2025 with a valid (non-NaN) AFAI value.
"""

from __future__ import annotations

import numpy as np

from pipeline.ingest.afai import Box
from spike.afai_bands import open_box, valid_fraction_by_distance
from spike.common import write

BOX = Box(20.75, 21.30, -87.10, -86.65)
LAT = 20.85


def main() -> None:
    ds = open_box("1D", BOX, "2025-06", "2025-06")
    row = ds.sel(latitude=LAT, method="nearest")
    ocean = row.where(~row.land, drop=True)
    ocean = ocean.sortby("longitude")
    valid_days = ocean.AFAI.notnull().sum("time").values
    dist = ocean.coast_km.values
    n_days = int(ds.sizes["time"])
    first = int(valid_days[0])
    band = (dist >= 3) & (dist <= 15)
    results = [
        {"metric": "june_2025_days_in_product", "spike": 30, "rerun": n_days},
        {
            "metric": "first_ocean_pixel_valid_days (first pixel off the NE coastline)",
            "spike": 3,
            "rerun": first,
        },
        {
            "metric": "first_ocean_pixel_valid_days (first pixel >= 1.5 km out)",
            "spike": 3,
            "rerun": int(valid_days[dist >= 1.5][0]),
        },
        {"metric": "pixels_3_15km_valid_days_min", "spike": 9, "rerun": int(valid_days[band].min())},
        {"metric": "pixels_3_15km_valid_days_max", "spike": 14, "rerun": int(valid_days[band].max())},
    ]
    vf = valid_fraction_by_distance(ds, [0, 1.5, 3, 5, 10, 15, 30])
    write(
        "s02_nearshore_puerto_morelos",
        "Near-shore data availability, Puerto Morelos, June 2025",
        f"AFAI 1D row at {float(row.latitude):.4f}N east of the coast; first ocean pixel at "
        f"{float(ocean.longitude[0]):.3f}E, {dist[0]:.2f} km from the Natural Earth coastline.",
        results,
        extra={
            "valid_share_by_coast_distance_june2025_box": vf,
            "transect_km_and_valid_days": [
                [round(float(d), 2), int(v)] for d, v in zip(dist[:20], valid_days[:20], strict=True)
            ],
        },
        notes=["Natural Earth 10 m coastline is good to ~0.5–1 km, so 'first ocean pixel' is approximate"],
    )
    _ = np


if __name__ == "__main__":
    main()
