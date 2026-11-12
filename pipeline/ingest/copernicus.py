"""Copernicus Marine adapter (catalogue + subset of SMOC hourly surface currents).

Primary feed: ``GLOBAL_ANALYSISFORECAST_PHY_001_024`` dataset ``cmems_mod_glo_phy_anfc_merged-uv_PT1H-i``
(SMOC: Eulerian uo/vo + tides utide/vtide + Stokes drift vsdx/vsdy = utotal/vtotal), 1/12°, hourly,
with a 10-day forecast. Older seasons: ``GLOBAL_MULTIYEAR_PHY_001_030`` (GLORYS12V1) daily-mean uo/vo
on the same 1/12° grid, and ``GLOBAL_MULTIYEAR_WAV_001_032`` 3-hourly Stokes drift (VSDX/VSDY, 0.2°).

Catalogue queries need no account. Data access (``subset``) needs a free Copernicus Marine account via
``COPERNICUSMARINE_SERVICE_USERNAME`` / ``COPERNICUSMARINE_SERVICE_PASSWORD`` (env vars or GitHub
secrets only; never logged). Credit: E.U. Copernicus Marine Service Information.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SMOC = "cmems_mod_glo_phy_anfc_merged-uv_PT1H-i"
PRODUCTS = {
    "GLOBAL_ANALYSISFORECAST_PHY_001_024": "analysis + 10-day forecast",
    "GLOBAL_MULTIYEAR_PHY_001_030": "GLORYS12V1 reanalysis",
    "GLOBAL_MULTIYEAR_WAV_001_032": "wave reanalysis (Stokes drift)",
    "MULTIOBS_GLO_PHY_MYNRT_015_003": "GlobCurrent observation-based total currents",
}
CURRENT_VARS = {
    "uo",
    "vo",
    "utotal",
    "vtotal",
    "utide",
    "vtide",
    "vsdx",
    "vsdy",
    "VSDX",
    "VSDY",
    "ue",
    "ve",
    "ugos",
    "vgos",
    "uo_glor",
}


def has_credentials() -> bool:
    return bool(os.environ.get("COPERNICUSMARINE_SERVICE_USERNAME")) and bool(
        os.environ.get("COPERNICUSMARINE_SERVICE_PASSWORD")
    )


def _ms(v: Any) -> str | None:
    if v is None:
        return None
    return datetime.fromtimestamp(float(v) / 1000, UTC).strftime("%Y-%m-%dT%H:%M")


def catalogue_rows(product_id: str) -> list[dict[str, Any]]:
    """One row per (dataset, version, part) with time coverage, step, grid step and current variables."""
    import copernicusmarine as cm

    cat = cm.describe(product_id=product_id, disable_progress_bar=True)
    rows = []
    for p in cat.products:
        for ds in p.datasets:
            for v in ds.versions:
                for part in v.parts:
                    svc = next((s for s in part.services if s.service_name == "arco-geo-series"), None)
                    if svc is None or not svc.variables:
                        continue
                    names = [x.short_name for x in svc.variables]
                    co = {c.coordinate_id: c for c in svc.variables[0].coordinates}
                    t, lat = co.get("time"), co.get("latitude")
                    rows.append(
                        {
                            "product_id": p.product_id,
                            "dataset_id": ds.dataset_id,
                            "version": v.label,
                            "part": part.name,
                            "time_min": _ms(getattr(t, "minimum_value", None)),
                            "time_max": _ms(getattr(t, "maximum_value", None)),
                            "time_step_hours": (float(t.step) / 3.6e6) if t is not None and t.step else None,
                            "lat_step_deg": float(lat.step) if lat is not None and lat.step else None,
                            "current_vars": sorted(set(names) & CURRENT_VARS),
                        }
                    )
    return rows


def subset_smoc(start: str, end: str, box: tuple[float, float, float, float], out: Path) -> Path:
    """Download SMOC surface currents for [start, end] over (lat0, lat1, lon0, lon1). Needs credentials."""
    if not has_credentials():
        raise PermissionError("Copernicus Marine credentials not set (see .env.example)")
    import copernicusmarine as cm

    lat0, lat1, lon0, lon1 = box
    out.parent.mkdir(parents=True, exist_ok=True)
    cm.subset(
        dataset_id=SMOC,
        variables=["utotal", "vtotal", "uo", "vo", "utide", "vtide", "vsdx", "vsdy"],
        minimum_latitude=lat0,
        maximum_latitude=lat1,
        minimum_longitude=lon0,
        maximum_longitude=lon1,
        start_datetime=start,
        end_datetime=end,
        output_directory=str(out.parent),
        output_filename=out.name,
        disable_progress_bar=True,
    )
    return out
