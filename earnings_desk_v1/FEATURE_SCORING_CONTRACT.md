# Earnings Feature-Scoring Contract V1.1

Contract ID: `earn-feature-contract-v1.1.0`

Research callers submit raw, source-cited `feature_inputs`; they cannot submit numerical `features`. The Worker calculates every quantitative feature, maps the two judgment features through closed anchor sets, rounds to six decimal places, and clips the result to `[-3, 3]`. Every feature must cite at least one evidence item of an allowed source type.

## Deterministic quantitative rules

All standardised features use `clip((observed - historical_mean) / historical_std, -3, 3)`. A zero or missing historical standard deviation is `DATA BLOCKED`.

| Feature | Observed value calculated by the Worker | Required evidence class |
|---|---|---|
| `eps_revision_z` | `(current EPS consensus - prior EPS consensus) / abs(prior EPS consensus)` | consensus and revisions |
| `revenue_revision_z` | `(current revenue consensus - prior revenue consensus) / abs(prior revenue consensus)` | consensus and revisions |
| `consensus_dispersion_z` | sample standard deviation of analyst estimates divided by their absolute mean | consensus and revisions |
| `peer_readthrough_z` | relevance-weighted mean of cited peer event returns | peer read-through |
| `pre_earnings_drift_z` | stock return over the supplied window minus benchmark return | market/sector regime |
| `sector_regime_z` | sector return over the supplied window minus index return | market/sector regime |
| `index_regime_z` | index return over the supplied window | market/sector regime |
| `surprise_reaction_beta_z` | OLS slope of at least four cited historical surprise/reaction pairs, standardised against the supplied historical beta cohort | historical earnings |

## Guidance trajectory

When comparable numeric guidance ranges exist, the Worker calculates the midpoint change from `prior_low`, `prior_high`, `current_low`, and `current_high`. Changes of at most -10%, -3%, and -0.5% map to -3, -2, and -1; changes from -0.5% through +0.5% map to 0; and changes below +3%, below +10%, and at least +10% map to +1, +2, and +3. The caller must declare whether comparable numeric guidance is available.

Only when comparable numeric guidance is unavailable may the anchored path be used. The selected anchor requires an evidence-cited rationale. No intermediate score is permitted.

| Anchor | Score | Rule |
|---|---:|---|
| `MATERIAL_CUT_OR_WITHDRAWAL` | -3 | Guidance is withdrawn or materially cut across the principal earnings driver. |
| `CLEAR_CUT` | -2 | The company clearly lowers the principal guided range or midpoint. |
| `MODEST_CUT_OR_CAUTION` | -1 | A modest reduction, lowered subcomponent, or explicit caution weakens the trajectory. |
| `UNCHANGED_OR_NOT_ISSUED` | 0 | Guidance is reiterated, absent, or has no evidenced directional change. |
| `MODEST_RAISE` | 1 | A modest increase or raised low end improves the trajectory. |
| `CLEAR_RAISE` | 2 | The company clearly raises the principal guided range or midpoint. |
| `MATERIAL_RAISE` | 3 | Guidance is materially raised across the principal earnings driver. |

Allowed evidence: SEC/official filing, company investor relations, or company guidance.

## Anchored company-specific evidence

The anchor represents confirmed incremental company information since the prior earnings baseline. Unsupported sentiment and duplicated guidance/revision facts are not allowed.

| Anchor | Score |
|---|---:|
| `MATERIAL_ADVERSE_CONFIRMED` | -3 |
| `ADVERSE_CONFIRMED` | -2 |
| `MODEST_ADVERSE_CONFIRMED` | -1 |
| `NO_NET_MATERIAL_CHANGE` | 0 |
| `MODEST_POSITIVE_CONFIRMED` | 1 |
| `POSITIVE_CONFIRMED` | 2 |
| `MATERIAL_POSITIVE_CONFIRMED` | 3 |

Allowed evidence: SEC/official filing, company investor relations, company guidance, or material company news. The rationale must identify the confirmed fact and why it meets the selected materiality anchor.

## Model-status warning

The P_MODEL feature coefficients, pooling constants, tail transform, and uncertainty constants are declared as `V1_PRIORS_NOT_EMPIRICALLY_TRAINED`. They are deterministic and versioned, but they are not represented as fitted coefficients. Any empirical replacement requires a new model version, reproducible backtest, calibration report, and documented approval.
