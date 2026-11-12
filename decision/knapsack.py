"""Exact 0/1 knapsack crew allocation.

Ported from ``knapsack_select`` in Costa (https://github.com/nareshrajesh787/Costa,
``backend/app/lib/algorithms.py``), by Costa's authors nareshrajesh787 and Avisator1. The algorithm, the
1e-12 value tolerance and the reconstruction are unchanged. The only changes are type hints, this header, and a
tie-break note.

Tie-break note: Costa's docstring promises "highest value, then fewer hours used, then lexicographic id
set". The DP guarantees the first two: ``best_w`` is the smallest capacity that reaches the best value, so the
chosen set uses the fewest hours among optimal sets. The id-set tie-break is not implemented (Costa's tie
branch is ``pass``). Tests therefore compare value and hours with brute force on all cases, and exact sets
only where no two subsets tie on value.
"""

from __future__ import annotations

from typing import Any


def knapsack_select(items: list[dict[str, Any]], budget: int) -> tuple[list[str], float, int]:
    """Exact 0/1 knapsack via DP.

    items: dicts with id, value (float), hours (positive int)
    Returns (selected_ids in stable catalog order, total_value, hours_used)
    """
    if budget < 0:
        raise ValueError("budget must be >= 0")
    if budget == 0 or not items:
        return [], 0.0, 0

    n = len(items)
    hours_list = []
    value_list = []
    for item in items:
        hours = int(item["hours"])
        if hours <= 0:
            raise ValueError(f"item {item.get('id')} has non-positive hours")
        hours_list.append(hours)
        value_list.append(float(item["value"]))

    # dp[i][w] = max value using the first i items with capacity w
    dp = [[0.0] * (budget + 1) for _ in range(n + 1)]
    take = [[False] * (budget + 1) for _ in range(n + 1)]

    for i in range(1, n + 1):
        hours = hours_list[i - 1]
        value = value_list[i - 1]
        for w in range(budget + 1):
            dp[i][w] = dp[i - 1][w]
            take[i][w] = False
            if hours <= w:
                candidate = dp[i - 1][w - hours] + value
                skip = dp[i][w]
                if candidate > skip + 1e-12:
                    dp[i][w] = candidate
                    take[i][w] = True

    best_w = max(range(budget + 1), key=lambda w: (dp[n][w], -w))
    selected_idx: list[int] = []
    w = best_w
    for i in range(n, 0, -1):
        if take[i][w]:
            selected_idx.append(i - 1)
            w -= hours_list[i - 1]

    selected_idx.sort()
    selected_ids = [items[i]["id"] for i in selected_idx]
    hours_used = sum(hours_list[i] for i in selected_idx)
    total_value = sum(value_list[i] for i in selected_idx)
    return selected_ids, total_value, hours_used


def brute_force(items: list[dict[str, Any]], budget: int) -> tuple[frozenset[str], float, int]:
    """Exhaustive reference (from Costa's tests): max value, then fewest hours, then lexicographic id set."""
    best_value, best_ids, best_hours = -1.0, frozenset[str](), 0
    for mask in range(1 << len(items)):
        ids, value, hours = [], 0.0, 0
        for i, item in enumerate(items):
            if mask & (1 << i):
                ids.append(item["id"])
                value += float(item["value"])
                hours += int(item["hours"])
        if hours > budget:
            continue
        s = frozenset(ids)
        if value > best_value + 1e-12 or (
            abs(value - best_value) <= 1e-12
            and (hours < best_hours or (hours == best_hours and tuple(sorted(s)) < tuple(sorted(best_ids))))
        ):
            best_value, best_ids, best_hours = value, s, hours
    return best_ids, best_value, best_hours
