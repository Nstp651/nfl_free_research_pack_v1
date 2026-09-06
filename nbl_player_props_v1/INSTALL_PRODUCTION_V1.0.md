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

The schema should import without skipped operations or unresolved component warnings before the GPT is saved.

## Action 2 — Market
Create a second Action using:
- `market_openapi_v1.yaml`

Expected server:
- `https://nbl-player-props-market-v1.nickarnott01.workers.dev`

Expected operations:
- `healthNblPlayerPropsMarket`
- `evaluateNblPlayerPropsMarkets`

The Market Action is intentionally unable to create or mutate P_model. It may only evaluate rows against an existing frozen Research run.

## Runtime assets
Production Research Worker expects immutable runtime assets under:
- `nbl_player_props_v1/data/manifest.json`
- `nbl_player_props_v1/data/model/qbase_assists_v0.1.0.json`
- `nbl_player_props_v1/data/model/qbase_rebounds_v0.1.0.json`
- `nbl_player_props_v1/data/prior_snapshot.json`
- `nbl_player_props_v1/data/source_receipt.json`

The Research Worker pins one GitHub `main` commit at run start and verifies canonical hashes before the run is accepted.

## Cloudflare
Research Worker:
- Wrangler project name: `nbl-player-props-research-v1`
- Requires Durable Object binding `MATCH_RUNS` for `NblMatchRun`.

Market Worker:
- Wrangler project name: `nbl-player-props-market-v1`
- `RESEARCH_BASE` should resolve to the production Research Worker URL.

Production deployment is owned by Cloudflare Git integration. GitHub workflows verify source/contracts and Wrangler dry-run; do not create a second competing deployment owner.

## Acceptance before use
Require all of the following before calling V1.0 production-ready:
1. repository unit/integrity tests pass;
2. Research Worker verification workflow passes;
3. Market Worker verification workflow passes;
4. Wrangler dry-runs pass;
5. Cloudflare production deployments are healthy;
6. Research Action imports cleanly in Custom GPT editor;
7. Market Action imports cleanly;
8. one live future-fixture E2E completes: fixture -> run -> research checkpoint -> BOTH freeze -> immutable retry -> frozen-player hash retrieval;
9. one post-freeze market acceptance completes with exact freeze receipt and per-player hash binding;
10. a pre-freeze market attempt and a market observation timestamped before freeze are both rejected.

## First run
Use `LAUNCH_PROMPT_PRODUCTION_V1.0.md` in a brand-new chat and replace the fixture placeholders.

For later Bet365 screenshots, keep the original conversation/run so the same immutable `run_id`, `frozen_at` and `freeze_receipt_sha256` can be reused without rebuilding P_model.
