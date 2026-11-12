"""Write 1,000 random knapsack cases with the Python results to ``web/lib/__fixtures__/knapsack_cases.json``.

The TypeScript port (``web/lib/knapsack.ts``) is tested against this file. ``tests/test_knapsack.py``
checks that the committed file still matches the Python implementation.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from decision.knapsack import knapsack_select

FIXTURE = Path("web/lib/__fixtures__/knapsack_cases.json")
SEED = 20261111
N_CASES = 1000


def cases(seed: int = SEED, n: int = N_CASES) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    out = []
    for k in range(n):
        m = rng.randint(0, 10)
        # every 4th case uses small integer values to force value ties
        items = [
            {
                "id": f"z{j}",
                "value": (rng.randint(0, 3) if k % 4 == 0 else round(rng.uniform(0, 1), 6)),
                "hours": rng.randint(1, 5),
            }
            for j in range(m)
        ]
        budget = rng.randint(0, 20)
        ids, value, hours = knapsack_select(items, budget)
        out.append({"items": items, "budget": budget, "expected": {"ids": ids, "value": value, "hours": hours}})
    return out


def main() -> None:
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(json.dumps({"seed": SEED, "cases": cases()}, separators=(",", ":")) + "\n")
    print(f"wrote {FIXTURE} ({N_CASES} cases)")


if __name__ == "__main__":
    main()
