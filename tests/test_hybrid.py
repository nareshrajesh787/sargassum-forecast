"""M1 design: ablation feature lists and leave-one-season-out stacking."""

from __future__ import annotations

import numpy as np
import pandas as pd

from models.hybrid import ABLATIONS, feature_list, stacked_baselines


def _frame(seasons: list[int], n: int = 40) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    rows = []
    for s in seasons:
        for i in range(n):
            rows.append(
                {
                    "season": s,
                    "date": pd.Timestamp(f"{s}-01-01") + pd.Timedelta(days=119 + i),
                    "site": "the_palms",
                    "lead": 1 + i % 2,
                    "doy": 120 + i,
                    "event": int(rng.random() < 0.3),
                    "last_event": float(rng.integers(0, 2)),
                    "afai1d_r50_anom": rng.normal(),
                    "wind_pp_onshore": rng.normal() if s >= 2022 else np.nan,
                    "wind_fc_onshore": np.nan,
                    "afai1d_band_recent7": rng.random(),
                    "p1_idx_window": rng.random(),
                }
            )
    return pd.DataFrame(rows)


def test_ablations_drop_families_and_derived_baselines() -> None:
    df = _frame([2022])
    full = set(feature_list(df, "full"))
    assert {"b2", "b3", "afai1d_band_recent7", "p1_idx_window"} <= full
    no_afai = set(feature_list(df, "no_afai"))
    assert not any(c.startswith("afai") for c in no_afai) and "b2" not in no_afai and "b3" not in no_afai
    no_wind = set(feature_list(df, "no_wind"))
    assert "wind_pp_onshore" not in no_wind and "b3" not in no_wind and "b2" in no_wind
    assert "p1_idx_window" not in set(feature_list(df, "no_p1"))
    assert set(ABLATIONS) == {"full", "no_p1", "no_afai", "no_wind", "fc"}


def test_stacking_is_leave_one_season_out() -> None:
    tr = _frame([2020, 2021, 2022, 2023])
    va = _frame([2024], n=10)
    # make 2023's labels extreme: an in-sample B1 would learn them, a held-out one cannot
    tr.loc[tr.season == 2023, "event"] = 1
    st, (v,) = stacked_baselines(tr, [va])
    b1_2023 = st.loc[st.season == 2023, "b1"].mean()
    assert b1_2023 < 0.9  # held-out fit never saw 2023's all-ones labels
    assert st.loc[st.season.isin([2020, 2021]), "b3"].isna().all()  # no wind before 2022 → NaN, not a crash
    assert v[["b0", "b1", "b2", "b3"]].notna().all().all()


def test_fc_ablation_is_leakage_safe_and_every_model_is_labelled() -> None:
    from eval.run_val import MODELS, model_info

    df = _frame([2022])
    for c in ["waves_pp_hs", "curr_pp_onshore", "p1_idx_cum"]:
        df[c] = 0.0
    fc = feature_list(df, "fc")
    assert not any(c.endswith("_pp") or "_pp_" in c or c.startswith("p1_") or c == "b3" for c in fc)
    for name in ["P1", "M1", "M2", "M1_no_p1", "M1_no_afai", "M1_no_wind", "M1_fc", "M2_fc"]:
        assert name in MODELS
    assert model_info("M2")[1] is True and model_info("M2_fc")[1] is False and model_info("P1")[1] is True
    import pytest

    with pytest.raises(KeyError):
        model_info("M9")
