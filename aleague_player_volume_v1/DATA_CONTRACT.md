# A-League Player Volume V1 — Canonical Data Contract

## Goal
Separate provider-specific extraction from model-specific feature building. Parsers may change; canonical rows and their semantics must remain stable/versioned.

## Common identity fields
Every historical event row must contain:

- `fixture_id` — stable canonical fixture key;
- `kickoff_utc` — ISO-8601 UTC timestamp used for ordering/leakage control;
- `season` — canonical season label;
- canonical `team_id` / `opponent_id`;
- source identity/receipt in the publication manifest.

Player/keeper rows additionally require canonical `player_id` plus source aliases in the separate identity map.

## `TeamMatchShooting`
Required numerical fields:

- shots_for
- sot_for
- shots_against
- sot_against

All are full-match team counts. A duplicated team-fixture key is invalid.

## `PlayerMatchShooting`
Required fields:

- player_id
- team_id
- opponent_id
- minutes
- started
- shots
- shots_on_target

Validation:

- minutes >= 0;
- shots >= 0;
- 0 <= shots_on_target <= shots.

The QBASE shot prior is stored as shots per 90. Projected minutes are **not** embedded in the current-match allocation prior; current exposure is added later in Layer 1/2.

## `GoalkeeperMatch`
Required fields:

- player_id
- minutes
- shots_on_target_faced
- saves
- goals_allowed

Validation:

- saves <= shots_on_target_faced;
- goals_allowed <= shots_on_target_faced;
- provider stat-definition discrepancies (for example own goals/penalties) must be documented rather than silently forced into equality.

Optional advanced fields may include `psxg`, `psxg_per_sot` and related keeper-quality measures where source coverage is validated.

## Leakage rule
A pre-match QBASE snapshot for fixture time `T` may use only canonical rows with `kickoff_utc < T`.

This is enforced in code and tested by the invariant:

> Adding, changing or deleting a future event must not change any earlier prematch snapshot.

Season aggregate pages are useful for reconciliation, but they are not themselves valid historical prematch features.
