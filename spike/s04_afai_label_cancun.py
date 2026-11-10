"""Spike row 4: AFAI as a label, Cancún–Puerto Morelos coastal band, all of 2025.

Band: ocean pixels 1.5–10 km from the coast, 20.80–21.20°N. Daily valid share = valid band pixels /
band pixels. A day is "observed" when ≥ 20% of band pixels are valid. Daily label variants: positive if
the share of valid band pixels with AFAI > 0 is > 0, ≥ 1%, ≥ 5%, ≥ 25% or ≥ 50%, for the 1D and 3D
products (10 variants; 25% and 50% were added after the first run showed the lower thresholds give labels that
are positive on 87–99% of days). The spike reports ranges, so the rerun reports min–max over these variants.

Agreement = share of consecutive observed days (next observed day, any gap) with the same label.
Persistence BSS = 1 − BS(previous observed label) / BS(monthly climatology of the label, in-sample).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline.ingest.afai import Box
from spike.afai_bands import band_mask, open_box
from spike.common import write

BOX = Box(20.75, 21.30, -87.10, -86.65)
MIN_VALID = 0.20
THRESH = {"any": 0.0, "1pct": 0.01, "5pct": 0.05, "25pct": 0.25, "50pct": 0.50}  # 25/50% added after run 1


def daily(ds) -> pd.DataFrame:  # type: ignore[no-untyped-def]
    m = band_mask(ds, 1.5, 10, 20.80, 21.20)
    a = ds.AFAI.where(m)
    n_band = int(m.sum())
    valid = a.notnull().sum(["latitude", "longitude"]).to_series() / n_band
    pos = (a > 0).sum(["latitude", "longitude"]).to_series()
    nval = a.notnull().sum(["latitude", "longitude"]).to_series()
    return pd.DataFrame({"valid_share": valid, "pos_share": pos / nval.replace(0, np.nan)})


def metrics(d: pd.DataFrame, thr: float) -> dict[str, float]:
    obs = d[d.valid_share >= MIN_VALID].copy()
    obs["y"] = (obs.pos_share > thr).astype(float) if thr == 0 else (obs.pos_share >= thr).astype(float)
    y = obs.y.to_numpy()
    prev = y[:-1]
    nxt = y[1:]
    agree = float((prev == nxt).mean())
    clim = obs.groupby(pd.DatetimeIndex(obs.index).month).y.transform("mean").to_numpy()[1:]
    bs_p = float(((prev - nxt) ** 2).mean())
    bs_c = float(((clim - nxt) ** 2).mean())
    return {
        "n_observed_days": len(obs),
        "event_rate": float(y.mean()),
        "agreement": agree,
        "bss_persistence_vs_monthly_clim": 1 - bs_p / bs_c if bs_c > 0 else float("nan"),
    }


def main() -> None:
    per = {}
    valid_mean = {}
    for key in ("1D", "3D"):
        ds = open_box(key, BOX, "2025-01", "2025-12")
        d = daily(ds)
        valid_mean[key] = float(d.valid_share.mean())
        for name, thr in THRESH.items():
            per[f"{key}_{name}"] = metrics(d, thr)
    ag = [v["agreement"] for v in per.values()]
    bss = [v["bss_persistence_vs_monthly_clim"] for v in per.values()]
    results = [
        {"metric": "mean_daily_valid_share_1D", "spike": 0.44, "rerun": valid_mean["1D"]},
        {"metric": "consecutive_observed_agreement_min", "spike": 0.50, "rerun": min(ag)},
        {"metric": "consecutive_observed_agreement_max", "spike": 0.66, "rerun": max(ag)},
        {"metric": "persistence_BSS_vs_monthly_clim_min", "spike": -0.21, "rerun": min(bss)},
        {"metric": "persistence_BSS_vs_monthly_clim_max", "spike": -0.07, "rerun": max(bss)},
    ]
    write(
        "s04_afai_label_cancun",
        "AFAI as a label, Cancún–Puerto Morelos band, all of 2025",
        __doc__.split("\n\n", 1)[1].strip() if __doc__ else "",
        results,
        extra={"variants": per, "mean_daily_valid_share_3D": valid_mean["3D"]},
        notes=[
            "the spike's label definition was not recorded in SPEC; the variants here bracket plausible "
            "choices, so a mismatch may be a definition difference rather than a data change"
        ],
    )


if __name__ == "__main__":
    main()
