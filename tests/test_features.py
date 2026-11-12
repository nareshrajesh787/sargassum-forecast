"""Leakage and split discipline for the feature store, plus Phase 2 unit tests."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from eval.bootstrap import ci, resample_indices, week_blocks
from eval.metrics import brier, bss, reliability
from models.baselines import B0, B1
from pipeline.features import build as fb
from pipeline.geo import onshore

STORE = Path(f"data/features/v{fb.FEATURE_VERSION}/features.parquet")
needs_store = pytest.mark.skipif(not STORE.exists(), reason="feature store not built (no data in CI)")


# ------------------------------------------------------------------ on the real store
@needs_store
def test_every_feature_available_by_issue_time_except_declared_perfect_prog() -> None:
    df = pd.read_parquet(STORE)
    manifest = json.loads((STORE.parent / "manifest.json").read_text())
    assert set(manifest["perfect_prog_groups"]) == set(fb.PERFECT_PROG)
    for group, cols in manifest["groups"].items():
        avail = df[f"avail_{group}"]
        late = avail > df["issue_time"]
        if group in fb.PERFECT_PROG:
            # declared upper-bound inputs: valid on the target day, so after the issue time wherever present
            present = df[cols].notna().any(axis=1)
            assert late[present].all(), group
        else:
            assert not late.any(), f"{group}: {int(late.sum())} rows use data after the issue time"


@needs_store
def test_store_has_no_test_seasons_and_every_feature_has_a_group() -> None:
    df = pd.read_parquet(STORE)
    assert not set(df["season"].unique()) & set(fb.TEST_SEASONS)
    manifest = json.loads((STORE.parent / "manifest.json").read_text())
    grouped = {c for cols in manifest["groups"].values() for c in cols}
    meta = {"site", "date", "season", "severity", "event", "heavy", "issue_date", "issue_time"}
    ungrouped = [c for c in df.columns if c not in grouped | meta and not c.startswith("avail_")]
    assert ungrouped == []


@needs_store
def test_persistence_uses_only_days_before_issue_and_at_most_3_days_old() -> None:
    df = pd.read_parquet(STORE)
    has = df["last_age_days"].notna()
    assert df.loc[has, "last_age_days"].between(1, 3).all()


# ------------------------------------------------------------------ synthetic unit tests (run in CI)
def test_test_seasons_are_locked() -> None:
    with pytest.raises(fb.TestSeasonLocked):
        fb.check_seasons([2024, 2025], allow_test=False)
    fb.check_seasons([2025], allow_test=True)


def _labels(rows: list[tuple[str, str, float, str]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "site": [r[0] for r in rows],
            "date": pd.to_datetime([r[1] for r in rows]),
            "severity": [r[2] for r in rows],
            "event": [float(r[2] >= 2) for r in rows],
            "available_at": pd.to_datetime([r[3] for r in rows], utc=True),
        }
    )


def test_persistence_ignores_reports_uploaded_after_issue_time() -> None:
    labels = _labels(
        [
            ("the_palms", "2024-06-08", 3, "2024-06-08T14:00Z"),  # day I−2, uploaded in time
            ("the_palms", "2024-06-09", 1, "2024-06-10T13:00Z"),  # day I−1, uploaded 1 h AFTER issue
            ("the_palms", "2024-06-10", 0, "2024-06-10T11:00Z"),  # day I itself: never used
        ]
    )
    issue = pd.Timestamp("2024-06-10")
    df = pd.DataFrame({"site": ["the_palms"], "issue_date": [issue], "issue_time": [pd.Timestamp("2024-06-10T12:00Z")]})
    out = fb.add_persist(df, labels).iloc[0]
    assert out.last_sev == 3 and out.last_age_days == 2
    assert out.avail_persist <= pd.Timestamp("2024-06-10T12:00Z")


def test_persistence_rejects_reports_older_than_3_days() -> None:
    labels = _labels([("the_palms", "2024-06-05", 3, "2024-06-05T14:00Z")])
    df = pd.DataFrame(
        {
            "site": ["the_palms"],
            "issue_date": [pd.Timestamp("2024-06-10")],
            "issue_time": [pd.Timestamp("2024-06-10T12:00Z")],
        }
    )
    out = fb.add_persist(df, labels).iloc[0]
    assert pd.isna(out.get("last_sev", np.nan))
    assert out.n_reports_7d == 1  # still counted in the 7-day rate


def test_afai_window_ends_the_day_before_issue() -> None:
    days = pd.date_range("2024-05-01", "2024-06-30", freq="D")
    det = np.where(days == pd.Timestamp("2024-06-10"), 1.0, 0.0)  # a spike ON the issue day
    stats = pd.DataFrame(
        {"date": days, "region": "offshore", "n_valid": 100, "valid_frac": 1.0, "det_frac": det, "mean_anom": 0.0}
    )
    w = fb.afai_window_stats(stats, "offshore", pd.Series(pd.to_datetime(["2024-06-10", "2024-06-11"])))
    assert w.loc["2024-06-10", "recent7"] == 0.0  # issue-day data not visible
    assert w.loc["2024-06-11", "recent7"] == pytest.approx(1 / 7)  # visible the next day


def test_window_mean_covers_d_minus_1_noon_to_d_0600() -> None:
    idx = pd.date_range("2024-06-09T00:00Z", "2024-06-10T23:00Z", freq="h")
    s = pd.Series(np.where((idx >= "2024-06-09T12:00Z") & (idx <= "2024-06-10T06:00Z"), 1.0, 100.0), index=idx)
    assert fb._window_mean(s, pd.Series(pd.to_datetime(["2024-06-10"])))[0] == 1.0


def test_onshore_sign() -> None:
    assert onshore(np.array(5.0), np.array(95.0), 95.0) == pytest.approx(5.0)  # from the sea → onshore
    assert onshore(np.array(5.0), np.array(275.0), 95.0) == pytest.approx(-5.0)  # from land → offshore
    assert abs(onshore(np.array(5.0), np.array(5.0), 95.0)) < 1e-9  # alongshore


def test_metrics_basics() -> None:
    y = np.array([0, 1, 0, 1])
    assert brier(y, y.astype(float)) == 0.0
    assert bss(0.05, 0.10) == pytest.approx(0.5)
    r = reliability(np.array([0, 1, 1, 0]), np.array([0.05, 0.95, 0.9, 0.15]))
    assert r.n.sum() == 4 and set(r.bin) == {0, 1, 9}


def test_bootstrap_resamples_whole_weeks_deterministically() -> None:
    dates = pd.Series(pd.date_range("2024-06-03", periods=21, freq="D"))  # 3 ISO weeks
    blocks = week_blocks(dates)
    assert len(np.unique(blocks)) == 3
    a, b = resample_indices(blocks, n_boot=5, seed=1), resample_indices(blocks, n_boot=5, seed=1)
    assert all((x == y).all() for x, y in zip(a, b, strict=True))
    for idx in a:
        assert len(idx) == 21  # 3 weeks × 7 rows, whole weeks only
    assert ci(np.arange(1000)) == pytest.approx((24.975, 974.025))


def test_b0_and_b1_fit_on_train_only_shapes() -> None:
    tr = pd.DataFrame({"lead": [1] * 6, "last_event": [1, 1, 0, 0, np.nan, np.nan], "event": [1, 0, 0, 0, 1, 0]})
    m = B0().fit(tr)
    assert m.table[(1, "event")] > m.table[(1, "no_event")]
    sd = pd.DataFrame({"site": ["the_palms"] * 4, "doy": [150, 151, 152, 153], "event": [1, 1, 0, 0]})
    p = B1().fit(sd).predict(pd.DataFrame({"site": ["the_palms", "county_line"], "doy": [151, 151]}))
    assert 0 < p[0] < 1 and 0 < p[1] < 1
