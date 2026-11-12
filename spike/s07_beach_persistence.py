"""Spike row 7: beach persistence, Broward 2025–2026 seasons (same-site next-day agreement, P(e|e))."""

from __future__ import annotations

from typing import Any

import pandas as pd

from spike.common import load_site_days, write


def pairs(sd: pd.DataFrame) -> pd.DataFrame:
    s = sd[sd.in_season & sd.event.notna()][["site", "date", "season", "event"]].copy()
    prev = s.rename(columns={"event": "event_prev"}).assign(date=lambda d: d.date + pd.Timedelta(days=1))
    return s.merge(prev[["site", "date", "event_prev"]], on=["site", "date"], how="inner")


def stats(p: pd.DataFrame, sd_season: pd.DataFrame) -> dict[str, float]:
    e, ep = p.event.astype(bool), p.event_prev.astype(bool)
    return {
        "n_pairs": len(p),
        "agreement": float((e == ep).mean()),
        "p_event_given_event_yesterday": float(e[ep].mean()),
        "base_rate": float(sd_season.event.astype(float).mean()),
    }


def main() -> None:
    sd = load_site_days()
    p = pairs(sd)
    labeled = sd[sd.in_season & sd.event.notna()]
    test = stats(p[p.season.isin([2025, 2026])], labeled[labeled.season.isin([2025, 2026])])
    results: list[dict[str, Any]] = [
        {"metric": "next_day_event_agreement_2025_2026", "spike": 0.70, "rerun": test["agreement"]},
        {
            "metric": "P(event|event_yesterday)_2025_2026",
            "spike": 0.47,
            "rerun": test["p_event_given_event_yesterday"],
        },
        {"metric": "event_base_rate_2025_2026", "spike": 0.28, "rerun": test["base_rate"]},
        {"metric": "n_consecutive_site_day_pairs_2025_2026", "spike": None, "rerun": test["n_pairs"]},
    ]
    # Same statistics on the train (2019–2023) and validation (2024) seasons, for Phase 2 reference.
    by = {}
    for name, seasons in {"train_2019_2023": range(2019, 2024), "val_2024": [2024]}.items():
        by[name] = stats(p[p.season.isin(seasons)], labeled[labeled.season.isin(seasons)])
    write(
        "s07_beach_persistence",
        "Beach persistence, Broward 2025–2026 seasons",
        "Site-day events (severity >= 2), Mar–Oct. Pairs = same site on consecutive calendar days, both labeled. "
        "Agreement = share of pairs with the same event value. Base rate = event share of labeled site-days.",
        results,
        touches_test_seasons=True,
        extra={"non_test_seasons": by},
        notes=["fixed-rule statistics only; nothing fitted or selected"],
    )


if __name__ == "__main__":
    main()
