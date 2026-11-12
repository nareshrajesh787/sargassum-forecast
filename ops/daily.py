"""Daily job (SPEC "Daily job"): ingest → P1 → M2 → freeze → score matured → publish static API → staleness alarm.

  uv run python -m ops.daily [--date YYYY-MM-DD] [--no-p1]

1. Gather live inputs for issue day I (``ops.live``) and build feature rows with the frozen-store code.
2. P1: OpenDrift with the frozen configuration (no Stokes, 2% windage), SMOC forecast currents and GFS wind grid.
   Seeds come from the AFAI 3D field of I−1. Drift overlay positions are kept for the map.
3. Predict with the frozen bundle (``models/artifacts/forecast_bundle_v1.pkl``). Served probability = M2 (the SPEC's
   user-facing model), with the empirical 2025–2026 80% interval (``ops.intervals``). Climatology B1 and the
   issue-time M2_fc are published alongside for comparison.
4. Freeze ``outputs/forecasts/YYYY-MM-DD.json`` (append-only: an existing file is never rewritten) with model
   version and
   input hashes.
5. Score every frozen forecast whose target day now has a beach report → ``outputs/track_record_items.csv``
   (append-only) and ``outputs/track_record.json``.
6. Publish the static API to ``web/public/api/v1/``.
7. Staleness: write ``outputs/ops/status.json``; under GitHub Actions (``GITHUB_ACTIONS=true``), open an issue if
   any input
   is more than 3 days stale.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ops import bundle as B
from ops.intervals import lookup
from ops.live import LiveInputs, build_rows, gather, smoc_forecast, wind_grid
from pipeline.sites import SITES

OUT = Path("outputs")  # read: committed tables (test results, interval table)
WOUT = OUT  # write: track record, status (redirected by --scratch)
FORECASTS = OUT / "forecasts"
API = Path("web/public/api/v1")
STALE_DAYS = 3
SEASON_MONTHS = range(3, 11)
ATTRIBUTION = (
    "Beach observations: FIU Sargassum Watch (Marine Macroalgae Research Lab). Satellite AFAI: NOAA AOML "
    "Atlantic OceanWatch / USF Optical Oceanography Lab. Currents: E.U. Copernicus Marine Service "
    "Information. Winds, waves: Open-Meteo.com (Météo-France, NOAA GFS). Tides: NOAA CO-OPS."
)


def disclaimer() -> str:
    """Built from ``outputs/results_test.csv`` so the served text never hard-codes a number (CLAUDE.md rule 3)."""
    t = pd.read_csv(OUT / "results_test.csv", dtype={"lead": str, "season": str})
    r = t[(t.season == "2025-2026") & (t.lead == "all") & (t.model == "M2")].iloc[0]
    return (
        f"Experimental research forecast, not a warning system. On the 2025–2026 test seasons the served model (M2) "
        f"had Brier skill {r.bss_B1:+.3f} [{r.bss_B1_lo:+.3f}, {r.bss_B1_hi:+.3f}] versus climatology (negative = "
        "worse than climatology). See the track record and methods."
    )


log = logging.getLogger("daily")


def _sha_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16] if p.exists() else ""


def _sha_dir(d: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(d.rglob("*")):
        if p.is_file():
            h.update(p.name.encode())
            h.update(p.read_bytes())
    return h.hexdigest()[:16]


# ---------------------------------------------------------------------------------------------- P1
def run_p1(inp: LiveInputs, bundle: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any], str]:
    from physics.arrivals import RUN_HOURS, lead_window
    from physics.drift import simulate, simulate_tracks
    from physics.seed import _coast, seeds_from_field

    if inp.seed_anom is None or inp.seed_day is None:
        raise RuntimeError("no AFAI 3D field available")
    # frozen config seeds from I−1; if that field is not yet published, seed from the newest older field and let the
    # particles drift the extra days, shifting the arrival clock so lead windows still end on the right target days
    offset_h = int((inp.issue.normalize() - pd.Timedelta(days=1) - inp.seed_day.normalize()).days) * 24
    cur = smoc_forecast(inp.issue, inp.root, inp.seed_day)
    wind = wind_grid(inp.issue, inp.root, past_days=2 + offset_h // 24)
    a = inp.seed_anom
    lat, lon = a.latitude.values, a.longitude.values
    coast, land = _coast(tuple(map(float, lat)), tuple(map(float, lon)))
    day = inp.seed_day.normalize()
    seeds = seeds_from_field(
        a.values, lat, lon, 2000, np.random.default_rng(int(day.strftime("%Y%m%d"))), day, coast, land
    )
    w = float(bundle["p1"]["chosen_windage"])
    tab = simulate(seeds, cur, wind, windages=(w,), n_per_group=2000, hours=RUN_HOURS + offset_h, hour_offset=offset_h)
    if tab.empty:
        from physics.drift import zero_table

        tab = zero_table((w,))
    # drift overlay: particle positions at the end of each lead window (300 particles)
    feats: list[dict[str, Any]] = []
    if len(seeds.lon):
        lon_t, lat_t = simulate_tracks(seeds, cur, wind, w, hours=RUN_HOURS + offset_h)
        for L in sorted(tab["lead"].unique()):
            h = min(lead_window(int(L))[1] + offset_h, lon_t.shape[1] - 1)
            pts = [
                [round(float(x), 4), round(float(y), 4)]
                for x, y in zip(lon_t[:300, h], lat_t[:300, h], strict=True)
                if np.isfinite(x) and np.isfinite(y)
            ]
            feats.append(
                {
                    "type": "Feature",
                    "properties": {"lead": int(L)},
                    "geometry": {"type": "MultiPoint", "coordinates": pts},
                }
            )
    overlay = {
        "type": "FeatureCollection",
        "features": feats,
        "properties": {
            "issue_date": f"{inp.issue:%Y-%m-%d}",
            "seed_field_day": f"{inp.seed_day:%Y-%m-%d}",
            "seed_pixels": seeds.n_pixels,
            "note": "P1 drift particles (frozen config) at the end of each lead window",
        },
    }
    return tab, overlay, _sha_file(cur) + _sha_file(wind)


# ---------------------------------------------------------------------------------------------- forecast
def make_forecast(issue: pd.Timestamp, use_p1: bool = True) -> dict[str, Any]:
    bundle = B.load()
    inp = gather(issue)
    rows = build_rows(inp)
    overlay: dict[str, Any] = {"type": "FeatureCollection", "features": []}
    p1_status = "skipped"
    p1_hash = ""
    if use_p1:
        try:
            tab, overlay, p1_hash = run_p1(inp, bundle)
            t = tab[["site", "lead", "idx_window", "idx_cum"]]
            rows = rows.merge(t, on=["site", "lead"], how="left")
            p1_status = "ok"
        except Exception as e:  # never fake P1: fall back to missing P1 features and say so
            log.error("P1 failed: %s", e)
            p1_status = f"failed: {type(e).__name__}: {e}"[:300]
    if "idx_window" not in rows:
        rows["idx_window"], rows["idx_cum"] = np.nan, np.nan
    rows["p1_idx_window"], rows["p1_idx_cum"] = np.log1p(rows["idx_window"]), np.log1p(rows["idx_cum"])
    pred = B.predict(bundle, rows.assign(idx_window=rows["idx_window"].fillna(0.0)))
    if p1_status != "ok":
        pred["P1"] = np.nan
    itab = pd.read_csv(OUT / "m2_interval_table.csv")
    sites = []
    for s in SITES:
        leads = []
        for i in np.flatnonzero((rows["site"] == s.id).to_numpy()):
            p = float(pred["M2"].iloc[i])
            lo, hi = lookup(itab, p)
            D = rows["date"].iloc[i]
            leads.append(
                {
                    "lead_days": int(rows["lead"].iloc[i]),
                    "target_date": f"{D:%Y-%m-%d}",
                    "probability": round(p, 4),
                    "interval_80": [round(lo, 4), round(hi, 4)],
                    "climatology": round(float(pred["B1"].iloc[i]), 4),
                    "issue_time_model_M2_fc": round(float(pred["M2_fc"].iloc[i]), 4),
                    "drift_index_P1": None if pd.isna(pred["P1"].iloc[i]) else round(float(pred["P1"].iloc[i]), 4),
                    "in_validated_season": bool(D.month in SEASON_MONTHS),
                }
            )
        sites.append({"id": s.id, "name": s.name, "lat": s.lat, "lon": s.lon, "leads": leads})
    issue_time = issue.normalize().tz_localize("UTC") + pd.Timedelta(hours=12)
    return {
        "issue_date": f"{issue:%Y-%m-%d}",
        "issue_time": issue_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generated_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model_version": bundle["model_version"],
        "served_model": "M2",
        "target": "P(moderate-or-worse sargassum day: severity >= 2) at the beach on the target date",
        "interval_80_definition": "10th–90th percentile of the observed event frequency in 2025–2026 when M2 issued a "
        "probability in the same 0.05 bin (outputs/m2_interval_table.csv)",
        "p1_status": p1_status,
        "inputs": {
            **inp.status,
            "afai_hash": _sha_dir(inp.afai_dir),
            "openmeteo_hash": _sha_dir(inp.om_root),
            "p1_forcing_hash": p1_hash,
            "bundle_sha256": B.load_meta()["bundle_sha256"][:16],
        },
        "disclaimer": disclaimer(),
        "attribution": ATTRIBUTION,
        "sites": sites,
        "_overlay": overlay,
        "_labels": inp.labels,
    }


# ---------------------------------------------------------------------------------------------- track record
def score_matured(labels: pd.DataFrame) -> dict[str, Any]:
    items_path = WOUT / "track_record_items.csv"
    have = pd.read_csv(items_path, parse_dates=["target_date"]) if items_path.exists() else pd.DataFrame()
    done = set(zip(have.get("issue_date", []), have.get("site", []), have.get("lead_days", []), strict=False))
    lab = labels[labels.severity.notna()][["site", "date", "event"]]
    new = []
    for f in sorted(FORECASTS.glob("*.json")):
        fc = json.loads(f.read_text())
        for s in fc["sites"]:
            for L in s["leads"]:
                key = (fc["issue_date"], s["id"], L["lead_days"])
                if key in done:
                    continue
                m = lab[(lab.site == s["id"]) & (lab.date == pd.Timestamp(L["target_date"]))]
                if len(m):
                    new.append(
                        {
                            "issue_date": fc["issue_date"],
                            "site": s["id"],
                            "lead_days": L["lead_days"],
                            "target_date": L["target_date"],
                            "probability": L["probability"],
                            "climatology": L["climatology"],
                            "observed_event": int(m.event.iloc[0]),
                            "model_version": fc["model_version"],
                        }
                    )
    allrows = pd.concat([have, pd.DataFrame(new)], ignore_index=True) if new else have
    if new:
        allrows.to_csv(items_path, index=False)
    rec: dict[str, Any] = {
        "updated_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "n": int(len(allrows)),
        "note": "Live forecasts scored as beach reports arrive. Off-season (Nov–Feb) days are outside "
        "the validated Mar–Oct season.",
    }
    if len(allrows) >= 1:
        from eval.metrics import brier, bss, reliability, roc_auc

        y, p, c = allrows.observed_event.to_numpy(), allrows.probability.to_numpy(), allrows.climatology.to_numpy()
        bs, bc = brier(y, p), brier(y, c)
        rec.update(
            {
                "brier": round(bs, 4),
                "brier_climatology": round(bc, 4),
                "bss_vs_climatology": round(bss(bs, bc), 4),
                "auc": None if np.isnan(roc_auc(y, p)) else round(roc_auc(y, p), 4),
                "event_rate": round(float(y.mean()), 4),
                "reliability": reliability(y, p).round(4).to_dict(orient="records"),
            }
        )
    test = pd.read_csv(OUT / "results_test.csv", dtype={"lead": str, "season": str})
    t = test[(test.season == "2025-2026") & (test.lead == "all") & (test.model.isin(["M2", "B1", "M2_fc", "M1"]))]
    rec["test_seasons_2025_2026"] = (
        t[["model", "brier", "bss_B1", "bss_B1_lo", "bss_B1_hi", "auc", "auc_lo", "auc_hi"]]
        .round(4)
        .to_dict(orient="records")
    )
    (WOUT / "track_record.json").write_text(json.dumps(rec, indent=1) + "\n")
    return rec


# ---------------------------------------------------------------------------------------------- publish + staleness
def publish(fc: dict[str, Any], overlay: dict[str, Any], track: dict[str, Any]) -> None:
    (API / "forecast").mkdir(parents=True, exist_ok=True)
    for f in sorted(FORECASTS.glob("*.json")):
        (API / "forecast" / f.name).write_text(f.read_text())
    (API / "forecast" / "latest.json").write_text(json.dumps(fc, indent=1) + "\n")
    (API / "drift").mkdir(parents=True, exist_ok=True)
    (API / "drift" / "latest.geojson").write_text(json.dumps(overlay) + "\n")
    (API / "track_record.json").write_text(json.dumps(track, indent=1) + "\n")
    sites = {
        "sites": [{"id": s.id, "name": s.name, "lat": s.lat, "lon": s.lon} for s in SITES],
        "region": "Broward County, Florida (8 FIU Sargassum Watch sites)",
        "attribution": ATTRIBUTION,
        "disclaimer": disclaimer(),
        "model_version": fc["model_version"],
        "validated_season": "March–October",
        "leads_days": [1, 2, 3, 5, 7],
    }
    (API / "sites.json").write_text(json.dumps(sites, indent=1) + "\n")


def staleness(fc: dict[str, Any], issue: pd.Timestamp) -> dict[str, Any]:
    st = fc["inputs"]

    def age(s: str) -> float | None:
        try:
            return float((issue.normalize() - pd.Timestamp(s[:10])).days)
        except Exception:
            return None

    ages = {
        "fiu_newest_entry": age(st.get("fiu_newest_entry", "")),
        "afai_last_step": age(st.get("afai_last_step", "")),
    }
    stale = {k: v for k, v in ages.items() if v is None or v > STALE_DAYS}
    if not str(fc["p1_status"]).startswith(("ok", "skipped")):
        stale["p1"] = fc["p1_status"]
    status = {"issue_date": fc["issue_date"], "ages_days": ages, "stale": stale, "p1_status": fc["p1_status"]}
    (WOUT / "ops").mkdir(parents=True, exist_ok=True)
    (WOUT / "ops" / "status.json").write_text(json.dumps(status, indent=1) + "\n")
    if stale and os.environ.get("GITHUB_ACTIONS") == "true":
        title = f"Stale input(s) > {STALE_DAYS} days: {', '.join(sorted(stale))}"
        existing = subprocess.run(
            ["gh", "issue", "list", "--state", "open", "--search", title, "--json", "number"],
            capture_output=True,
            text=True,
        ).stdout
        if existing.strip() in ("", "[]"):
            subprocess.run(
                [
                    "gh",
                    "issue",
                    "create",
                    "--title",
                    title,
                    "--body",
                    f"Daily run {fc['issue_date']}: {json.dumps(status, indent=1)}\n\nIf AFAI has stopped "
                    "(MODIS end, 2027), switch the adapter to a VIIRS/OLCI product (SPEC risks).",
                ],
                check=False,
            )
    return status


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", type=pd.Timestamp, default=pd.Timestamp(datetime.now(UTC).date()))
    ap.add_argument("--no-p1", action="store_true")
    ap.add_argument(
        "--scratch",
        type=Path,
        default=None,
        help="write everything under this dir (test runs; never touches the append-only record or the published API)",
    )
    a = ap.parse_args()
    if a.scratch:
        global WOUT, FORECASTS, API
        WOUT, FORECASTS, API = a.scratch, a.scratch / "forecasts", a.scratch / "api" / "v1"
        WOUT.mkdir(parents=True, exist_ok=True)
    issue = pd.Timestamp(a.date).normalize()
    dest = FORECASTS / f"{issue:%Y-%m-%d}.json"
    fc = make_forecast(issue, use_p1=not a.no_p1)
    overlay, labels = fc.pop("_overlay"), fc.pop("_labels")
    FORECASTS.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        log.info("%s already frozen; not rewritten (append-only)", dest)
        fc = json.loads(dest.read_text())
    else:
        dest.write_text(json.dumps(fc, indent=1) + "\n")
    track = score_matured(labels)
    publish(fc, overlay, track)
    status = staleness(fc, issue)
    print(
        json.dumps(
            {"issue_date": fc["issue_date"], "p1": fc["p1_status"], "stale": status["stale"], "scored": track["n"]},
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
