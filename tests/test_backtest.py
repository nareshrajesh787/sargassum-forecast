"""Decision backtest: policies use only issue-time information, the oracle bounds every policy, budgets hold."""

from __future__ import annotations

import numpy as np
import pandas as pd

from decision.backtest import POLICIES, ZONE_HOURS, allocate, summarize
from pipeline.sites import SITES


def _preds(days: int = 28, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for d in pd.date_range("2024-06-03", periods=days, freq="D"):
        for s in SITES:
            ev = int(rng.random() < 0.3)
            for lead in (1, 2, 3):
                rows.append(
                    {
                        "site": s.id,
                        "date": d,
                        "lead": lead,
                        "event": ev,
                        "last_event": float(rng.integers(0, 2)),
                        "event_rate_7d": rng.random(),
                        "B1": rng.random() * 0.3,
                        "M2": 0.6 * ev + 0.4 * rng.random(),
                        "M2_fc": rng.random(),
                    }
                )
    return pd.DataFrame(rows)


def test_budget_respected_and_oracle_is_the_ceiling() -> None:
    p = _preds()
    for budget in (4, 8, 16):
        a = allocate(p, lead=2, budget=budget)
        assert (a.hours <= budget).all()
        wide = a.pivot(index="date", columns="policy", values="covered")
        for pol in POLICIES:
            assert (wide[pol] <= wide["oracle"]).all()


def test_oracle_covers_everything_it_can_afford() -> None:
    p = _preds()
    total_hours = sum(ZONE_HOURS.values())
    a = allocate(p, lead=1, budget=total_hours)
    o = a[a.policy == "oracle"]
    assert (o.covered == o.events_available).all()


def test_summary_shares_and_paired_diffs() -> None:
    p = _preds()
    s = summarize(allocate(p, lead=2, budget=8), n_boot=50).set_index("policy")
    assert s.loc["oracle", "share_of_oracle"] == 1.0
    assert 0 <= s.loc["reactive", "share_of_oracle"] <= 1
    assert s.loc["forecast", "share_of_oracle"] > s.loc["forecast_fc", "share_of_oracle"]  # informative M2 here
    assert np.isnan(s.loc["reactive"].get("share_of_oracle_minus_reactive", np.nan))
