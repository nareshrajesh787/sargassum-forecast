"""P1 physics tests on synthetic forcing (no Copernicus data needed)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from physics.arrivals import RUN_HOURS, arrival_table, first_arrival_hours, lead_window
from physics.forcing import currents_cf, wind_cf, write_cf
from physics.seed import MIN_COAST_KM, Seeds, seeds_from_field
from pipeline.features.afai_grid import DETECT_THRESHOLD
from pipeline.sites import SITES

PALMS = next(s for s in SITES if s.id == "the_palms")


def _smoc(u: float, v: float, hours: int = 200) -> xr.Dataset:
    t = pd.date_range("2024-06-01T18:00", periods=hours, freq="h")
    lat = np.arange(25.0, 27.51, 1 / 12)
    lon = np.arange(-81.0, -78.49, 1 / 12)
    shape = (len(t), 1, len(lat), len(lon))
    f = lambda x: (("time", "depth", "latitude", "longitude"), np.full(shape, x, np.float32))  # noqa: E731
    return xr.Dataset(
        {
            "uo": f(u),
            "vo": f(v),
            "utide": f(0.01),
            "vtide": f(0.0),
            "vsdx": f(0.05),
            "vsdy": f(0.0),
            "utotal": f(u + 0.06),
            "vtotal": f(v),
        },
        coords={"time": t, "depth": [0.494], "latitude": lat, "longitude": lon},
    )


def _wind(u: float, hours: int = 200) -> xr.Dataset:
    s = _smoc(0, 0, hours).isel(depth=0)
    return xr.Dataset({"eastward_wind": s.uo * 0 + u, "northward_wind": s.vo * 0}).drop_vars("depth")


def test_current_modes_add_up() -> None:
    s = _smoc(-0.2, 0.5)
    tot = currents_cf(s, "total")
    nos = currents_cf(s, "no_stokes")
    assert float(tot.x_sea_water_velocity.mean()) == pytest.approx(-0.14)
    assert float(nos.x_sea_water_velocity.mean()) == pytest.approx(-0.19)  # uo + utide, Stokes removed
    assert tot.x_sea_water_velocity.attrs["standard_name"] == "x_sea_water_velocity"
    assert set(tot.dims) == {"time", "lat", "lon"}


def test_lead_windows_tile_the_week() -> None:
    assert lead_window(1) == (18, 42)  # D−1 12:00 → D 12:00 with seed at I−1 18:00, D = I+1
    assert lead_window(7) == (162, 186)
    assert RUN_HOURS == 186
    for a, b in zip((1, 2), (2, 3), strict=True):
        assert lead_window(a)[1] == lead_window(b)[0]


def test_first_arrival_uses_last_valid_position_for_stranded() -> None:
    hours = np.arange(5.0)
    lon = np.array(
        [
            [-79.9, -80.0, PALMS.lon + 0.01, np.nan, np.nan],  # strands 1 km from site at hour 2
            [-79.5, -79.5, -79.5, -79.5, -79.5],
        ]
    )  # never near
    lat = np.full_like(lon, PALMS.lat)
    lat[np.isnan(lon)] = np.nan
    first = first_arrival_hours(lon, lat, hours)["the_palms"]
    assert first[0] == 2 and np.isnan(first[1])


def test_arrival_table_index_scales_with_weight() -> None:
    hours = np.arange(0, 50.0)
    lon = np.full((4, 50), -79.0)
    lon[:2, 30:] = PALMS.lon  # two particles arrive at hour 30 → lead 1 window (18, 42]
    lat = np.full_like(lon, PALMS.lat)
    tab = arrival_table(lon, lat, hours, np.array([0.0, 0.0, 0.0, 0.0]), total_weight=10.0)
    r = tab[(tab.site == "the_palms") & (tab.lead == 1)].iloc[0]
    assert r.arr_window == 2 and r.idx_window == pytest.approx(5.0)
    assert tab[(tab.site == "the_palms") & (tab.lead == 2)].iloc[0].arr_window == 0


def test_seeding_respects_threshold_and_coast() -> None:
    lat = np.array([26.0, 26.1])
    lon = np.array([-80.0, -79.5])
    anom = np.array([[DETECT_THRESHOLD * 0.5, 0.002], [0.003, np.nan]])
    coast = np.array([[10.0, 1.0], [MIN_COAST_KM + 1, 50.0]])  # (0,1) is too close to shore
    land = np.zeros_like(coast, bool)
    s = seeds_from_field(anom, lat, lon, 50, np.random.default_rng(0), pd.Timestamp("2024-06-01"), coast, land)
    assert s.n_pixels == 1 and np.allclose(s.lat, 26.1, atol=0.05) and np.allclose(s.lon, -80.0, atol=0.25)
    assert s.total_weight == pytest.approx(0.003 - DETECT_THRESHOLD)


@pytest.mark.filterwarnings("ignore")
def test_opendrift_onshore_flow_strands_at_site_and_windage_matters(tmp_path: Path) -> None:
    pytest.importorskip("opendrift")
    from physics.drift import simulate

    cur = write_cf(currents_cf(_smoc(-0.25, 0.0), "no_stokes"), tmp_path / "cur.nc")
    wind = write_cf(wind_cf(_wind(-8.0)), tmp_path / "wind.nc")  # 8 m/s easterly → onshore
    rng = np.random.default_rng(1)
    seeds = Seeds(
        PALMS.lon + 0.15 + rng.uniform(-0.01, 0.01, 200),
        PALMS.lat + rng.uniform(-0.01, 0.01, 200),
        total_weight=1.0,
        n_pixels=200,
        field_day=pd.Timestamp("2024-06-01"),
    )
    tab = simulate(seeds, cur, wind, windages=(0.0, 0.03), n_per_group=200, hours=96)
    palms = tab[tab.site == "the_palms"]
    cum = palms.groupby("windage").arr_cum.max()
    assert cum.loc[0.03] > 0 and cum.loc[0.0] > 0
    # with an onshore wind, 3 % windage must arrive no later (more by lead 1) than 0 %
    l1 = palms[palms.lead == 1].set_index("windage").arr_cum
    assert l1.loc[0.03] >= l1.loc[0.0]


def test_score_sweep_and_mapping_on_synthetic_arrivals() -> None:
    from physics.score import fit_mapping, p1_features, predict_mapping, sweep

    rng = np.random.default_rng(0)
    dates = pd.date_range("2024-06-01", periods=60, freq="D")
    labels = pd.DataFrame(
        {
            "site": "the_palms",
            "date": np.repeat(dates, 2),
            "lead": np.tile([1, 2], 60),
            "season": 2024,
            "event": rng.integers(0, 2, 120),
        }
    )
    rows = []
    for mode in ("total", "no_stokes"):
        for w in (0.0, 0.02):
            idx = labels.event * (5.0 if (mode, w) == ("total", 0.02) else 0.0) + rng.uniform(0, 1, 120)
            rows.append(labels[["site", "date", "lead"]].assign(mode=mode, windage=w, idx_window=idx, idx_cum=idx))
    feat = p1_features(pd.concat(rows), labels)
    sw = sweep(feat)
    assert (sw.iloc[0]["mode"], sw.iloc[0].windage) == ("total", 0.02) and sw.iloc[0].auc_window == 1.0
    chosen = feat[(feat["mode"] == "total") & (feat.windage == 0.02)].reset_index(drop=True)
    p = predict_mapping(fit_mapping(chosen), chosen)
    assert np.all((p > 0) & (p < 1)) and p[chosen.event == 1].mean() > p[chosen.event == 0].mean()


def test_empty_seed_days_produce_explicit_zeros() -> None:
    from physics.drift import zero_table

    z = zero_table((0.0, 0.03))
    assert len(z) == len(SITES) * 5 * 2 and (z.idx_window == 0).all()
