"""Phase 6 ops: interval lookup, frozen bundle reproducibility, disclaimer sourced from outputs, live skeleton."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from ops.intervals import lookup


def test_interval_lookup_and_fallback() -> None:
    tab = pd.DataFrame({"bin_lo": [0.0, 0.05, 0.15], "obs_p10": [0.06, 0.11, 0.4], "obs_p90": [0.1, 0.16, 0.5]})
    assert lookup(tab, 0.02) == (0.06, 0.1)
    assert lookup(tab, 0.07) == (0.11, 0.16)
    assert lookup(tab, 0.12) in {(0.11, 0.16), (0.4, 0.5)}  # unseen bin → nearest seen bin
    assert lookup(tab, 0.99) == (0.4, 0.5)


@pytest.mark.skipif(not Path("data/test_lock/preds_test.parquet").exists(), reason="needs local test-lock data")
def test_bundle_reproduces_frozen_test_predictions() -> None:
    from ops.bundle import verify

    assert verify() == 0


def test_disclaimer_numbers_come_from_outputs() -> None:
    from ops.daily import disclaimer

    t = pd.read_csv("outputs/results_test.csv", dtype={"lead": str, "season": str})
    r = t[(t.season == "2025-2026") & (t.lead == "all") & (t.model == "M2")].iloc[0]
    assert f"{r.bss_B1:+.3f}" in disclaimer()


def test_live_skeleton_has_no_labels_and_correct_targets() -> None:
    from ops.live import skeleton_live

    df = skeleton_live(pd.Timestamp("2027-06-01"))
    assert len(df) == 8 * 5 and "event" not in df
    assert (df.date - df.issue_date).dt.days.tolist() == df.lead.tolist()
    assert (df.issue_time == pd.Timestamp("2027-06-01T12:00Z")).all()
