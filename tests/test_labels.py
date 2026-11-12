"""Frozen label rules, site assignment and label timestamps."""

from __future__ import annotations

import math
from typing import Any

import pandas as pd
import pytest

from pipeline.labels import fiu_labels as L
from pipeline.sites import SITES

PRESENT = "Mostly Fresh (Yellow) Specimens"
NONE = "No Sargassum Present"


@pytest.mark.parametrize(
    ("cond", "water", "smell", "expected"),
    [
        (NONE, "Unchanged (blue and/or green)", "No", 0),
        (PRESENT, "Unchanged (blue and/or green)", "No", 1),
        (PRESENT, "Slightly brown", "No", 2),
        (PRESENT, "Unchanged (blue and/or green)", "Yes", 2),
        (PRESENT, "Very Brown", "No", 3),
        (PRESENT, "Very Brown", "Yes", 3),
        (PRESENT, "", "", 1),  # 2019 form: no water question
        (PRESENT, "Not applicable", "No", 1),
        ("", "Very Brown", "No", 3),
        ("", "", "No", math.nan),  # presence unknown
        # precedence none_first (frozen): "No Sargassum Present" wins over brown water / smell
        (NONE, "Very Brown", "No", 0),
        (NONE, "Slightly brown", "Yes", 0),
    ],
)
def test_severity_rules_frozen(cond: str, water: str, smell: str, expected: float) -> None:
    got = L.severity(cond, water, smell)
    if math.isnan(expected):
        assert math.isnan(got)
    else:
        assert got == expected


def test_precedence_is_frozen() -> None:
    assert L.PRECEDENCE == "none_first"
    assert L.severity(NONE, "Very Brown", "Yes", "water_first") == 3


def _entry(
    uuid: str,
    name: str,
    lat: Any,
    lon: Any,
    date: str,
    created: str,
    uploaded: str,
    cond: str = PRESENT,
    water: str = "Unchanged (blue and/or green)",
    smell: str = "No",
) -> dict[str, Any]:
    return {
        "ec5_uuid": uuid,
        "created_at": created,
        "uploaded_at": uploaded,
        "1_Date_of_Observatio": date,
        "2_Time_of_Observatio": "08:00:00",
        "3_GPS_Coordinates_of": {"latitude": lat, "longitude": lon},
        "4_Site_Name_eg_Miami": name,
        "12_Condition_of_the_": cond,
        "14_Color_of_the_wate": water,
        "15_Does_the_site_sme": smell,
    }


PALMS = next(s for s in SITES if s.id == "the_palms")
PIER = next(s for s in SITES if s.id == "commercial_pier")


@pytest.mark.parametrize(
    ("name", "lat", "lon", "expected"),
    [
        ("The Palms", PALMS.lat, PALMS.lon, "the_palms"),
        ("  the  palms ", "", "", "the_palms"),  # no GPS: name alone
        ("Commerical pier", PIER.lat, PIER.lon, "commercial_pier"),  # typo alias
        ("The Palms", PIER.lat, PIER.lon, None),  # name says Palms, GPS 3.7 km away at the pier → conflict
        ("Fort Lauderdale", PALMS.lat + 0.001, PALMS.lon, "the_palms"),  # generic name, GPS within 0.3 km
        ("Fort Lauderdale", PALMS.lat + 0.01, PALMS.lon, None),  # generic name, GPS 1.1 km away
        ("Georgia street", 26.0155, -80.1170, None),  # another beach
        ("Palm Beach County Line", 26.3209, -80.0744, "county_line"),  # not The Palms
        ("Key Biscayne (Key colony)", 25.6968, -80.1560, None),
    ],
)
def test_assign_site(name: str, lat: Any, lon: Any, expected: str | None) -> None:
    df = L.parse_reports([_entry("u", name, lat, lon, "01/06/2024", "2024-06-01T12:00:00Z", "2024-06-01T12:01:00Z")])
    assert L.assign_site(df).iloc[0] == expected


def test_date_is_day_first() -> None:
    df = L.parse_reports(
        [
            _entry(
                "u",
                "The Palms",
                PALMS.lat,
                PALMS.lon,
                "09/11/2026",
                "2026-11-09T22:27:23Z",
                "2026-11-10T00:19:42Z",
            )
        ]
    )
    assert df.obs_date.iloc[0] == pd.Timestamp("2026-11-09")


def test_site_day_merges_worst_and_available_at_is_last_upload() -> None:
    entries = [
        _entry(
            "a",
            "The Palms",
            PALMS.lat,
            PALMS.lon,
            "01/06/2024",
            "2024-06-01T12:00:00Z",
            "2024-06-01T13:00:00Z",
        ),
        _entry(
            "b",
            "The Palms",
            PALMS.lat,
            PALMS.lon,
            "01/06/2024",
            "2024-06-01T14:00:00Z",
            "2024-06-02T09:00:00Z",
            water="Very Brown",
        ),
        _entry(
            "c",
            "The Palms",
            PALMS.lat,
            PALMS.lon,
            "02/06/2024",
            "2024-06-02T12:00:00Z",
            "2024-06-02T12:05:00Z",
        ),
    ]
    sd = L.site_days(L.label_reports(L.parse_reports(entries))).set_index("date")
    d1 = sd.loc[pd.Timestamp("2024-06-01")]
    assert d1.severity == 3 and d1.n_reports == 2 and bool(d1.event) and bool(d1.heavy)
    assert d1.available_at == pd.Timestamp("2024-06-02T09:00:00Z")
    assert sd.loc[pd.Timestamp("2024-06-02")].severity == 1
    # a label can never be available before the day it describes ends... at the earliest, during it
    assert (sd.available_at.dt.tz_convert("America/New_York").dt.normalize().dt.tz_localize(None) >= sd.index).all()


def test_implausible_dates_dropped() -> None:
    entries = [
        _entry(
            "typo",
            "The Palms",
            PALMS.lat,
            PALMS.lon,
            "06/10/2018",
            "2021-06-11T21:38:46Z",
            "2021-06-11T21:40:00Z",
        ),
        _entry(
            "future",
            "The Palms",
            PALMS.lat,
            PALMS.lon,
            "05/06/2024",
            "2024-06-01T12:00:00Z",
            "2024-06-01T12:00:00Z",
        ),
        _entry(
            "ok",
            "The Palms",
            PALMS.lat,
            PALMS.lon,
            "28/05/2024",
            "2024-06-01T12:00:00Z",
            "2024-06-01T12:00:00Z",
        ),
    ]
    sd = L.site_days(L.label_reports(L.parse_reports(entries)))
    assert list(sd.date) == [pd.Timestamp("2024-05-28")]


def test_missing_days_stay_missing() -> None:
    entries = [
        _entry(
            "a",
            "The Palms",
            PALMS.lat,
            PALMS.lon,
            "01/06/2024",
            "2024-06-01T12:00:00Z",
            "2024-06-01T12:00:00Z",
        ),
        _entry(
            "b",
            "The Palms",
            PALMS.lat,
            PALMS.lon,
            "03/06/2024",
            "2024-06-03T12:00:00Z",
            "2024-06-03T12:00:00Z",
        ),
    ]
    sd = L.site_days(L.label_reports(L.parse_reports(entries)))
    assert len(sd) == 2  # 2024-06-02 is absent, not filled with 0
    assert pd.Timestamp("2024-06-02") not in set(sd.date)


def test_unknown_severity_site_day_has_no_event() -> None:
    entries = [
        _entry(
            "a",
            "The Palms",
            PALMS.lat,
            PALMS.lon,
            "01/06/2024",
            "2024-06-01T12:00:00Z",
            "2024-06-01T12:00:00Z",
            cond="",
            water="",
            smell="No",
        )
    ]
    sd = L.site_days(L.label_reports(L.parse_reports(entries)))
    assert pd.isna(sd.severity.iloc[0]) and pd.isna(sd.event.iloc[0])
