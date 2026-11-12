"""Offline tests for Phase 1 adapters and spike helpers."""

from __future__ import annotations

import math
from datetime import date

import numpy as np
import pytest

from pipeline.ingest import afai, openmeteo
from spike import common


def test_month_range_inclusive_and_year_rollover() -> None:
    r = afai.month_range("2024-11", "2025-02")
    assert [f.isoformat() for f, _ in r] == ["2024-11-01", "2024-12-01", "2025-01-01", "2025-02-01"]
    assert r[1][1] == date(2024, 12, 31) and r[3][1] == date(2025, 2, 28)


def test_griddap_url_box_and_stride() -> None:
    u = afai.griddap_url(afai.DATASETS["1D"], date(2024, 6, 1), date(2024, 6, 30), afai.Box(23, 28, -82, -78, 2))
    assert "noaa_aoml_atlantic_oceanwatch_AFAI_1D.nc?AFAI" in u
    assert "(2024-06-01T00:00:00Z):1:(2024-06-30T23:59:59Z)" in u
    assert "(23):2:(28)" in u and "(-82):2:(-78)" in u


def test_openmeteo_weight_and_chunks() -> None:
    assert openmeteo.estimate_weight(2, date(2024, 1, 1), date(2024, 1, 7)) == 1.0
    assert openmeteo.estimate_weight(20, date(2024, 1, 1), date(2024, 1, 28)) == pytest.approx(4.0)
    ch = openmeteo.year_chunks(date(2022, 3, 1), date(2024, 2, 1))
    assert ch == [
        (date(2022, 3, 1), date(2022, 12, 31)),
        (date(2023, 1, 1), date(2023, 12, 31)),
        (date(2024, 1, 1), date(2024, 2, 1)),
    ]


def test_wind_prev_requests_only_lead_specific_fields() -> None:
    f = openmeteo.FEEDS["wind_prev"]
    assert all("_previous_day" in v for v in f.hourly)
    assert {int(v.rsplit("day", 1)[1]) for v in f.hourly} == set(openmeteo.LEADS)


@pytest.mark.parametrize(
    ("spike", "rerun", "flag"),
    [
        (0.76, 0.7615, False),
        (0.67, 0.6351, True),
        (215, 231, True),
        (2508, 2509, False),
        (3, 0, True),
        ("2016-06-18", "2016-06-18", False),
        (None, 1.0, None),
        (0.5, math.nan, None),
    ],
)
def test_differs_tolerance(spike: object, rerun: object, flag: bool | None) -> None:
    assert common.differs(spike, rerun) is flag


def test_auc_matches_definition() -> None:
    y = np.array([0, 0, 1, 1])
    assert common.auc(y, np.array([0.1, 0.4, 0.35, 0.8])) == pytest.approx(0.75)
    assert common.auc(y, np.array([1, 1, 1, 1])) == pytest.approx(0.5)  # ties count 1/2
    assert common.auc(np.array([1, 1]), np.array([0.2, 0.3])) != common.auc(np.array([1, 1]), np.array([0.2, 0.3]))
