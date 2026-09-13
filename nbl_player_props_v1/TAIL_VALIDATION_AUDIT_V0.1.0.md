# NBL QBASE V0.1.0 Tail-Validation Audit

## Scope and reproduction

The audit uses the same 24,208 season-by-season temporal out-of-sample predictions per head that produced the shipped model-family selection and NB2 dispersion. Historical inputs reproduce the pinned source receipt hashes. `model/tail_validation.py` rebuilds the selected Poisson model's OOS predictions and `evidence/qbase_tail_validation_v0.1.0.json` records every threshold from 1 through each probability-grid maximum.

`thresholds_used_for_selection` is the consecutive set whose temporal-OOS at-least Brier scores were averaged to rank candidate model families and regularization values. It is not a statement that the full mathematical NB2 grid was independently reliable. Before this patch no Brier, observed-frequency or predicted-frequency evidence was stored outside that selection set.

## Reliability policy

The direct gate requires at least 250 observed and 250 predicted OOS events, Brier skill of at least 0.05 versus constant prevalence, and predicted/observed frequency ratio from 0.75 to 1.35. Direct support must remain consecutive from the original selection-range floor.

The secondary tail gate requires at least 250 observed and predicted events, non-negative Brier skill, predicted/observed ratio from 0.5 to 2.0, and absolute aggregate calibration error no greater than 0.01. Upper-tail support stops at the first failed threshold. A `TAIL_SUPPORTED` threshold is BEST SINGLE eligible only if it also passes the direct reliability gate.

## Assists findings

Original selection thresholds: 2+ through 10+.

| At least | Observed OOS | Predicted OOS | Observed rate | Predicted rate | Ratio | Brier skill |
|---:|---:|---:|---:|---:|---:|---:|
| 8+ | 531 | 573.1 | 2.193% | 2.367% | 1.079 | 0.143 |
| 9+ | 307 | 394.3 | 1.268% | 1.629% | 1.284 | 0.086 |
| 10+ | 158 | 276.8 | 0.653% | 1.143% | 1.752 | -0.057 |
| 11+ | 75 | 197.6 | 0.310% | 0.816% | 2.635 | -0.286 |
| 12+ | 40 | 143.3 | 0.165% | 0.592% | 3.583 | -0.481 |
| 13+ | 22 | 105.3 | 0.091% | 0.435% | 4.788 | -0.722 |

Conclusion: 2+–9+ is `DIRECT_VALIDATED`; 1+ is lower-ladder `TAIL_SUPPORTED` and BEST SINGLE eligible; 10+ and above is `EXTREME_TAIL`. There is no defensible high-ladder `TAIL_SUPPORTED` assists range. The Cotton 12+ example therefore remains visible and raw-EV-ranked but is ineligible for BEST SINGLE.

## Rebounds findings

Original selection thresholds: 3+ through 15+.

| At least | Observed OOS | Predicted OOS | Observed rate | Predicted rate | Ratio | Brier skill |
|---:|---:|---:|---:|---:|---:|---:|
| 11+ | 782 | 847.3 | 3.230% | 3.500% | 1.083 | 0.116 |
| 12+ | 493 | 618.8 | 2.037% | 2.556% | 1.255 | 0.068 |
| 13+ | 310 | 455.9 | 1.281% | 1.883% | 1.471 | 0.005 |
| 14+ | 188 | 338.5 | 0.777% | 1.398% | 1.801 | -0.078 |
| 15+ | 103 | 253.1 | 0.425% | 1.046% | 2.457 | -0.181 |
| 16+ | 58 | 190.4 | 0.240% | 0.787% | 3.283 | -0.348 |

Conclusion: 3+–12+ is `DIRECT_VALIDATED`; 1+, 2+ and 13+ are `TAIL_SUPPORTED`; 14+ and above is `EXTREME_TAIL`. Rebounds 13+ has enough observations for secondary tail support but not the stronger BEST SINGLE gate, so it is visible and deterministically ineligible.

## Model integrity

No coefficient, intercept, imputer, scaler, NB2 dispersion, maximum count or frozen probability-grid algorithm changed. The QBASE JSON and manifest hashes change only because the evidence-derived threshold policy is appended to model metadata. Existing frozen runs remain byte-for-byte unchanged; the Market Worker contains an exact old-QBASE-hash compatibility policy for those runs.
