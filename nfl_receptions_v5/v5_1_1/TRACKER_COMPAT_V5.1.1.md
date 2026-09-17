# NFL Receptions V5.1.1 — Tracker Compatibility

No tracker database migration is required.

The existing NFL V5 tracker and frozen-selection registry remain authoritative for persistence. V5.1.1 changes recommendation semantics only.

## Initial model-run handoff

When a V5.1.1 recommendation exists:

- `model_name` remains `NFL Receptions V5` unless the production tracker explicitly supports a new model-name enum;
- preserve the actual backend `model_version` and place `selection_policy=NFL_RECEPTIONS_PLAYER_FIRST_1.1`, V5 run id and freeze receipt in supported notes/metadata;
- `final_play=true` only for rows actually recommended by V5.1.1;
- `final_rank` is the V5.1.1 recommendation order only: CORE first, then OPTIONAL LADDER, then OPTIONAL STRETCH where present;
- `ranking_score` stays null unless the tracker has an explicitly defined V5.1.1 score. Do not write raw ROI into it;
- extra frozen/current registry rows may be persisted with `final_play=false`, `final_rank=null`, `ranking_score=null` and their market integration fields for audit;
- never copy `positive_edge_ranked` array position into `final_rank`.

A V5.1.1 `NO BET`, `MARKET INPUT REQUIRED`, `MARKET COVERAGE INCOMPLETE`, `RESEARCH QUALITY BLOCKED` or `SELECTION INPUT INCOMPLETE` must not be converted into a fake final play merely to satisfy tracker payload shape. If the current tracker endpoint cannot create a run without at least one real selection row, defer tracker-run creation until a legitimate selection exists rather than inventing one.

## Later price refresh / Bet365 screenshot

Reuse the same V5 run and freeze receipt. If a newly actionable or user-confirmed exact threshold lacks a tracker selection id, use the existing `ensureNflReceptionsFrozenSelection` route. That route independently verifies:

- existing tracker model run;
- source V5 run and freeze-receipt binding;
- player id;
- exact sportsbook half-point threshold;
- authoritative frozen P_model from the Control Worker.

New ensured rows remain `final_play=0` until an actual recommendation/wager workflow explicitly uses them. The route must never trust caller-supplied P_model.

## Bet recording

Call `recordNflReceptionsBet` only after explicit user confirmation of book, odds and stake. Bind the wager to the exact tracker `model_selection_id`. Never create a second actual bet for the same confirmed wager because a price refresh or supplemental sportsbook row was processed later.

## Compatibility conclusion

V5.1.1 is compatible with the deployed frozen-selection registry design. The selection policy must treat tracker storage rank and legacy raw market rank as separate from the V5.1.1 recommendation decision.
