"""Probabilistic verification metrics (Brier, BSS, ROC-AUC, PR-AUC, reliability)."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score


def brier(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean((np.asarray(p, float) - np.asarray(y, float)) ** 2))


def bss(bs_model: float, bs_ref: float) -> float:
    """Brier skill score of a model against a reference forecast (1 = perfect, 0 = no better, < 0 worse)."""
    return float(1.0 - bs_model / bs_ref) if bs_ref > 0 else float("nan")


def roc_auc(y: np.ndarray, p: np.ndarray) -> float:
    y = np.asarray(y)
    if y.min() == y.max():
        return float("nan")
    return float(roc_auc_score(y, p))


def pr_auc(y: np.ndarray, p: np.ndarray) -> float:
    """Average precision (area under the precision–recall curve). Its no-skill level is the base rate."""
    y = np.asarray(y)
    if y.max() == 0:
        return float("nan")
    return float(average_precision_score(y, p))


def reliability(y: np.ndarray, p: np.ndarray, n_bins: int = 10) -> pd.DataFrame:
    """Equal-width bins on [0, 1]: mean forecast, observed frequency and count per non-empty bin."""
    y = np.asarray(y, float)
    p = np.asarray(p, float)
    edges = np.linspace(0, 1, n_bins + 1)
    b = np.clip(np.digitize(p, edges[1:-1]), 0, n_bins - 1)
    rows = []
    for k in range(n_bins):
        m = b == k
        if m.any():
            rows.append(
                {
                    "bin": k,
                    "bin_lo": edges[k],
                    "bin_hi": edges[k + 1],
                    "p_mean": float(p[m].mean()),
                    "obs_freq": float(y[m].mean()),
                    "n": int(m.sum()),
                }
            )
    return pd.DataFrame(rows)
