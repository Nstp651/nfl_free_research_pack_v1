# Tracker Frozen Selection Registry — NFL V5

## Goal
Allow any exact NFL Receptions V5 frozen ladder point to be attached to the existing Bet Tracker model run on demand, even when that selection was not included in the initial top-25 tracker handoff.

## Integrity rules
- Keep the initial `createNflReceptionsTrackerRun` handoff capped at 25 selections.
- Never create a second tracker model run for a missing Bet365/supplemental threshold.
- Never trust a GPT-supplied `p_model` for an on-demand selection.
- Verify the V5 run, freeze receipt, player id and exact threshold against the live NFL V5 Control Worker.
- Reuse an existing matching tracker selection when present.
- New on-demand selections are `final_play = 0`, have no integration-price/rank fields, and inherit authoritative frozen P_model/fair odds.
- No D1 schema migration is required.

## Backend patch
Apply `betting_platform_v1/TRACKER_FROZEN_SELECTION_REGISTRY_PATCH_V1.js` to the existing `nick-betting-api` Worker.

Add the documented route before the Worker's GET-only odds/event guard:

`POST /tracker/model-runs/{runId}/selections/ensure`

The patch uses existing Worker helpers and the existing `BET_DB` binding.

## GPT Tracker Action
Import:

`nfl_receptions_v5/tracker_openapi_builder_v2.json`

Keep existing API-key authentication unchanged:

`X-GPT-Action-Key`

Expected Action operations after import:
- `checkBetTracker`
- `createNflReceptionsTrackerRun`
- `ensureNflReceptionsFrozenSelection`
- `recordNflReceptionsBet`
- `listNflReceptionsTrackedBets`

## GPT Instructions
Use:

`nfl_receptions_v5/GPT_INSTRUCTIONS_BUILDER_COMPACT_V5.0.0_REGISTRY.md`

It remains below the Custom GPT 8,000-character instruction limit.

## Runtime flow
1. Complete V5 research/model/freeze/market normally.
2. Persist compact top-25 tracker board normally.
3. When a later Bet365/supplemental exact prop is confirmed and no stored `model_selection_id` exists, call `ensureNflReceptionsFrozenSelection` with:
   - existing tracker `model_run_id`
   - V5 `run_id`
   - exact `freeze_receipt_sha256`
   - exact frozen `player_id`
   - sportsbook half-point threshold (for example `4.5` for 5+ receptions)
4. The Tracker Worker fetches the authoritative frozen player ladder from the V5 Control Worker and returns an existing or newly-created `model_selection_id`.
5. Record the wager normally with `recordNflReceptionsBet` using that ID.

## Acceptance
PASS only if all are true:
- existing top-25 selection returns the existing ID idempotently;
- missing-but-frozen exact selection returns `201` and a new model_selection_id;
- repeating that request returns the same ID with `200`;
- wrong freeze receipt is rejected;
- non-frozen/missing player or invalid threshold is rejected;
- a user-confirmed Bet365 wager using the ensured ID records against the original tracker model run;
- no new tracker model run is created;
- no P_model/freeze value changes.
