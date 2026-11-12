"""Spike row 3: artifact check at a control coast (Progreso, Gulf side), June 2025.

Band: ocean pixels 1.5–10 km from the coast between 89.80°W and 89.50°W. Positive pixel = AFAI > 0.
"""

from __future__ import annotations

from pipeline.ingest.afai import Box
from spike.afai_bands import band_mask, open_box
from spike.common import write

BOX = Box(21.20, 21.50, -89.90, -89.40)


def main() -> None:
    ds = open_box("1D", BOX, "2025-06", "2025-06")
    m = band_mask(ds, 1.5, 10, 21.20, 21.50, -89.80, -89.50)
    a = ds.AFAI.where(m)
    n_valid = int(a.notnull().sum())
    results = [
        {"metric": "positive_pixels_(AFAI>0)", "spike": 0, "rerun": int((a > 0).sum())},
        {"metric": "mean_AFAI", "spike": -0.0018, "rerun": float(a.mean())},
    ]
    write(
        "s03_progreso_control",
        "Artifact check at a control coast (Progreso), June 2025",
        "AFAI 1D, June 2025, ocean pixels 1.5–10 km offshore, 89.80–89.50°W. Positive = AFAI > 0.",
        results,
        extra={
            "valid_pixel_days": n_valid,
            "band_pixels": int(m.sum()),
            "p99_AFAI": float(a.quantile(0.99, skipna=True)),
        },
        notes=[
            "'positive' in the spike is undefined; AFAI > 0 is the literal reading. The mean AFAI comparison "
            "uses the absolute 0.03 tolerance, which is loose for values of order 1e-3."
        ],
    )


if __name__ == "__main__":
    main()
