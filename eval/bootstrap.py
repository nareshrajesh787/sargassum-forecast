"""Weekly block bootstrap (SPEC: 1,000 resamples, because neighbouring days are not independent).

Blocks are ISO weeks of the *target* date, pooled across sites and leads, so all rows that share a
week are resampled together. The same resampled weeks are used for every model, which makes model
differences *paired*. A difference "counts" only if its 95% percentile interval excludes zero.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd

N_BOOT = 1000
SEED = 20261110
ALPHA = 0.05


def week_blocks(dates: pd.Series) -> np.ndarray:
    iso = pd.DatetimeIndex(dates).isocalendar()
    key = iso["year"].astype(int).to_numpy() * 100 + iso["week"].astype(int).to_numpy()
    _, codes = np.unique(key, return_inverse=True)
    return np.asarray(codes)


def resample_indices(blocks: np.ndarray, n_boot: int = N_BOOT, seed: int = SEED) -> list[np.ndarray]:
    """Row-index arrays for each bootstrap replicate (weeks drawn with replacement)."""
    rng = np.random.default_rng(seed)
    uniq = np.unique(blocks)
    members = [np.flatnonzero(blocks == b) for b in uniq]
    out = []
    for _ in range(n_boot):
        pick = rng.integers(0, len(uniq), len(uniq))
        out.append(np.concatenate([members[i] for i in pick]))
    return out


def ci(samples: np.ndarray, alpha: float = ALPHA) -> tuple[float, float]:
    s = np.asarray(samples, float)
    s = s[np.isfinite(s)]
    if len(s) == 0:
        return float("nan"), float("nan")
    return float(np.quantile(s, alpha / 2)), float(np.quantile(s, 1 - alpha / 2))


def bootstrap_stat(idx: list[np.ndarray], fn: Callable[[np.ndarray], float]) -> np.ndarray:
    return np.array([fn(i) for i in idx])
