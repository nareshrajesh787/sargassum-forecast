"""Spike row 6 (and the SPEC label-share table): severity counts over the latest 3,775 site reports."""

from __future__ import annotations

from spike.common import load_reports, write

N_LATEST = 3775
SPIKE_COUNTS = {0: 203, 1: 2508, 2: 805, 3: 259}
SPIKE_SHARES = {0: 0.05, 1: 0.66, 2: 0.21, 3: 0.07}
NAMES = {0: "none", 1: "present", 2: "moderate", 3: "heavy"}


def main() -> None:
    rep = load_reports()
    a = rep[rep.site.notna()].sort_values("created_at").tail(N_LATEST)
    vc = a.severity.value_counts(dropna=False)
    results = []
    for k in range(4):
        results.append({"metric": f"count_{NAMES[k]}", "spike": SPIKE_COUNTS[k], "rerun": int(vc.get(float(k), 0))})
    for k in range(4):
        results.append(
            {
                "metric": f"share_{NAMES[k]}",
                "spike": SPIKE_SHARES[k],
                "rerun": float(vc.get(float(k), 0) / len(a)),
            }
        )
    results.append({"metric": "count_unknown_severity", "spike": 0, "rerun": int(a.severity.isna().sum())})
    results.append({"metric": "event_share_(severity>=2)", "spike": 0.28, "rerun": float((a.severity >= 2).mean())})
    write(
        "s06_label_base_rates",
        "Broward label base rates (latest 3,775 site reports)",
        "The 3,775 most recently created reports assigned to one of the 8 sites; per-report severity with the "
        "frozen rules (precedence none_first). Reports, not site-days.",
        results,
        touches_test_seasons=True,
        notes=[
            f"date span of these reports: {a.obs_date.min().date()} .. {a.obs_date.max().date()}",
            "descriptive label counts only; no prediction is scored",
        ],
    )


if __name__ == "__main__":
    main()
