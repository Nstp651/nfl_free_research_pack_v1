# NFL RECEPTIONS V5.1.1 — LIVE INTEGRATION CONTRACT

This contract supplies the missing bridge between the V5.1.1 player-first policy and the existing V5 Workers. It does **not** change P_model or Worker business logic.

## Existing server capabilities used

The control-plane frozen artifact already persists `source_to_parameter_ledger`, `players`, Confidence, Fragility, ladders and the freeze receipt. The market Worker already returns the complete mapped `best_prices` board with frozen P_model, price, bookmaker, market key and `last_update`.

V5.1.1 MUST use these existing fields. `positive_edge_ranked` is audit-only and cannot be used as a substitute for `best_prices`.

## Pre-market frozen selection registry

Before `computeNflReceptionsFreezeV5`, append the following records to the existing `source_to_parameter_ledger`.

### Global permission record

Exactly one item:

- `parameter_path`: `selection_policy.research_quality_permission`
- `evidence_ids`: non-empty valid checkpoint evidence IDs
- `rationale`: canonical compact JSON exactly shaped as `{"permission":"YES","v":1}` or `{"permission":"NO","v":1}`

### One record per modelled player

Exactly one item per player:

- `parameter_path`: `selection_eligibility.<player_id>`
- `evidence_ids`: non-empty evidence IDs supporting the eligibility assessment
- `rationale`: canonical compact JSON with exactly these keys:
  - `v`: `1`
  - `position`: `WR|TE|RB|OTHER`
  - `include`: `INCLUDE|WATCHLIST|EXCLUDE`
  - `receiver_class`: one of the four V5.1 approved classes or `OTHER`
  - `role`: `STABLE|VERIFIED_EXPANSION|SPECULATIVE|UNUSABLE`
  - `pathway_usable`: boolean
  - `evidence_score`: integer 0–16
  - `availability_score`: integer 0–2
  - `role_score`: integer 0–2
  - `threshold_fragility`: object mapping reception threshold strings (`"1"`, `"2"`, ...) to `LOW|MODERATE|HIGH`

`threshold_fragility` comes only from the pre-market sensitivity/reliability audit. Never create, upgrade or downgrade it after prices are available.

The registry is therefore included in the same immutable freeze receipt as the model probabilities. It is durable across refreshes and fresh GPT sessions without changing the HBB engine schema.

## Post-freeze normalization

Use the full frozen artifact plus the market board and execute `nfl_v511_adapter.py`.

The adapter must prove:

1. exact 64-char run ID agreement;
2. exact freeze receipt agreement;
3. one registry row for every frozen player;
4. frozen Confidence/Fragility are used, not reconstructed later;
5. `mapped_selection_count == len(best_prices)`;
6. market row player IDs exist in the frozen registry;
7. only standard/alternate reception market keys are accepted;
8. `last_update` is timezone-aware and current for a new recommendation;
9. threshold fragility is read from the frozen registry;
10. no probability is recalculated or market-fitted.

## Readiness statuses

Do not collapse these into NO BET:

- `RESEARCH QUALITY BLOCKED` — frozen research permission is not YES.
- `MARKET INPUT REQUIRED` — there are no current valid mapped reception prices; sportsbook screenshots may be used as the existing post-freeze supplemental workflow permits.
- `MARKET COVERAGE INCOMPLETE` — mapped market response is malformed/incomplete.
- `SELECTION INPUT INCOMPLETE` — run/freeze/registry binding is missing or contradictory.

Only a complete, current and valid board that genuinely produces no qualifying V5.1.1 CORE anchor may return:

`NO BET — no qualifying actionable core reception bet.`

## Deployment consequence

No Cloudflare Worker code deployment is required for this integration contract because it consumes fields the current Workers already return. The GPT Action response schemas should be refreshed so the full frozen artifact and `best_prices` fields are explicitly documented.
