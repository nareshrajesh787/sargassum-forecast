"""Knapsack: Costa's original tests, brute-force equality on random cases, the budget-monotonicity property,
and the TypeScript fixture staying in sync with Python."""

from __future__ import annotations

import json
import random
from typing import Any

import pytest

from decision.knapsack import brute_force, knapsack_select
from decision.make_fixture import FIXTURE, cases

COSTA_ITEMS: list[dict[str, Any]] = [
    {"id": "a", "value": 100, "hours": 3},
    {"id": "b", "value": 90, "hours": 3},
    {"id": "c", "value": 80, "hours": 2},
    {"id": "d", "value": 70, "hours": 4},
    {"id": "e", "value": 40, "hours": 2},
    {"id": "f", "value": 10, "hours": 1},
]


def test_costa_knapsack_never_exceeds_budget_and_matches_brute_force() -> None:
    by_id = {i["id"]: i for i in COSTA_ITEMS}
    for budget in range(0, 13):
        ids, value, hours = knapsack_select(COSTA_ITEMS, budget)
        assert hours <= budget
        assert abs(sum(by_id[i]["value"] for i in ids) - value) < 1e-9
        o_ids, o_value, o_hours = brute_force(COSTA_ITEMS, budget)
        assert frozenset(ids) == o_ids and abs(value - o_value) < 1e-9 and hours == o_hours


def test_costa_tiny_set_max_value() -> None:
    items = [
        {"id": "high", "value": 50, "hours": 5},
        {"id": "mid_a", "value": 32, "hours": 3},
        {"id": "mid_b", "value": 31, "hours": 3},
        {"id": "cheap", "value": 18, "hours": 2},
    ]
    ids, value, _ = knapsack_select(items, 8)
    _, o_value, _ = brute_force(items, 8)
    assert abs(value - o_value) < 1e-9


def _random_items(rng: random.Random, ties: bool) -> list[dict]:
    return [
        {"id": f"z{j}", "value": rng.randint(0, 3) if ties else rng.random(), "hours": rng.randint(1, 5)}
        for j in range(rng.randint(0, 10))
    ]


@pytest.mark.parametrize("ties", [False, True])
def test_brute_force_equality_on_random_cases(ties: bool) -> None:
    rng = random.Random(7 + ties)
    for _ in range(300):
        items, budget = _random_items(rng, ties), rng.randint(0, 20)
        ids, value, hours = knapsack_select(items, budget)
        o_ids, o_value, o_hours = brute_force(items, budget)
        assert abs(value - o_value) < 1e-9 and hours == o_hours and hours <= budget
        if not ties:  # continuous values: the optimum is unique, so the sets must match too
            assert frozenset(ids) == o_ids


def test_more_budget_never_lowers_value() -> None:
    rng = random.Random(11)
    for _ in range(300):
        items = _random_items(rng, ties=rng.random() < 0.5)
        values = [knapsack_select(items, b)[1] for b in range(0, 25)]
        assert all(b >= a - 1e-12 for a, b in zip(values, values[1:], strict=False))


def test_rejects_bad_input() -> None:
    with pytest.raises(ValueError):
        knapsack_select(COSTA_ITEMS, -1)
    with pytest.raises(ValueError):
        knapsack_select([{"id": "x", "value": 1, "hours": 0}], 3)


def test_typescript_fixture_matches_python() -> None:
    committed = json.loads(FIXTURE.read_text())["cases"]
    assert committed == cases(), "regenerate with `uv run python -m decision.make_fixture`"
