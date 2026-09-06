# NFL V5 Layer 2 Model Input Contract

The GPT performs football judgement in Layer 1, then submits explicit parameters. The Worker performs all repeatable probability maths and freezes the result.

## Team opportunity
Each scenario supplies a discrete distribution of targetable passes as `{value, probability}` rows summing to 1.

## Player target construction
Exactly one target method per player/scenario:
- `A`: targetable pass opportunity × beta target-share rate.
- `B`: discrete route-count opportunity × beta TPRR rate.

`target_rate = {mean, strength}`. Strength parameterizes the beta uncertainty around the rate; degenerate 0/1 rates are supported.

## Catch conversion
`catch_rate = {mean, strength}` is one coherent per-target catch probability distribution. Do not duplicate catchability through a second conversion factor.

## Allocation gate
For each team/scenario, the Worker's derived expected player target shares plus `other_share` must equal exactly 1 within `1e-8`. The same exact parameters are used in the probability engine. Combined scenario-weighted allocation must also reconcile.

## Scenario gate
Scenario weights must sum to 1 within `1e-8`. Scenarios represent material discrete football states already justified in Layer 1; they are not generic uncertainty haircuts.

## Evidence binding
Every modelled player must exactly match an INCLUDE/WATCHLIST player in the checkpointed research receipt. Every `source_to_parameter_ledger` row must cite evidence IDs in that same receipt.

## Output
The Worker returns a frozen probability artifact with:
- expected targets/receptions;
- exact hierarchical beta-binomial reception ladder;
- allocation audits;
- Confidence/Fragility metadata;
- input, probability and complete freeze SHA-256 receipts.
