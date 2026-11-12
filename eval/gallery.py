"""Failure gallery: the 10 worst M2 misses on the test seasons (SPEC "Failure gallery").

A miss = one (site, target date) with the largest squared error of M2 (worst lead kept), distinct site-days.
Each panel shows: the AFAI 3D anomaly field the issue used (day I−1), P1 particle tracks for that issue
(re-run with the frozen configuration, trajectories kept), the hourly onshore wind before the report, and the
derived beach label (severity class only; FIU photos and free text are never shown).

Cause (one line, fixed rules applied in this order; heuristic, stated as such):
  cloud gap          valid fraction of the site's coastal AFAI band over the 7 days before issue < 0.10
  wind shift         onshore wind in the report window has the opposite sign to its mean over the previous 3 days
  label noise        the site's label differs from both its previous and next labeled day AND from the
                     majority of other sites reporting that day
  local accumulation none of the above
Outputs: outputs/failure_gallery.csv, outputs/figures/gallery/NN_<site>_<date>.png
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from eval.figures import AXIS, GRID, INK, MUTED, _style
from pipeline.sites import SITES

LOCK = Path("data/test_lock")
OUT = Path("outputs")
SEV = {0: "0 none", 1: "1 present", 2: "2 moderate (brown water or smell)", 3: "3 heavy (very brown water)"}


def pick_misses(preds: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    p = preds.assign(sqerr=(preds["M2"] - preds["event"]) ** 2)
    worst = p.sort_values("sqerr", ascending=False).drop_duplicates(["site", "date"]).head(n)
    return worst.reset_index(drop=True)


def cause(row: pd.Series, feats: pd.DataFrame, labels: pd.DataFrame, wind: pd.Series) -> str:
    if row.get("afai3d_band_valid7", np.nan) < 0.10:
        return "cloud gap"
    D = row["date"]
    win = wind[
        (wind.index > pd.Timestamp(D, tz="UTC") - pd.Timedelta(hours=12))
        & (wind.index <= pd.Timestamp(D, tz="UTC") + pd.Timedelta(hours=6))
    ].mean()
    prev = wind[
        (wind.index > pd.Timestamp(D, tz="UTC") - pd.Timedelta(days=3, hours=12))
        & (wind.index <= pd.Timestamp(D, tz="UTC") - pd.Timedelta(hours=12))
    ].mean()
    if np.sign(win) != np.sign(prev) and abs(win - prev) > 1.0:
        return "wind shift"
    s = labels[(labels.site == row["site"]) & labels.event.notna()].sort_values("date")
    before = s[s.date < D].tail(1).event
    after = s[s.date > D].head(1).event
    others = labels[(labels.date == D) & (labels.site != row["site"]) & labels.event.notna()].event
    y = row["event"]
    if (
        len(before)
        and len(after)
        and before.iloc[0] != y
        and after.iloc[0] != y
        and len(others)
        and (others.mean() >= 0.5) != bool(y)
    ):
        return "label noise"
    return "local accumulation"


def tracks(issue: pd.Timestamp, meta: dict, n: int = 300) -> tuple[np.ndarray, np.ndarray]:
    """Re-run P1 for one issue with trajectories kept (frozen config, fewer particles for plotting)."""
    from physics.arrivals import RUN_HOURS
    from physics.drift import simulate_tracks
    from physics.seed import seeds_for_issue

    seeds = seeds_for_issue(issue, n, zarr=LOCK / "afai" / "3D.zarr")
    season = issue.year
    cur = LOCK / "p1" / "forcing" / f"cur_{meta['chosen_mode']}_{season}.nc"
    wind = LOCK / "p1" / "forcing" / f"wind_{season}.nc"
    return simulate_tracks(seeds, cur, wind, meta["chosen_windage"], hours=RUN_HOURS)


def main() -> None:
    _style()
    import matplotlib.pyplot as plt

    from pipeline.geo import onshore, shore_normal_deg
    from pipeline.ingest.openmeteo import hourly_frame

    meta = json.loads((OUT / "results_val_p1_meta.json").read_text())
    preds = pd.read_parquet(LOCK / "preds_test.parquet")
    feats = pd.read_parquet(LOCK / "features" / "v1" / "features.parquet")
    labels = pd.read_parquet("data/interim/labels/site_day.parquet")
    worst = pick_misses(preds).merge(
        feats[["site", "date", "lead", "severity", "afai3d_band_valid7", "issue_date"]],
        on=["site", "date", "lead"],
        how="left",
    )
    z = xr.open_zarr(LOCK / "afai" / "3D.zarr", consolidated=False)
    gdir = OUT / "figures" / "gallery"
    gdir.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, r in worst.iterrows():
        site = next(s for s in SITES if s.id == r.site)
        w = hourly_frame(Path("data/raw/openmeteo"), "wind_hf", site.id)
        on = pd.Series(
            onshore(w.wind_speed_10m, w.wind_direction_10m, shore_normal_deg(site.lat, site.lon)), index=w.index
        )
        c = cause(r, feats, labels, on)
        fig, ax = plt.subplots(1, 3, figsize=(14, 4.4), gridspec_kw={"width_ratios": [1.1, 1.1, 1]})
        day = pd.Timestamp(r.issue_date) - pd.Timedelta(days=1)
        a = z.anom.sel(time=day, method="nearest")
        a.plot(
            ax=ax[0], cmap="Greys", vmin=-0.001, vmax=0.002, add_colorbar=True, cbar_kwargs={"label": "AFAI anomaly"}
        )
        ax[0].set_title("")  # drop xarray's automatic "time = …" title
        ax[0].plot(site.lon, site.lat, marker="*", color="#e34948", markersize=12)
        ax[0].set_aspect(1 / np.cos(np.radians(site.lat)))
        ax[0].set_title(f"AFAI 3D anomaly, {day.date()} (seed field)", loc="left", fontsize=9, color=INK)
        try:
            lon, lat = tracks(pd.Timestamp(r.issue_date), meta)
            for k in range(min(len(lon), 150)):
                ax[1].plot(lon[k], lat[k], color="#2a78d6", lw=0.4, alpha=0.5)
        except Exception as e:  # forcing missing: say so on the panel, never invent tracks
            ax[1].text(0.05, 0.5, f"tracks unavailable: {type(e).__name__}", transform=ax[1].transAxes, color=MUTED)
        ax[1].add_patch(plt.Circle((site.lon, site.lat), 5 / 111.2, fill=False, color="#e34948", lw=1.2))
        ax[1].set_xlim(site.lon - 1.2, site.lon + 1.0)
        ax[1].set_ylim(site.lat - 1.2, site.lat + 1.0)
        ax[1].set_aspect(1 / np.cos(np.radians(site.lat)))
        ax[1].set_title(
            f"P1 tracks from issue {pd.Timestamp(r.issue_date).date()} (5 km circle)", loc="left", fontsize=9, color=INK
        )
        ax[1].grid(color=GRID, lw=0.5)
        D = pd.Timestamp(r.date, tz="UTC")
        seg = on[(on.index >= D - pd.Timedelta(days=4)) & (on.index <= D + pd.Timedelta(hours=12))]
        ax[2].plot(seg.index, seg.values, color="#1baf7a", lw=1.5)
        ax[2].axhline(0, color=AXIS, lw=1)
        ax[2].axvspan(D - pd.Timedelta(hours=12), D + pd.Timedelta(hours=6), color=GRID, alpha=0.6)
        ax[2].set_title("Onshore wind at site (m/s; shaded = report window)", loc="left", fontsize=9, color=INK)
        ax[2].tick_params(axis="x", labelrotation=30, labelsize=7)
        txt = (
            f"{site.name}, {pd.Timestamp(r.date).date()}, lead {int(r.lead)} d\n"
            f"observed: {SEV.get(int(r.severity), '?')}\n"
            f"M2 {r.M2:.2f} · M1 {r.M1:.2f} · B0 {r.B0:.2f} · B1 {r.B1:.2f} · P1 {r.P1:.2f}\ncause (rule): {c}"
        )
        fig.text(0.01, 0.98, txt, va="top", fontsize=9, color=INK)
        fig.tight_layout(rect=(0, 0, 1, 0.82))
        name = f"{i + 1:02d}_{site.id}_{pd.Timestamp(r.date).date()}.png"
        fig.savefig(gdir / name, dpi=120)
        plt.close(fig)
        rows.append(
            {
                "rank": i + 1,
                "site": site.id,
                "date": str(pd.Timestamp(r.date).date()),
                "lead": int(r.lead),
                "observed_event": int(r.event),
                "severity": int(r.severity),
                "M2": r.M2,
                "M1": r.M1,
                "B0": r.B0,
                "B1": r.B1,
                "P1": r.P1,
                "cause": c,
                "figure": f"figures/gallery/{name}",
            }
        )
    pd.DataFrame(rows).to_csv(OUT / "failure_gallery.csv", index=False, float_format="%.3f")
    print(pd.DataFrame(rows)[["rank", "site", "date", "lead", "observed_event", "M2", "cause"]].to_string(index=False))


if __name__ == "__main__":
    main()
