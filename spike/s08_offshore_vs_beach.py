"""Spike row 8: can satellite pixels just offshore predict the beach? Broward, 2025.

Target (day level): event day = at least 3 of the 8 sites report severity >= 2. Days are Mar–Oct 2025
days on which at least ``MIN_SITES`` sites reported (the spike's 215 days fixes this choice; see notes).

Predictors at lead L (value from day D−L, no latency adjustment, as in the spike):
  persistence = number of the 8 sites with an event on D−L (NaN if no site reported that day)
  AFAI        = mean AFAI 1D over ocean pixels 3–8 km from the coast, 25.95–26.37°N (the Broward coast)
AUC = Mann–Whitney ROC-AUC over days where both target and predictor exist.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline.ingest.afai import BROWARD_UPSTREAM
from spike.afai_bands import band_mask, open_box
from spike.common import auc, load_site_days, write

LEADS = (1, 2, 3, 5, 7)
SPIKE_PERSIST = {1: 0.76, 2: 0.73, 3: 0.70, 5: 0.65, 7: 0.67}
SPIKE_AFAI = {1: 0.52, 2: 0.58, 3: 0.58, 5: 0.62, 7: 0.57}
LAT0, LAT1 = 25.95, 26.37


def day_table(sd: pd.DataFrame, min_sites: int) -> pd.DataFrame:
    s = sd[(sd.season == 2025) & sd.in_season & sd.event.notna()]
    g = s.groupby("date").agg(n_sites=("site", "nunique"), n_events=("event", "sum"))
    g["n_events"] = g["n_events"].astype(float)
    idx = pd.date_range("2025-03-01", "2025-10-31", freq="D")
    g = g.reindex(idx)
    g["target"] = (g.n_events >= 3).astype(float).where(g.n_sites >= min_sites)
    return g


def main() -> None:
    sd = load_site_days()
    counts = {k: int(day_table(sd, k).target.notna().sum()) for k in range(1, 9)}
    # choose the reporting threshold whose day count is closest to the spike's 215 days
    min_sites = min(counts, key=lambda k: abs(counts[k] - 215))
    g = day_table(sd, min_sites)
    ds = open_box("1D", BROWARD_UPSTREAM, "2025-02", "2025-10")
    m = band_mask(ds, 3, 8, LAT0, LAT1)
    afai = ds.AFAI.where(m).mean(["latitude", "longitude"]).to_series()
    afai.index = pd.DatetimeIndex(afai.index).tz_localize(None)
    afai = afai.reindex(pd.date_range("2025-02-01", "2025-10-31", freq="D"))
    events_any = sd[(sd.season == 2025) & sd.event.notna()].groupby("date").event.sum().astype(float)
    events_any = events_any.reindex(pd.date_range("2025-02-01", "2025-10-31", freq="D"))
    results = []
    per = {}
    for L in LEADS:
        pers = events_any.shift(L).reindex(g.index)
        af = afai.shift(L).reindex(g.index)
        a_p, a_a = auc(g.target.values, pers.values), auc(g.target.values, af.values)
        per[L] = {
            "persistence_auc": a_p,
            "afai_auc": a_a,
            "n_persistence": int((g.target.notna() & pers.notna()).sum()),
            "n_afai": int((g.target.notna() & af.notna()).sum()),
        }
        results.append({"metric": f"persistence_AUC_lead{L}", "spike": SPIKE_PERSIST[L], "rerun": a_p})
    for L in LEADS:
        results.append({"metric": f"AFAI_3_8km_AUC_lead{L}", "spike": SPIKE_AFAI[L], "rerun": per[L]["afai_auc"]})
    results.append({"metric": "n_days", "spike": 215, "rerun": int(g.target.notna().sum())})
    results.append({"metric": "event_day_rate", "spike": None, "rerun": float(g.target.mean())})
    write(
        "s08_offshore_vs_beach",
        "Can satellite pixels just offshore predict the beach? 2025, event = 3+ of 8 sites",
        (__doc__ or "").split("\n\n", 1)[1].strip(),
        results,
        touches_test_seasons=True,
        extra={
            "min_sites_reporting": min_sites,
            "days_by_min_sites": counts,
            "per_lead": per,
            "afai_band_pixels": int(m.sum()),
        },
        notes=[
            "The spike did not record how 215 days were chosen; MIN_SITES is set to the reporting threshold "
            "whose 2025 day count is closest to 215 (not to any score).",
            "Fixed-rule predictors only; nothing fitted. Rerun of pre-registered spike numbers on a test season.",
        ],
    )
    _ = np


if __name__ == "__main__":
    main()
