"""Collect every ``outputs/spike/s*.json`` into ``outputs/spike/comparison.csv`` (one row per metric)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

OUT = Path("outputs/spike")


def main() -> None:
    rows = []
    for p in sorted(OUT.glob("s*.json")):
        d = json.loads(p.read_text())
        for r in d["results"]:
            rows.append(
                {
                    "script": d["script"],
                    "test": d["test"],
                    "metric": r["metric"],
                    "spike": r.get("spike"),
                    "rerun": r.get("rerun"),
                    "flag_gt_tol": r.get("flag_gt_tol"),
                    "touches_test_seasons": d.get("touches_test_seasons", False),
                }
            )
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "comparison.csv", index=False)
    compared = df[df.flag_gt_tol.notna()]
    print(
        f"{len(df)} metrics, {len(compared)} with a spike value, {int(compared.flag_gt_tol.astype(bool).sum())} "
        "flagged (> tolerance)"
    )
    print(compared[compared.flag_gt_tol.astype(bool)][["script", "metric", "spike", "rerun"]].to_string(index=False))


if __name__ == "__main__":
    main()
