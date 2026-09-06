# NBL ASSISTS + REBOUNDS V1.0 — CUSTOM GPT INSTALL

## GPT configuration
Create one Custom GPT for the combined NBL matchup engine.

Recommended name: `Nick's NBL Assists + Rebounds Model`

### Instructions
Paste the complete contents of:
- `GPT_INSTRUCTIONS_PRODUCTION_V1.0.md`

### Knowledge
Upload:
- `NBL_ASSISTS_REBOUNDS_4_LAYER_MASTER_PRODUCTION_V1.0.md`

Do not upload sportsbook prices, screenshots or static market files as Knowledge.

## Action 1 — Research + Freeze
Create an Action using:
- `openapi_v1.yaml`

Expected server:
- `https://nbl-player-props-research-v1.nickarnott01.workers.dev`

Expected operations:
- `healthNblPlayerPropsResearch`
- `listNblPlayerPropsFixtures`
- `startNblPlayerPropsMatchRun`
- `getNblPlayerPropsMatchRun`
- `getNblPlayerPropsResearchSeed`
- `checkpointNblPlayerPropsResearch`
- `computeNblPlayerPropsFreeze`
- `getNblPlayerPropsFrozenPlayer`

The schema must import without skipped operations or unresolved component warnings.

## Action 2 — Market
Create a second Action using:
- `market_openapi_v1.yaml`

Expected server:
- `https://nbl-player-props-market-v1.nickarnott01.workers.dev`

Expected operations:
- `healthNblPlayerPropsMarket`
- `evaluateNblPlayerPropsMarkets`

The Market Action cannot create or mutate P_model; it evaluates post-freeze observations only.

## Action 3 — Nick Bet Tracker
Create a third Action using:
- `tracker_openapi_v1.yaml`

Expected server:
- `https://nick-betting-api.nickarnott01.workers.dev`

Authentication:
- API key
- header name: `X-GPT-Action-Key`
- use the same production tracker Action key used by Nick's other betting GPTs.

Expected operations:
- `checkBetTracker`
- `createModelRun`
- `recordBet`

Test only `checkBetTracker` during installation. Require `status=ok` and `schema_version=2.1.0`. Do not create dummy model runs or bets in production D1 merely to test connectivity.

Tracker is bookkeeping only. Recommendations are not wagers; `recordBet` is called only after Nick explicitly confirms an actual bookmaker, accepted odds and stake.

## Runtime assets
Production Research Worker expects immutable runtime assets under:
- `nbl_player_props_v1/data/manifest.json`
- `nbl_player_props_v1/data/model/qbase_assists_v0.1.0.json`
- `nbl_player_props_v1/data/model/qbase_rebounds_v0.1.0.json`
- `nbl_player_props_v1/data/prior_snapshot.json`
- `nbl_player_props_v1/data/source_receipt.json`

The Research Worker pins one GitHub `main` commit at run start and verifies canonical hashes before accepting the run.

## Cloudflare
Research Worker:
- Wrangler project: `nbl-player-props-research-v1`
- Durable Object binding `MATCH_RUNS` -> `NblMatchRun`.

Market Worker:
- Wrangler project: `nbl-player-props-market-v1`
- `RESEARCH_BASE` resolves to the production Research Worker URL.

Production deployment is owned by Cloudflare Git integration. GitHub workflows verify source/contracts and Wrangler dry-run; do not create a competing deployment owner.

## Acceptance before use
Require all before calling V1.0 production-ready:
1. repository unit/integrity tests pass;
2. final QBASE artifacts train and walk-forward score through the latest completed NBL season and pass promotion gates;
3. Research Worker verification + Wrangler dry-run pass;
4. Market Worker verification + Wrangler dry-run pass;
5. Cloudflare production deployments are healthy;
6. Research Action imports cleanly;
7. Market Action imports cleanly;
8. Tracker Action imports cleanly and `checkBetTracker` returns schema 2.1.0;
9. one live future-fixture E2E completes fixture -> run -> research checkpoint -> BOTH freeze -> immutable retry -> frozen-player hash retrieval;
10. one post-freeze market acceptance completes with exact freeze receipt and per-player hash binding;
11. a pre-freeze market attempt and a market observation timestamped before freeze are rejected;
12. one real later user-confirmed wager can be recorded using the existing `model_selection_id` without changing P_model.

## First run
Use `LAUNCH_PROMPT_PRODUCTION_V1.0.md` in a brand-new chat and replace the fixture placeholders.

For later post-freeze screenshots, keep the original conversation/run so the same immutable `run_id`, `frozen_at`, `freeze_receipt_sha256` and tracker model-selection IDs can be reused without rebuilding P_model.
