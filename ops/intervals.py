"""Empirical 80% interval for served probabilities (SPEC API: "probability, 80% interval").

The frozen M2 has no native predictive interval. For each M2 probability bin (width ``BIN``) this computes the
observed event frequency on the test seasons 2025–2026 and its 10th–90th percentile over a weekly block bootstrap
(1,000 resamples). The served interval answers: "in 2025–2026, when M2 said about this much, how often did it
happen?" Because M2 under-forecast the record test years, the interval often sits *above* the probability. That is
intentional: it carries the known calibration error to users.

Output: ``outputs/m2_interval_table.csv`` (committed; read by the daily job).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from eval.bootstrap import N_BOOT, SEED, week_blocks

BIN = 0.05
OUT = Path("outputs/m2_interval_table.csv")


def table(preds: pd.DataFrame, col: str = "M2", n_boot: int = N_BOOT, seed: int = SEED) -> pd.DataFrame:
    p = preds.reset_index(drop=True)
    b = np.minimum((p[col].to_numpy() / BIN).astype(int), int(1 / BIN) - 1)
    blocks = week_blocks(p["date"])
    nb = blocks.max() + 1
    members = [np.flatnonzero(blocks == k) for k in range(nb)]
    rng = np.random.default_rng(seed)
    boots = [np.concatenate([members[i] for i in rng.integers(0, nb, nb)]) for _ in range(n_boot)]
    y = p["event"].to_numpy()
    rows = []
    for k in np.unique(b):
        m = b == k
        freq = []
        for idx in boots:
            mm = m[idx]
            if mm.sum():
                freq.append(y[idx][mm].mean())
        rows.append(
            {
                "bin_lo": k * BIN,
                "bin_hi": (k + 1) * BIN,
                "n": int(m.sum()),
                "mean_forecast": float(p[col][m].mean()),
                "observed_freq": float(y[m].mean()),
                "obs_p10": float(np.quantile(freq, 0.10)),
                "obs_p90": float(np.quantile(freq, 0.90)),
            }
        )
    return pd.DataFrame(rows)


def lookup(tab: pd.DataFrame, prob: float) -> tuple[float, float]:
    k = min(int(prob / BIN), int(1 / BIN) - 1)
    row = tab[np.isclose(tab.bin_lo, k * BIN)]
    if row.empty:  # bin unseen on test: fall back to the nearest seen bin
        row = tab.iloc[[int(np.argmin(np.abs(tab.bin_lo.to_numpy() - k * BIN)))]]
    return float(row.obs_p10.iloc[0]), float(row.obs_p90.iloc[0])


def main() -> None:
    preds = pd.read_parquet("data/test_lock/preds_test.parquet")
    t = table(preds)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    t.to_csv(OUT, index=False, float_format="%.4f")
    print(t.to_string(index=False, float_format=lambda v: f"{v:.3f}"))


if __name__ == "__main__":
    main()
