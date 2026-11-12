# Model card — Broward sargassum beaching forecast (v0.1-test-frozen)

Every number in this card comes from a committed file in `outputs/`. The file is named next to the number.

## Model details

- **Served model: M2.** A LightGBM gradient-boosting classifier (M1) with isotonic calibration fit on the 2024 season. It is frozen at git
  tag `v0.1-test-frozen`. The live job uses `models/artifacts/forecast_bundle_v1.pkl`, which reproduces all frozen test predictions
  exactly (`ops/bundle.py verify`).
- **Inputs to M1**:
  - beach-report persistence (latest report ≤ 3 days old, 7-day rates)
  - satellite AFAI statistics (coastal band, 50 km radius, upstream corridors; 1-day and 3-day products)
  - winds, waves and currents for the target day
  - tides, day of season, site and lead
  - the baseline outputs B0–B3 (stacked, leave-one-season-out on training rows)
  - the P1 drift arrival index (OpenDrift, no Stokes drift, 2% windage)
- **Comparison models**, published alongside M2 in the API:
  - B1 climatology
  - M2_fc, the same model family using only data available at issue time
- **Owner:** Naresh Rajesh (nareshrajesh787@gmail.com). **License:** MIT for code; data keep their own terms.

## Intended use

- A research and planning aid for beach-cleanup crews and coastal managers at the 8 Broward County, FL sites of FIU Sargassum
  Watch, March–October, at leads of 1–7 days. It also feeds the crew planner and Costa's `ForecastProvider`.
- **Not intended** as a public-health or safety warning, or for any other location. It is not validated outside March–October.
  It should not be used to decide whether a beach is safe.

## Target and labels

P(a moderate-or-worse sargassum day at the beach on the target date). That means severity ≥ 2: water slightly or very brown, or the
site smells. Labels come from FIU Sargassum Watch reports. Same-day reports are merged by taking the worst. The rules were frozen before modelling
(`pipeline/labels/fiu_labels.py`). Event rates are 0.092 in 2024, 0.198 in 2025 and 0.359 in 2026
(`outputs/feasibility/fiu_season_stats.csv`).

## Training and evaluation data

- **Train:** seasons 2020–2023. 2019 used a different survey form and appears only in a sensitivity run
  (`outputs/results_val_train2019.csv`).
- **Validation:** 2024. Used for M1 hyper-parameters (≤ 50 trials), M2 calibration and P1 configuration selection.
- **Test:** 2025 and 2026, scored once after freezing (`outputs/results_test_meta.json`).
- **Drivers:** in training and testing, winds, waves, currents and P1 forcing are *analyses valid on the target day*. Results for
  models that use them (P1, M1, M2) are upper bounds. Live forecasts use real forecasts instead.

## Metrics (test seasons 2025–2026 pooled; 95% weekly block bootstrap; `outputs/results_test.csv`)

| Model | Brier skill vs climatology (B1) | Brier skill vs persistence (B0) | ROC-AUC |
| --- | --- | --- | --- |
| M2 (served) | −0.034 [−0.058, −0.011] | −0.023 [−0.047, 0.001] | 0.720 [0.676, 0.762] |
| M1 (uncalibrated) | 0.064 [0.032, 0.096] | 0.074 [0.043, 0.106] | 0.724 [0.678, 0.767] |
| M2_fc (issue-time inputs) | −0.103 [−0.136, −0.066] | −0.091 [−0.120, −0.058] | 0.666 [0.616, 0.710] |
| B1 climatology | 0 | 0.011 [−0.006, 0.028] | 0.701 [0.651, 0.743] |
| B0 persistence | −0.011 [−0.029, 0.006] | 0 | 0.616 [0.578, 0.649] |

- M2 is **worse than climatology** on test. Its calibration was fit on the quiet 2024 season, so it under-forecasts high-sargassum
  years. In 2026 its mean forecast was 0.127 against an observed event rate of 0.359 (`outputs/reliability_test.csv`).
- Each served probability comes with an **empirical 80% band**: the observed event frequency in 2025–2026 when M2 issued a
  similar probability (`outputs/m2_interval_table.csv`). The band is fit on the test seasons themselves, so its coverage on
  new data is untested until the 2027 live season.
- Per-season, per-lead and paired comparisons are in `outputs/results_test.csv`, `outputs/results_test_paired.csv` and
  [RESULTS.md](RESULTS.md).

## Factors and failure modes

- **Season and year:** skill differs sharply between 2025 and 2026 (RESULTS.md, "By season").
- **Late-season events in 2026, the highest-event season on record:** all ten worst test misses were events on days that climatology treats as quiet. Every model
  missed them, not only M2 (`outputs/failure_gallery.csv`).
- **Label noise:** reports are citizen science, coverage is uneven and photos are not used for labels.
- **Sensor change:** the AFAI input depends on MODIS, which is scheduled to end in 2027. The daily job alarms on stale inputs.

## Ethical considerations

- A wrong low forecast could send crews elsewhere on a heavy day. The app shows climatology and the empirical band next to every
  probability. It states the served model's test result on the map, crew-planner, track-record and methods pages, and "not a warning
  system" on every page.
- FIU's beach reports are used with FIU's agreement. Only derived daily labels are published; photos and free text never are.

## Caveats and recommendations

- Prefer the climatology column until the 2027 live track record shows skill. If M2 is used, read it with its 80% band, keeping in mind
  that the band itself was fit on 2025–2026 and is not yet validated.
- A recalibration fit on more than one season, or no calibration, was not tested on 2025–2026 because the models were frozen. It can
  only be evaluated on 2027 live data.
