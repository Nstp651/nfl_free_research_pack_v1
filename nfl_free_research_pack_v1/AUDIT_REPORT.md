# NFL Free Research Pack V1.1 — Pre-Season Production Audit

Audit date: 2026-09-01

## Verdict

Architecture is approved to proceed to live deployment testing.

It is intentionally simple:

1. one public GitHub repository
2. one scheduled GitHub Action
3. one small Cloudflare Worker
4. one GPT research-data Action
5. one pre-season model-instruction integration

No nflverse, FTN, Fantasy Points, PFF, StatRankings or SumerSports account is required.

## Important qualification

Do not call the system "season locked" until the real GitHub Action has successfully built 2026 Week 1 packs and the Worker/GPT Action has successfully returned and consumed at least two real matchups end-to-end.

That live test is the final production gate because this local build environment cannot execute the remote nflverse downloads.

## Issues found in the V1 audit and fixed in V1.1

### 1. Pre-Week-1 NGS history failure risk — FIXED

nflreadpy 0.1.5 validates requested NGS seasons against its current-season date logic. A combined request containing 2026 could fail before its date switch and discard valid 2024/2025 NGS history.

V1.1 loads each NGS season independently. If 2026 is not yet accepted, prior-year NGS still loads.

### 2. NGS historical look-ahead risk — FIXED

V1 used one current-season NGS aggregate for every target week. That was unsafe for historical replay because later-week data could enter earlier packs.

V1.1 builds target-week-specific NGS using weekly rows with `week < target_week`, explicitly excluding season-aggregate week-0 rows for current-season packs.

### 3. Repository growth / unnecessary full-season regeneration — FIXED

V1 regenerated every regular-season game four times per day.

V1.1 automatically resolves the earliest unplayed regular-season week and publishes only that active week. A manual `--week` override remains for testing.

### 4. Transient data-source failure handling — HARDENED

Every free-source load retries up to three times. Core sources are gated. If current schedule, current roster, prior-season player stats or prior-season PBP are missing, the build refuses to publish a degraded replacement.

The last good published pack therefore remains available rather than being overwritten by empty data.

### 5. Roster clutter — FIXED

Clearly released/retired historical roster statuses are excluded. Reserve, PUP, practice-squad and suspended players remain visible because they may matter to availability and redistribution.

### 6. Target-share aggregation — FIXED

V1 target-share summaries were inadvertently weighted by the player's own targets, overweighting high-target games. V1.1 uses the game-level mean as a descriptive baseline.

### 7. Dependency drift — REDUCED

`nflreadpy` is pinned to 0.1.5. Broader numerical dependencies are major-version constrained. After the first successful live GitHub run, the environment should be frozen to an exact lock file before the model is declared season locked.

### 8. No-change refreshes — HARDENED

Generated timestamps no longer force every pack to be rewritten. Pack hashes ignore volatile timestamps; unchanged packs remain untouched. Manifest rows carry a stable pack revision hash.

## Known intentional limitations

- No true current in-season routes / route participation from this free feed.
- Offensive snap share is PROXY ONLY and never relabelled as routes.
- nflverse injury data is not relied on because the injury source died after 2024.
- Preseason/camp deployment remains live-research evidence.
- FTN `read_thrown` category values remain raw until their semantics are independently verified.
- NGS missing rows do not mean zero; NGS has qualification thresholds.

## Week 1 state

The Week 1 pack is expected to provide:

- 2025 player receiving baselines
- 2025 FTN charting
- 2025 NGS receiving context
- 2025 PFR snap proxy and advanced receiving where available
- 2025 team pass environment
- 2024 stabilisation history
- current 2026 roster and depth-chart context
- transfer and rookie flags

It deliberately does not claim 2026 regular-season usage before a 2026 regular-season game has been played.

## Season-lock protocol

Before Week 1:

1. Complete real source build test.
2. Validate at least two Week 1 matchup packs manually.
3. Deploy Worker and test both API endpoints.
4. Add Action to NFL GPT.
5. Add the research-pack integration patch to the final NFL model.
6. Run at least two complete pre-market model dry runs.
7. Verify sportsbook actions remain inaccessible until after `P_MODEL_STATUS: FROZEN` in the model workflow.
8. Freeze exact package versions and tag repository `2026-season-lock`.
9. Freeze NFL model instructions for the regular season.

During the season, do not alter model logic, feature weighting, probability construction, gates or instructions based on results.

If an external data source temporarily fails, use the built-in pack-unavailable/live-research fallback. If an upstream schema technically breaks the adapter, infrastructure-only repair is permissible without changing the NFL model methodology.
