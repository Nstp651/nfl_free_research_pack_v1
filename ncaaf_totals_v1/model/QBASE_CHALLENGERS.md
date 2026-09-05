# NCAA Totals QBASE — Nonlinear Challenger Audit

Frame: **7,428** FBS-v-FBS games, 2016-2025; temporal walk-forward with **5,152** scored games.

| Model | N | MAE | RMSE | Bias | Residual SD | MAE Δ vs Ridge |
|---|---:|---:|---:|---:|---:|---:|
| ridge_full_100 | 5152 | 13.033 | 16.446 | 0.917 | 16.422 | +0.000 |
| extra_trees | 5152 | 13.155 | 16.518 | 0.139 | 16.519 | +0.123 |
| random_forest | 5152 | 13.232 | 16.607 | 0.291 | 16.606 | +0.200 |
| hgb_15 | 5152 | 13.457 | 16.929 | 1.112 | 16.894 | +0.424 |
| hgb_31 | 5152 | 13.619 | 17.148 | 0.968 | 17.122 | +0.586 |

Best challenger: **ridge_full_100 remains the winner**.

The nonlinear models were scored on the same market-blind, leak-free temporal frame. None improved MAE or RMSE, so V1 keeps the transparent Ridge QBASE rather than adding complexity without out-of-sample benefit.