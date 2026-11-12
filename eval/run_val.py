"""Validation-season evaluation (2024 only before Gate 4) → ``outputs/results_val*.csv`` + figures.

Tables
  results_val.csv           model × lead (1, 2, 3, 5, 7, all): n, base rate, Brier, BSS vs B0 and B1,
                            ROC-AUC, PR-AUC, each with weekly-block-bootstrap 95% CIs (1,000 resamples)
  results_val_paired.csv    Brier(model) − Brier(reference) for reference B0 and B1, paired over the same
                            resampled weeks. ``significant`` = CI excludes 0
  results_val_by_site.csv   the same metrics per site, leads pooled
  reliability_val.csv       reliability bins per model × lead
  results_val_train2019.csv sensitivity: training seasons 2019–2023 instead of the default 2020–2023
  wind_pp_vs_fc_val.csv     correlation of perfect-prog vs lead-L forecast onshore wind, by lead
Figures (outputs/figures): skill_vs_lead_val.png, reliability_val.png

"perfect_prog" = the model uses drivers valid on the target day (upper bound, FEASIBILITY §7).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from eval.bootstrap import N_BOOT, SEED, ci, week_blocks
from eval.metrics import brier, bss, pr_auc, reliability, roc_auc
from models.baselines import fit_all, predict_all
from pipeline.features.build import FEATURE_VERSION, check_seasons

FEATURES = Path(f"data/features/v{FEATURE_VERSION}/features.parquet")
OUT = Path("outputs")
VAL_SEASONS = [2024]
TRAIN_DEFAULT = [2020, 2021, 2022, 2023]  # G1 default: 2019 used a different FIU form
TRAIN_WITH_2019 = [2019, 2020, 2021, 2022, 2023]
LEADS = [1, 2, 3, 5, 7]
MODELS = {
    "B0": ("persistence", False),
    "B1": ("climatology", False),
    "B2": ("SIR-style AFAI index", False),
    "B3": ("B2 + onshore wind", True),
    "B3_fc": ("B2 + onshore wind, lead-L forecast winds", False),
}


def _subsets(df: pd.DataFrame) -> list[tuple[str, np.ndarray]]:
    subs: list[tuple[str, np.ndarray]] = [(str(L), (df["lead"] == L).to_numpy()) for L in LEADS]
    subs.append(("all", np.ones(len(df), bool)))
    return subs


def evaluate(
    df: pd.DataFrame,
    preds: pd.DataFrame,
    models: list[str],
    group_col: str | None = None,
    n_boot: int = N_BOOT,
    seed: int = SEED,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Point estimates + paired weekly-block bootstrap CIs. Returns (metrics table, paired-diff table)."""
    y_all = df["event"].to_numpy()
    weeks = week_blocks(df["date"])
    n_weeks = weeks.max() + 1
    rng = np.random.default_rng(seed)
    picks = [rng.integers(0, n_weeks, n_weeks) for _ in range(n_boot)]
    rows, prow = [], []
    groups: list[tuple[str, np.ndarray]] = [("all", np.ones(len(df), bool))]
    if group_col:
        groups = [(str(g), (df[group_col] == g).to_numpy()) for g in sorted(df[group_col].unique())]
    for gname, gmask in groups:
        for lead_name, lmask in _subsets(df) if not group_col else [("all", np.ones(len(df), bool))]:
            m = gmask & lmask
            if not m.any():
                continue
            rows_idx = np.flatnonzero(m)
            members = [rows_idx[weeks[rows_idx] == w] for w in range(n_weeks)]
            boot_idx = [np.concatenate([members[w] for w in p]) for p in picks]
            y = y_all[rows_idx]
            P = {k: preds[k].to_numpy() for k in models}
            ok = {k: np.isfinite(P[k][rows_idx]).all() for k in models}
            point_bs = {k: brier(y, P[k][rows_idx]) for k in models if ok[k]}
            boot_bs = {k: np.array([brier(y_all[i], P[k][i]) for i in boot_idx]) for k in models if ok[k]}
            boot_auc = {k: np.array([roc_auc(y_all[i], P[k][i]) for i in boot_idx]) for k in models if ok[k]}
            point_auc = {k: roc_auc(y, P[k][rows_idx]) for k in models if ok[k]}
            for k in models:
                if not ok[k]:
                    continue
                p = P[k][rows_idx]
                auc_b = boot_auc[k]
                pr_b = np.array([pr_auc(y_all[i], P[k][i]) for i in boot_idx])
                rec: dict[str, object] = {
                    "group": gname,
                    "lead": lead_name,
                    "model": k,
                    "description": MODELS.get(k, ("", False))[0],
                    "perfect_prog": MODELS.get(k, ("", False))[1],
                    "n": int(m.sum()),
                    "events": int(y.sum()),
                    "base_rate": float(y.mean()),
                    "brier": point_bs[k],
                }
                rec["brier_lo"], rec["brier_hi"] = ci(boot_bs[k])
                for ref in ("B0", "B1"):
                    if ref in point_bs:
                        rec[f"bss_{ref}"] = bss(point_bs[k], point_bs[ref])
                        rec[f"bss_{ref}_lo"], rec[f"bss_{ref}_hi"] = ci(1 - boot_bs[k] / boot_bs[ref])
                rec["auc"] = roc_auc(y, p)
                rec["auc_lo"], rec["auc_hi"] = ci(auc_b)
                rec["pr_auc"] = pr_auc(y, p)
                rec["pr_auc_lo"], rec["pr_auc_hi"] = ci(pr_b)
                rows.append(rec)
                for ref in ("B0", "B1"):
                    if ref == k or ref not in point_bs:
                        continue
                    lo, hi = ci(boot_bs[k] - boot_bs[ref])
                    alo, ahi = ci(boot_auc[k] - boot_auc[ref])
                    prow.append(
                        {
                            "group": gname,
                            "lead": lead_name,
                            "model": k,
                            "reference": ref,
                            "brier_diff": point_bs[k] - point_bs[ref],
                            "diff_lo": lo,
                            "diff_hi": hi,
                            "significant": bool(lo > 0 or hi < 0),
                            "verdict": "better" if hi < 0 else ("worse" if lo > 0 else "no detectable difference"),
                            "auc_diff": point_auc[k] - point_auc[ref],
                            "auc_diff_lo": alo,
                            "auc_diff_hi": ahi,
                            "auc_significant": bool(alo > 0 or ahi < 0),
                            "auc_verdict": "better"
                            if alo > 0
                            else ("worse" if ahi < 0 else "no detectable difference"),
                        }
                    )
    return pd.DataFrame(rows), pd.DataFrame(prow)


def run(train_seasons: list[int], features: Path = FEATURES) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    check_seasons(train_seasons + VAL_SEASONS, allow_test=False)
    df = pd.read_parquet(features)
    if set(df["season"].unique()) & {2025, 2026}:
        raise AssertionError("feature store contains test seasons")
    tr = df[df["season"].isin(train_seasons)].reset_index(drop=True)
    va = df[df["season"].isin(VAL_SEASONS)].reset_index(drop=True)
    fitted = fit_all(tr)
    preds = predict_all(fitted, va)
    return va, preds, pd.DataFrame({"train_seasons": [",".join(map(str, train_seasons))]})


def figures(res: pd.DataFrame, rel: pd.DataFrame, out: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    colors = {"B0": "#2a78d6", "B1": "#eb6834", "B2": "#1baf7a", "B3": "#eda100", "B3_fc": "#e87ba4"}
    markers = {"B0": "o", "B1": "s", "B2": "^", "B3": "D", "B3_fc": "v"}
    ink, muted, grid, axis = "#0b0b0b", "#898781", "#e1e0d9", "#c3c2b7"
    plt.rcParams.update(
        {
            "font.size": 10,
            "axes.edgecolor": axis,
            "axes.labelcolor": "#52514e",
            "xtick.color": muted,
            "ytick.color": muted,
            "axes.facecolor": "#fcfcfb",
            "figure.facecolor": "#fcfcfb",
        }
    )
    out.mkdir(parents=True, exist_ok=True)

    # Skill vs lead: BSS vs B1 (climatology) with 95% CIs
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    r = res[(res.group == "all") & (res.lead != "all")].copy()
    r["L"] = r["lead"].astype(int)
    offsets = {k: (i - 2) * 0.12 for i, k in enumerate(colors)}
    ends: list[tuple[float, str, float]] = []
    for k, c in colors.items():
        s = r[r.model == k].sort_values("L")
        if s.empty:
            continue
        x = s.L + offsets[k]
        ax.errorbar(
            x,
            s.bss_B1,
            yerr=[s.bss_B1 - s.bss_B1_lo, s.bss_B1_hi - s.bss_B1],
            color=c,
            marker=markers[k],
            markersize=6,
            lw=2,
            elinewidth=1.2,
            capsize=0,
            label=k,
        )
        ends.append((float(s.bss_B1.iloc[-1]), f"{k}{' (pp)' if MODELS[k][1] else ''}", float(x.iloc[-1])))
    # direct labels at the line ends, nudged apart so they never overlap
    ends.sort()
    span = ax.get_ylim()[1] - ax.get_ylim()[0]
    placed: list[float] = []
    for yv, text, xv in ends:
        yl = yv if not placed else max(yv, placed[-1] + 0.06 * span)
        placed.append(yl)
        ax.annotate(text, (xv + 0.15, yl), color=ink, fontsize=9, va="center")
    ax.axhline(0, color=axis, lw=1)
    ax.set_xticks(LEADS)
    ax.set_xlim(0.5, 8.4)
    ax.set_xlabel("Lead (days)")
    ax.set_ylabel("Brier skill vs B1 (climatology)")
    ax.set_title("Validation 2024: skill vs lead, 95% weekly-block CIs", color=ink, loc="left", fontsize=11)
    ax.grid(axis="y", color=grid, lw=0.6)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, fontsize=8, ncol=5, loc="upper left", bbox_to_anchor=(0, -0.15))
    fig.tight_layout()
    fig.savefig(out / "skill_vs_lead_val.png", dpi=150)
    plt.close(fig)

    # Reliability (leads pooled), small multiples
    ms = [k for k in colors if k in set(rel.model)]
    fig, axes = plt.subplots(1, len(ms), figsize=(3.0 * len(ms), 3.2), sharey=True)
    for ax, k in zip(np.atleast_1d(axes), ms, strict=True):
        s = rel[(rel.model == k) & (rel.lead == "all")]
        ax.plot([0, 1], [0, 1], color=axis, lw=1)
        ax.plot(s.p_mean, s.obs_freq, color=colors[k], marker=markers[k], lw=2, markersize=6)
        for _, b in s.iterrows():
            ax.annotate(
                f"{int(b.n)}",
                (b.p_mean, b.obs_freq),
                textcoords="offset points",
                xytext=(4, -10),
                fontsize=7,
                color=muted,
            )
        ax.set_title(f"{k}{' (perfect-prog)' if MODELS[k][1] else ''}", fontsize=9, color=ink, loc="left")
        ax.set_xlim(0, 0.7)
        ax.set_ylim(0, 0.7)
        ax.set_xlabel("Forecast probability")
        ax.grid(color=grid, lw=0.6)
        ax.spines[["top", "right"]].set_visible(False)
    np.atleast_1d(axes)[0].set_ylabel("Observed frequency")
    fig.suptitle(
        "Validation 2024 reliability (all leads; numbers = rows per bin)", x=0.01, ha="left", fontsize=10, color=ink
    )
    fig.tight_layout()
    fig.savefig(out / "reliability_val.png", dpi=150)
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-boot", type=int, default=N_BOOT)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    models = list(MODELS)

    va, preds, _ = run(TRAIN_DEFAULT)
    res, paired = evaluate(va, preds, models, n_boot=a.n_boot)
    res.to_csv(OUT / "results_val.csv", index=False, float_format="%.4f")
    paired.to_csv(OUT / "results_val_paired.csv", index=False, float_format="%.4f")
    by_site, _ = evaluate(va, preds, models, group_col="site", n_boot=a.n_boot)
    by_site.to_csv(OUT / "results_val_by_site.csv", index=False, float_format="%.4f")
    rel = []
    for k in models:
        for lead_name, m in _subsets(va):
            p = preds[k].to_numpy()[m]
            if np.isfinite(p).all():
                rel.append(reliability(va["event"].to_numpy()[m], p).assign(model=k, lead=lead_name))
    rel_df = pd.concat(rel, ignore_index=True)
    rel_df.to_csv(OUT / "reliability_val.csv", index=False, float_format="%.4f")

    va19, preds19, _ = run(TRAIN_WITH_2019)
    sens, _ = evaluate(va19, preds19, ["B0", "B1", "B2"], n_boot=a.n_boot)
    sens.assign(train_seasons="2019-2023").to_csv(OUT / "results_val_train2019.csv", index=False, float_format="%.4f")

    w = va[va.wind_fc_onshore.notna()]
    corr = pd.Series({L: g.wind_pp_onshore.corr(g.wind_fc_onshore) for L, g in w.groupby("lead")})
    g = w.groupby("lead")
    pd.DataFrame(
        {
            "lead": corr.index,
            "corr_pp_vs_fc_onshore_wind": corr.values,
            "n": g.size().values,
            "mean_pp_onshore_ms": g.wind_pp_onshore.mean().values,
            "mean_fc_onshore_ms": g.wind_fc_onshore.mean().values,
        }
    ).to_csv(OUT / "wind_pp_vs_fc_val.csv", index=False, float_format="%.4f")

    figures(res, rel_df, OUT / "figures")
    meta = {
        "train_seasons": TRAIN_DEFAULT,
        "val_seasons": VAL_SEASONS,
        "n_boot": a.n_boot,
        "seed": SEED,
        "feature_version": FEATURE_VERSION,
        "models": {k: v[0] for k, v in MODELS.items()},
        "perfect_prog_models": [k for k, v in MODELS.items() if v[1]],
    }
    (OUT / "results_val_meta.json").write_text(json.dumps(meta, indent=1) + "\n")
    show = res[res.group == "all"][
        ["model", "lead", "brier", "bss_B0", "bss_B1", "bss_B1_lo", "bss_B1_hi", "auc", "auc_lo", "auc_hi"]
    ]
    print(show.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    print(paired[paired.lead == "all"].to_string(index=False, float_format=lambda v: f"{v:.4f}"))


if __name__ == "__main__":
    main()
