"""Test-season figures (skill vs lead, reliability). Colours: validated categorical slots 1–6 in fixed order
(dataviz reference palette; contrast WARN relieved by direct labels, distinct markers and the CSV tables)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

MODELS = ["B0", "B1", "B3", "P1", "M1", "M2"]
COLORS = dict(zip(MODELS, ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"], strict=True))
MARKERS = dict(zip(MODELS, ["o", "s", "^", "D", "v", "P"], strict=True))
INK, MUTED, GRID, AXIS = "#0b0b0b", "#898781", "#e1e0d9", "#c3c2b7"
LEADS = [1, 2, 3, 5, 7]
PP_NOTE = "B3, P1, M1, M2 use target-day drivers (perfect-prog upper bound)"


def _style() -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update(
        {
            "font.size": 10,
            "axes.edgecolor": AXIS,
            "axes.labelcolor": "#52514e",
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "axes.facecolor": "#fcfcfb",
            "figure.facecolor": "#fcfcfb",
        }
    )


def _end_labels(ax, ends: list[tuple[float, str, float]]) -> None:  # type: ignore[no-untyped-def]
    ends.sort()
    span = ax.get_ylim()[1] - ax.get_ylim()[0]
    placed: list[float] = []
    for yv, text, xv in ends:
        yl = yv if not placed else max(yv, placed[-1] + 0.06 * span)
        placed.append(yl)
        ax.annotate(text, (xv + 0.2, yl), color=INK, fontsize=8, va="center")


def test_figures(res: pd.DataFrame, rel: pd.DataFrame, out: Path) -> None:
    _style()
    import matplotlib.pyplot as plt

    out.mkdir(parents=True, exist_ok=True)
    seasons = ["2025", "2026", "2025-2026"]
    r = res[res.lead != "all"].copy()
    r["L"] = r["lead"].astype(int)
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.2), sharey=True)
    for ax, s in zip(axes, seasons, strict=True):
        ends = []
        for i, k in enumerate(MODELS):
            d = r[(r.season == s) & (r.model == k)].sort_values("L")
            if d.empty:
                continue
            x = d.L + (i - 2.5) * 0.1
            ax.errorbar(
                x,
                d.bss_B1,
                yerr=[d.bss_B1 - d.bss_B1_lo, d.bss_B1_hi - d.bss_B1],
                color=COLORS[k],
                marker=MARKERS[k],
                markersize=6,
                lw=2,
                elinewidth=1.1,
                capsize=0,
                label=k,
            )
            ends.append((float(d.bss_B1.iloc[-1]), k, float(x.iloc[-1])))
        ax.axhline(0, color=AXIS, lw=1)
        ax.set_xticks(LEADS)
        ax.set_xlim(0.5, 8.6)
        ax.set_title(f"Test {s}", loc="left", fontsize=10, color=INK)
        ax.set_xlabel("Lead (days)")
        ax.grid(axis="y", color=GRID, lw=0.6)
        ax.spines[["top", "right"]].set_visible(False)
        _end_labels(ax, ends)
    axes[0].set_ylabel("Brier skill vs B1 (climatology)")
    axes[0].legend(frameon=False, fontsize=8, ncol=6, loc="upper left", bbox_to_anchor=(0, -0.16))
    fig.suptitle(
        f"Skill vs lead on held-out seasons, 95% weekly-block CIs. {PP_NOTE}", x=0.01, ha="left", fontsize=10, color=INK
    )
    fig.tight_layout()
    fig.savefig(out / "skill_vs_lead_test.png", dpi=150)
    plt.close(fig)

    show = ["B0", "B1", "P1", "M1", "M2"]
    fig, axes = plt.subplots(
        len(seasons), len(show), figsize=(3.0 * len(show), 3.0 * len(seasons)), sharex=True, sharey=True
    )
    for i, s in enumerate(seasons):
        for j, k in enumerate(show):
            ax = axes[i, j]
            d = rel[(rel.season == s) & (rel.model == k) & (rel.lead == "all")]
            ax.plot([0, 1], [0, 1], color=AXIS, lw=1)
            ax.plot(d.p_mean, d.obs_freq, color=COLORS[k], marker=MARKERS[k], lw=2, markersize=6)
            for _, b in d.iterrows():
                ax.annotate(
                    f"{int(b.n)}",
                    (b.p_mean, b.obs_freq),
                    textcoords="offset points",
                    xytext=(4, -10),
                    fontsize=6,
                    color=MUTED,
                )
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            ax.grid(color=GRID, lw=0.6)
            ax.spines[["top", "right"]].set_visible(False)
            if i == 0:
                ax.set_title(k, loc="left", fontsize=9, color=INK)
            if j == 0:
                ax.set_ylabel(f"{s}\nobserved frequency")
            if i == len(seasons) - 1:
                ax.set_xlabel("Forecast probability")
    fig.suptitle(
        "Reliability on held-out seasons (all leads; numbers = rows per bin)", x=0.01, ha="left", fontsize=10, color=INK
    )
    fig.tight_layout()
    fig.savefig(out / "reliability_test.png", dpi=150)
    plt.close(fig)
    _ = np
