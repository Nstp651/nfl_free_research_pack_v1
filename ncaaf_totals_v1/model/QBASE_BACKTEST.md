# NCAA Totals QBASE V0.1.0 — Walk-forward Backtest

Selected: **ridge_full**, alpha **100.0**
Training frame: **7428** FBS-v-FBS games, 2016-2025.

## Candidate results

| Family | Alpha | N | MAE | RMSE | Bias | Residual SD |
|---|---:|---:|---:|---:|---:|---:|
| ridge_full | 100.0 | 5152 | 13.033 | 16.446 | 0.917 | 16.422 |
| ridge_full | 10.0 | 5152 | 13.047 | 16.465 | 0.948 | 16.439 |
| ridge_full | 1.0 | 5152 | 13.050 | 16.467 | 0.944 | 16.441 |
| ridge_full | 0.1 | 5152 | 13.050 | 16.467 | 0.943 | 16.441 |
| ridge_core | 100.0 | 5152 | 13.074 | 16.512 | 0.804 | 16.494 |
| ridge_core | 10.0 | 5152 | 13.078 | 16.524 | 0.867 | 16.503 |
| ridge_core | 1.0 | 5152 | 13.079 | 16.526 | 0.872 | 16.504 |
| ridge_core | 0.1 | 5152 | 13.079 | 16.526 | 0.873 | 16.505 |

## Selected model residual calibration

| Bucket | N | MAE | RMSE | Bias | Residual SD |
|---|---:|---:|---:|---:|---:|
| ALL | 5152 | 13.033 | 16.446 | 0.917 | 16.422 |
| WEEK_0_1 | 559 | 13.699 | 17.000 | -1.017 | 16.984 |
| WEEK_2_4 | 958 | 13.236 | 16.883 | 1.377 | 16.835 |
| WEEK_5_PLUS | 3635 | 12.876 | 16.241 | 1.094 | 16.206 |

## Integrity

- Market data used: **NO**
- Current-season cutoff: **week W uses through W-1**
- Model selection: temporal walk-forward by season
- Residual calibration: temporal out-of-sample residuals
- Current injuries/QB/weather: intentionally outside QBASE
