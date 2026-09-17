# NFL Receptions V5.1.1 — Install and Live Acceptance

V5.1.1 is a downstream player-first selection revision. It is **not** a replacement probability engine.

## Install set

Use these together:

1. Exact existing `NFL_RECEPTIONS_V5.1.0_MASTER.md` from the approved 17 September 2026 release. Do not reconstruct or edit it from excerpts.
2. `NFL_RECEPTIONS_V5.1.1_SELECTION_POLICY.md` as the explicit selection override.
3. `NFL_RECEPTIONS_V5.1.1_INTEGRATION_CONTRACT.md` for the frozen eligibility registry and actual Worker response mapping.
4. `GPT_INSTRUCTIONS_BUILDER_V5.1.1_R2.md` as the full replacement GPT Instructions field. Do not append it to older instructions.
5. `nfl_v511_selector.py` and `nfl_v511_adapter.py` with code/Data Analysis enabled.
6. Replace the GPT Control Action schema with `openapi_builder_v511.json`.
7. Replace the GPT Market Action schema with `market_openapi_v511.yaml`.
8. Keep the existing tracker Action schema `nfl_receptions_v5/tracker_openapi_builder_v2.json` and existing authentication.

Do not install the older V5.1.0 Builder Instructions at the same time as V5.1.1. The V5.1.0 master remains the underlying football/research/mathematical specification; V5.1.1 overrides only conflicting selection cutoffs, ladder dependency, readiness states and integration details.

## No infrastructure deployment required by this release

The current Control Worker already freezes `source_to_parameter_ledger`, player ladders, Confidence/Fragility and receipt hashes. The current Market Worker already returns the complete mapped `best_prices` board and quote `last_update` fields. The new Action schemas expose those existing response fields.

Therefore this release requires no HBB engine change, no market Worker business-logic change, no D1 migration, no route change, no secret change and no cron change.

## Fresh-run requirement

V5.1.1 normal production acceptance requires a **fresh run** created after the V5.1.1 installation because the pre-market selection registry must be included in the immutable freeze receipt.

A historical V5/V5.1 freeze without that registry is not silently upgraded. It returns `SELECTION INPUT INCOMPLETE` unless an expressly requested audit replay has all preserved pre-market evidence and is clearly labelled non-production.

## Pre-freeze acceptance

For the fresh fixture:

1. Validate fixture/week/kickoff and create one V5 run.
2. Retrieve every research page at one locked pack revision.
3. Complete the full V5.1 master research, including current roles and both four-part defensive profiles.
4. Checkpoint exactly once with no market information.
5. Construct model inputs only from the checkpoint.
6. Add exactly one frozen global registry item and one player registry item per modelled player as defined in the integration contract.
7. Before compute, prove:
   - registry player IDs exactly equal the modelled player IDs;
   - each registry `include` exactly equals the checkpoint player's `research_status`;
   - registry research permission exactly equals checkpoint `research_quality_permission`;
   - every registry evidence ID exists in the checkpoint;
   - threshold fragility was produced pre-market, not after price discovery.
8. Compute once. Require `complete_model_integrity_confirmed=true` and `p_model_status=FROZEN`.
9. Retrieve the frozen artifact and prove the registry is present inside `source_to_parameter_ledger` under the same `freeze_receipt_sha256`.

Failure at any step means the run is not V5.1.1 compliant.

## Post-freeze market acceptance

1. Call `getNflReceptionsBoardV5` only after freeze.
2. Verify market response run ID and freeze receipt against the control artifact.
3. Require `best_prices` and `mapped_selection_count == len(best_prices)`.
4. Never substitute `positive_edge_ranked` for the complete board.
5. Verify exact full-game Over mapping: k+ receptions = Over k-0.5.
6. Use `last_update` for quote age. Only 0–30 minute CURRENT prices may create a new recommendation.
7. Pass the frozen artifact and complete market response through `nfl_v511_adapter.py`, then `nfl_v511_selector.py`.
8. Preserve P_model, Confidence, Fragility, roles, means, distributions and registry values unchanged.

Expected decision must be one of:
- `BET`
- `NO BET — no qualifying actionable core reception bet`
- `RESEARCH QUALITY BLOCKED`
- `MARKET INPUT REQUIRED`
- `MARKET COVERAGE INCOMPLETE`
- `SELECTION INPUT INCOMPLETE`

A data-readiness failure is not a genuine NO BET.

## Required live selection cases

Production sign-off requires at least two fresh real fixtures:

### Case A — actionable board
- at least two eligible players contend for the CORE decision;
- include TE or RB contention if available;
- prove upper-tail raw ROI cannot choose the player;
- prove selected CORE follows the V5.1.1 deterministic ordering;
- if a 20–30% CORE qualifies, prove HIGH Confidence + LOW player Fragility + explicit LOW threshold Fragility and stronger value gates all existed pre-market.

### Case B — no-core or readiness case
- prove a complete board with no qualifying CORE returns genuine NO BET; OR
- prove missing/stale/incomplete market input returns its exact readiness status rather than NO BET.

No live bet must be placed merely to pass acceptance.

## Price-only refresh acceptance

Using the same valid fresh freeze:

1. Capture `freeze_receipt_sha256` and `frozen_probability_sha256` before refresh.
2. Refresh market prices only.
3. Rerun adapter + Layers 3–4 only.
4. Verify recommendation may change with price.
5. Verify both frozen hashes are byte-identical before/after.
6. Verify no role, Confidence, Fragility, mean, distribution or threshold reliability changed.

For Bet365 screenshots, exact visible price/threshold mapping is allowed only post-freeze. Screenshot upload time is not quote time.

## Tracker acceptance

When a V5.1.1 recommendation exists:

- create/reuse one tracker model run with the existing V5 identity;
- store V5.1.1 policy/run/receipt metadata only in supported fields;
- `final_play=true` only for actual V5.1.1 recommendations;
- `final_rank` is V5.1.1 recommendation order, never legacy raw-ROI order;
- `ranking_score=null` unless an explicit V5.1.1 score is later defined;
- supplemental exact thresholds use `ensureNflReceptionsFrozenSelection` and its server-derived P_model;
- repeated ensure is idempotent;
- no wager is recorded without explicit user placement confirmation.

If tracker representation cannot truthfully encode the decision, disclose it rather than writing a misleading rank/play flag.

## Hash / mutation gate

At the end of each accepted fixture retain:

- run ID;
- research receipt;
- model input hash;
- frozen probability hash;
- freeze receipt;
- normalized selection-input hash if retained;
- policy ID `NFL_RECEPTIONS_PLAYER_FIRST_1.1`;
- selection output;
- market checked time;
- tracker result.

Selection and price refresh must never mutate the first four model/freeze identities.

## Merge gate

PR #32 stays draft until:

- exact approved V5.1.0 master + V5.1.1 files are installed in the GPT;
- both replacement Action schemas are accepted by the GPT Builder;
- code execution is enabled;
- fresh Case A and Case B acceptance pass;
- price-only refresh immutability passes;
- tracker semantics pass or an explicit unsupported-policy limitation is recorded;
- GitHub policy/build/verify checks remain green.

Only then merge and call V5.1.1 production.
