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
- `fetchNblPlayerPropsOddsApi`
- `evaluateNblPlayerPropsMarkets`

`fetchNblPlayerPropsOddsApi` is post-freeze only. It verifies the exact immutable freeze before any Odds API request, resolves the exact `basketball_nbl` event and requests assists/rebounds plus alternate ladders. If alternates are rejected it can fall back to base assists/rebounds. Screenshot/public-web observations continue through `evaluateNblPlayerPropsMarkets`.

The Market Action cannot create or mutate P_model.

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

The Research Worker is pinned at Cloudflare build time to the exact deployed Git commit (`WORKERS_CI_COMMIT_SHA`) and verifies immutable runtime asset hashes before accepting a run. The checked-in generated source-commit placeholder fails closed if the build pin is unavailable.

## Cloudflare
Research Worker:
- Wrangler project: `nbl-player-props-research-v1`
- Durable Object binding `MATCH_RUNS` -> `NblMatchRun`.
- Wrangler custom build generates the exact deployment source commit before bundling.

Market Worker:
- Wrangler project: `nbl-player-props-market-v1`
- production Worker-to-Worker transport uses Cloudflare Service Binding `RESEARCH` -> `nbl-player-props-research-v1`.
- `RESEARCH_BASE` is retained only as a local/test fallback.
- configure `ODDS_API_KEY` as an encrypted Cloudflare Worker secret for automated live retrieval. Never commit the key. The Worker still deploys and supports screenshot evaluation when the secret is absent; `/health` reports `odds_api_fetch_configured=false`.

Production deployment is owned by Cloudflare Git integration. GitHub workflows verify source/contracts and Wrangler dry-run; do not create a competing deployment owner.

## Acceptance before use
Require all before calling V1.0 production-ready:
1. repository unit/integrity tests pass;
2. final QBASE artifacts train and walk-forward score through the latest completed NBL season and pass promotion gates;
3. Research Worker verification + Wrangler dry-run pass;
4. Market Worker verification + Wrangler dry-run pass;
5. Cloudflare production deployments are healthy;
6. Research Action imports cleanly;
7. Market Action imports cleanly and exposes live Odds API retrieval;
8. Tracker Action imports cleanly and `checkBetTracker` returns schema 2.1.0;
9. one live future-fixture E2E completes fixture -> run -> research checkpoint -> BOTH freeze -> immutable retry -> frozen-player hash retrieval;
10. returning-player projection sanity rejects a Cotton-style opening-season stable-role extrapolation outside the server envelope;
11. one post-freeze Odds API support test returns an explicit support state, and any returned rows bind to the same freeze;
12. one post-freeze screenshot market acceptance completes with exact freeze receipt and per-player hash binding;
13. a pre-freeze market attempt and a market observation timestamped before freeze are rejected;
14. one real later user-confirmed wager can be recorded using the existing `model_selection_id` without changing P_model.

## First run
Use `LAUNCH_PROMPT_PRODUCTION_V1.0.md` in a brand-new chat and replace the fixture placeholders.

For later post-freeze screenshots, keep the original conversation/run so the same immutable `run_id`, `frozen_at`, `freeze_receipt_sha256` and tracker model-selection IDs can be reused without rebuilding P_model.
