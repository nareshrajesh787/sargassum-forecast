# Results — held-out test seasons 2025–2026

These are the held-out test seasons 2025 and 2026, scored once. The test set was unlocked at 2026-11-12T02:06:10Z with the frozen model
(sha256 c355696f…; `outputs/results_test_meta.json`). The target is a moderate-or-worse sargassum day (severity ≥ 2) at each of 8
Broward beaches, at leads of 1, 2, 3, 5 and 7 days. All intervals are 95% weekly-block bootstrap, 1,000 resamples (`eval/bootstrap.py`
`N_BOOT`; recorded in `outputs/results_val_meta.json`). A difference counts only if its interval excludes zero.

**Upper bound** marks models that use winds, waves, currents or drift forcing *valid on the target day*. These are analyses,
not forecasts available at the issue time (`perfect_prog` column): P1, M1, M2 and the M1 ablations. **Issue-time** models
use only data available when the forecast is made: B0, B1, B2, B3_fc, M1_fc and M2_fc.

## Headline

**Pooled over seasons and leads, no issue-time model beats climatology on the test seasons.** The only exception
anywhere in the per-season, per-lead table is persistence at a 1-day lead in 2026: B0 − B1 Brier −0.0103 [−0.0189,
−0.0013] (`results_test_paired.csv`).

| Model (2025–2026 pooled, leads pooled) | Kind | Brier skill vs B1 | Brier skill vs B0 | ROC-AUC |
| --- | --- | --- | --- | --- |
| B1 climatology | issue-time | 0 (reference) | 0.011 [−0.006, 0.028] | 0.701 [0.651, 0.743] |
| B0 persistence | issue-time | −0.011 [−0.029, 0.006] | 0 (reference) | 0.616 [0.578, 0.649] |
| B2 SIR-style AFAI index | issue-time | −0.078 [−0.106, −0.043] | −0.066 [−0.092, −0.036] | 0.535 [0.483, 0.587] |
| B3_fc: B2 + lead-L forecast onshore wind | issue-time | −0.025 [−0.059, 0.010] | −0.014 [−0.046, 0.022] | 0.575 [0.536, 0.614] |
| M1_fc: LightGBM, issue-time inputs | issue-time | −0.018 [−0.040, 0.005] | −0.006 [−0.024, 0.013] | 0.671 [0.620, 0.716] |
| M2_fc: M1_fc + isotonic calibration (2024) | issue-time | −0.103 [−0.136, −0.066] | −0.091 [−0.120, −0.058] | 0.666 [0.616, 0.710] |
| P1 Lagrangian drift alone | upper bound | −0.025 [−0.057, 0.004] | −0.014 [−0.038, 0.009] | 0.592 [0.551, 0.626] |
| M1 LightGBM hybrid, uncalibrated | upper bound | **0.064 [0.032, 0.096]** | **0.074 [0.043, 0.106]** | 0.724 [0.678, 0.767] |
| M2 = M1 + isotonic calibration (2024), the SPEC's user-facing model | upper bound | −0.034 [−0.058, −0.011] | −0.023 [−0.047, 0.001] | 0.720 [0.676, 0.762] |

Source: `outputs/results_test.csv`, rows with `season == "2025-2026"` and `lead == "all"`.

## Findings

1. **Validation results reversed on test.** On 2024, every hybrid beat climatology on Brier, including the issue-time M1_fc
   (−0.0065 [−0.0107, −0.0025]) and M2_fc (−0.0074 [−0.0121, −0.0030]). M2's BSS vs B1 was 0.105 [0.057, 0.162]
   (`results_val_hybrid_paired.csv`, `results_val_hybrid.csv`). Those validation scores are optimistic, because M1 was tuned and M2
   was calibrated on 2024. On test, M1_fc shows no detectable difference from B1 and M2_fc is worse.
2. **Calibration on one quiet season hurt.** The 2024 event rate was 0.092, against 0.198 in 2025 and 0.359 in 2026
   (`feasibility/fiu_season_stats.csv`). Isotonic calibration turns M1's +0.064 into −0.034. Paired, M2 is worse than B1: Brier +0.0070
   [+0.0021, +0.0125]. In 2026 every model's mean forecast is 0.127–0.206 against an observed event rate of 0.359. M2 is lowest, at 0.127
   (count-weighted means of `reliability_test.csv`, season 2026, all leads; `figures/reliability_test.png`).
3. **Skill over climatology needs target-day drivers.** M1 (upper bound) beats B1 on Brier, −0.0131 [−0.0205, −0.0060], but only
   in 2026 (−0.0241 [−0.0372, −0.0118]). In 2025 there is no detectable difference (−0.0019 [−0.0068, +0.0035]). M1 does not
   out-rank B1: AUC +0.0231 [−0.0067, +0.0549]. Without wind, M1 still beats B1 (−0.0065 [−0.0126, −0.0005]) using target-day waves,
   currents and P1. So the edge comes from target-day weather and ocean drivers generally, not wind alone. The issue-time
   M1_fc is worse than M1 (Brier +0.0167 [+0.0086, +0.0265]).
4. **Real forecast winds did not rescue the wind baseline.** B3_fc uses lead-L GFS forecast winds. Against B1 it shows no
   detectable Brier difference (+0.0051 [−0.0022, +0.0120]) and ranks worse (AUC −0.1256 [−0.1884, −0.0591]).
5. **The drift physics did not help.** Removing P1 from M1 changes nothing detectable (Brier +0.0004 [−0.0004, +0.0012]). P1 alone is
   worse than B1 at leads 5 and 7 (Brier +0.0161 [+0.0078, +0.0246] at both) and ranks below B1 pooled (AUC −0.1086 [−0.1534,
   −0.0654]). It also showed no detectable skill on validation (`results_val_p1_paired.csv`).
6. **Satellite AFAI alone is the weakest signal.** B2 is worse than B1 (Brier +0.0159 [+0.0081, +0.0239]; AUC 0.535). Inside M1,
   AFAI still contributes: removing it worsens Brier by +0.0029 [+0.0009, +0.0049], and removing wind worsens it by +0.0066 [+0.0020, +0.0125].
7. **Persistence is weaker than climatology.** B0 ranks below B1 pooled (AUC −0.0842 [−0.1111, −0.0549]). On Brier it is worse in 2025
   (+0.0070 [+0.0022, +0.0116]) and at leads 5 (+0.0047 [+0.0001, +0.0098]) and 7 (+0.0065 [+0.0012, +0.0123]). It beats B1 only at
   lead 1 in 2026.

## By season and lead

| Season | M1 BSS vs B1 (upper bound) | M2 BSS vs B1 (upper bound) | M1_fc BSS vs B1 (issue-time) | Event rate |
| --- | --- | --- | --- | --- |
| 2025 | 0.012 [−0.023, 0.045] | −0.026 [−0.063, 0.015] | −0.041 [−0.074, −0.007] | 0.198 |
| 2026 | 0.094 [0.052, 0.134] | −0.039 [−0.066, −0.008] | −0.005 [−0.031, 0.025] | 0.359 |

Per-lead skill is in `outputs/results_test.csv` (lead 1–7 rows) and `outputs/figures/skill_vs_lead_test.png`. M1's skill vs
B1 is roughly flat across leads, because its target-day drivers do not depend on lead. P1 degrades at leads 5 and 7.

## Decision backtest (SIMULATED)

The backtest uses the 8 sites with an exact knapsack (ported from Costa), budgets of 4–16 crew-hours and booking leads of 1, 2 and 3 days
(`backtest_test.csv`). The metric is the share of the oracle's event coverage, as a paired difference vs climatology. The "forecast" policy uses M2
(**upper bound**). "forecast_fc" uses M2_fc (issue-time).

- **Booking lead 2 days:**
  - Climatology beats reactive ("go where it was last reported") at every budget. For example, at 8 h reactive is −0.041 [−0.081, −0.001].
  - The M2 policy shows no detectable difference from climatology at any budget. At 8 h it is −0.017 [−0.047, +0.013].
  - M2_fc is worse at 14 h (−0.047 [−0.077, −0.017]) and 16 h (−0.037 [−0.065, −0.009]).
- **Booking lead 1 day:** M2 is worse than climatology at 14 h (−0.0358 [−0.0638, −0.0073]) and 16 h (−0.0243 [−0.0457, −0.0043]).
  M2_fc is worse at 12, 14 and 16 h.
- **Booking lead 3 days:** M2_fc is worse at 8, 10, 14 and 16 h.
- No forecast policy beats climatology at any budget or booking lead.

Limitation: candidate zones each day are the sites that reported that day.

## Failure gallery

The gallery holds the ten worst M2 test misses (`outputs/failure_gallery.csv`, `outputs/figures/gallery/`). Each has the AFAI
seed field, P1 drift tracks, onshore wind and the observed severity class. FIU agreed to publication of derived daily labels
(`docs/DATA_SOURCES.md`); photos and raw reports are never shown.

- All ten are observed events that M2 gave 0.000–0.029.
- **Every model missed them**, not only M2: M1 gave 0.050–0.062 and climatology 0.028–0.083.
- 8 of the 10 fall in September–October 2026. These are late-season days in a record year, which the training climatology treats as quiet.
- Rule-based cause, applied in a fixed order: local accumulation 5, label noise 3, wind shift 2, cloud gap 0. The rules are heuristics (`eval/gallery.py`).

## What this means

On 2025–2026, a seasonal climatology of when sargassum days happen at each beach is as good as any forecast this project
can issue days ahead. The hybrid gains skill only when it is handed the target day's actual weather and ocean conditions. Calibrating on one
quiet season was a mistake that the test exposed. The live 2027 track record is the next real check.
