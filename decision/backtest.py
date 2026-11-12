"""Crew-allocation decision backtest (SIMULATED — SPEC "Decision backtest").

Every target day D, a budget of B crew-hours (``BUDGETS``) is allocated across the Broward sites by Costa's exact
0/1 knapsack (``decision.knapsack``). Crews are booked L days ahead (``BOOKING_LEADS``, default 2), so every
policy may only use what was known at issue day I = D − L:

  reactive       value = 1 if the site's latest report (≤ 3 days old, by the issue time) was an event, else 0;
                 ties broken by the site's 7-day event rate (×1e-3)
  climatology    value = B1 probability × weight
  forecast       value = M2 probability × weight            (perfect-prog upper bound, like M2)
  forecast_fc    value = M2_fc probability × weight         (issue-time inputs only, leakage-safe)
  oracle         value = observed event × weight            (ceiling, perfect knowledge)

Candidate zones on day D are the sites with an observation that day: an unobserved site-day has no outcome
to score. This is a limitation (a real crew would not know which sites will report) and is stated in every output.

Metrics per policy × budget × lead (pooled over days): event site-days covered, crew-hours used, events covered
per crew-hour, share of the oracle's coverage, regret (oracle − policy events covered). 95% CIs: weekly block
bootstrap (1,000), paired across policies (same resampled weeks).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from decision.knapsack import knapsack_select
from eval.bootstrap import N_BOOT, SEED, ci, week_blocks
from pipeline.sites import SITES

# editable zone parameters: crew-hours to clean a site (2–4) and equity weight (default 1)
ZONE_HOURS = dict(zip([s.id for s in SITES], [2, 3, 4, 3, 2, 4, 3, 2], strict=True))
ZONE_WEIGHT = {s.id: 1.0 for s in SITES}
BUDGETS = (4, 6, 8, 10, 12, 14, 16)
BOOKING_LEADS = (1, 2, 3)
POLICIES = ("reactive", "climatology", "forecast", "forecast_fc", "oracle")
OUT = Path("outputs")
LABEL = "SIMULATED backtest (not an operational evaluation)"


def policy_values(day: pd.DataFrame, policy: str) -> np.ndarray:
    w = day["site"].map(ZONE_WEIGHT).to_numpy()
    if policy == "reactive":
        return day["last_event"].fillna(0).to_numpy() + 1e-3 * day["event_rate_7d"].fillna(0).to_numpy()
    if policy == "climatology":
        return day["B1"].to_numpy() * w
    if policy == "forecast":
        return day["M2"].to_numpy() * w
    if policy == "forecast_fc":
        return day["M2_fc"].to_numpy() * w
    if policy == "oracle":
        return day["event"].to_numpy() * w
    raise ValueError(policy)


def allocate(preds: pd.DataFrame, lead: int, budget: int) -> pd.DataFrame:
    """One row per (date, policy): events covered, hours used."""
    rows = []
    for d, day in preds[preds["lead"] == lead].groupby("date"):
        day = day.reset_index(drop=True)
        hours = day["site"].map(ZONE_HOURS).to_numpy()
        for pol in POLICIES:
            vals = policy_values(day, pol)
            items = [
                {"id": str(i), "value": float(v), "hours": int(h)}
                for i, (v, h) in enumerate(zip(vals, hours, strict=True))
            ]
            ids, _, used = knapsack_select(items, budget)
            chosen = [int(i) for i in ids]
            rows.append(
                {
                    "date": d,
                    "policy": pol,
                    "covered": int(day.loc[chosen, "event"].sum()),
                    "hours": used,
                    "events_available": int(day["event"].sum()),
                }
            )
    return pd.DataFrame(rows)


def summarize(alloc: pd.DataFrame, n_boot: int = N_BOOT, seed: int = SEED) -> pd.DataFrame:
    wide = alloc.pivot_table(index="date", columns="policy", values=["covered", "hours"], aggfunc="sum")
    dates = pd.Series(wide.index)
    blocks = week_blocks(dates)
    nb = blocks.max() + 1
    members = [np.flatnonzero(blocks == b) for b in range(nb)]
    rng = np.random.default_rng(seed)
    boots = [np.concatenate([members[i] for i in rng.integers(0, nb, nb)]) for _ in range(n_boot)]
    cov = {p: wide["covered"][p].to_numpy() for p in POLICIES}
    hrs = {p: wide["hours"][p].to_numpy() for p in POLICIES}
    out = []
    for p in POLICIES:

        def stats(idx: np.ndarray, p: str = p) -> tuple[float, float, float]:
            c, h, o = cov[p][idx].sum(), hrs[p][idx].sum(), cov["oracle"][idx].sum()
            return c / h if h else np.nan, c / o if o else np.nan, float(o - c)

        point = stats(np.arange(len(dates)))
        b = np.array([stats(i) for i in boots])
        rec = {
            "policy": p,
            "days": len(dates),
            "events_covered": int(cov[p].sum()),
            "crew_hours": int(hrs[p].sum()),
            "covered_per_crew_hour": point[0],
            "share_of_oracle": point[1],
            "regret_events": point[2],
        }
        for j, name in enumerate(["covered_per_crew_hour", "share_of_oracle", "regret_events"]):
            rec[f"{name}_lo"], rec[f"{name}_hi"] = ci(b[:, j])
        for ref in ("reactive", "climatology"):  # paired differences in share of oracle (same resampled weeks)
            if p == ref:
                continue
            d_pt = point[1] - stats(np.arange(len(dates)), ref)[1]
            lo, hi = ci(np.array([stats(i)[1] - stats(i, ref)[1] for i in boots]))
            rec[f"share_minus_{ref}"] = d_pt
            rec[f"share_minus_{ref}_lo"], rec[f"share_minus_{ref}_hi"] = lo, hi
            rec[f"share_minus_{ref}_significant"] = bool(lo > 0 or hi < 0)
        out.append(rec)
    return pd.DataFrame(out)


def run(preds: pd.DataFrame, tag: str, n_boot: int = N_BOOT) -> pd.DataFrame:
    frames = []
    for lead in BOOKING_LEADS:
        for budget in BUDGETS:
            s = summarize(allocate(preds, lead, budget), n_boot=n_boot)
            frames.append(s.assign(booking_lead=lead, budget_hours=budget))
    res = pd.concat(frames, ignore_index=True)
    res.insert(0, "label", LABEL)
    OUT.mkdir(parents=True, exist_ok=True)
    res.to_csv(OUT / f"backtest_{tag}.csv", index=False, float_format="%.4f")
    meta = {
        "label": LABEL,
        "zone_hours": ZONE_HOURS,
        "zone_weight": ZONE_WEIGHT,
        "budgets": BUDGETS,
        "booking_leads": BOOKING_LEADS,
        "policies": POLICIES,
        "n_boot": n_boot,
        "seed": SEED,
        "candidate_zones": "sites with an observation on the target day (limitation)",
        "knapsack": "decision.knapsack.knapsack_select, ported from Costa (nareshrajesh787, Avisator1)",
    }
    (OUT / f"backtest_{tag}_meta.json").write_text(json.dumps(meta, indent=1) + "\n")
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--preds",
        type=Path,
        required=True,
        help="parquet with site,date,lead,event,last_event,event_rate_7d,B1,M2,M2_fc",
    )
    ap.add_argument("--tag", required=True, help="e.g. val2024 or test")
    ap.add_argument("--n-boot", type=int, default=N_BOOT)
    a = ap.parse_args()
    res = run(pd.read_parquet(a.preds), a.tag, a.n_boot)
    show = res[res.booking_lead == 2][
        [
            "budget_hours",
            "policy",
            "share_of_oracle",
            "share_of_oracle_lo",
            "share_of_oracle_hi",
            "share_minus_climatology",
            "share_minus_climatology_lo",
            "share_minus_climatology_hi",
        ]
    ]
    print(LABEL)
    print(show.to_string(index=False, float_format=lambda v: f"{v:.3f}"))


if __name__ == "__main__":
    main()
