# NBA ASSISTS + REBOUNDS V1.0 — INSTALL / DEPLOYMENT SPEC

This file is the deployment contract for the production candidate. Do not mark production accepted until the live acceptance prompt passes end-to-end.

## 1. Repository / deployment ownership

Repository: `Nstp651/nfl_free_research_pack_v1`  
Build branch during acceptance: `feature/nba-player-props-v1`  
Final production branch after accepted merge: `main`

Use Cloudflare-native Git deployment ownership. Do not introduce a second CI/CD owner that independently deploys the same Worker.

NBA paths are isolated under `nba_player_props_v1/`. The deployment must not modify `nbl_player_props_v1/` or any existing NBL Worker/binding.

## 2. Required Workers

### Research / Freeze
Worker name: `nba-player-props-research-v1`  
Source directory: `nba_player_props_v1/worker`  
Config: `nba_player_props_v1/worker/wrangler.toml`  
Expected URL: `https://nba-player-props-research-v1.nickarnott01.workers.dev`

Required Durable Object binding:
- binding: `SLATE_RUNS`
- class: `NbaSlateRun`

The Worker build command writes `source_commit.generated.js` from the exact deployment Git HEAD. `/health` must return `source_commit_ready=true` after deployment.

### Market
Worker name: `nba-player-props-market-v1`  
Source directory: `nba_player_props_v1/market_worker`  
Config: `nba_player_props_v1/market_worker/wrangler.toml`  
Expected URL: `https://nba-player-props-market-v1.nickarnott01.workers.dev`

Required Durable Object binding:
- binding: `MARKET_RUNS`
- class: `NbaMarketRun`

Required service binding:
- binding: `RESEARCH_SERVICE`
- service: `nba-player-props-research-v1`

Default variable:
- `ODDS_API_REGIONS=us`

## 3. Secrets

Never commit secret values.

Research Worker:
- `ACTION_TOKEN` — optional in code but required for secured production Action access.

Market Worker:
- `ACTION_TOKEN` — secured production Action access.
- `RESEARCH_ACTION_TOKEN` — must authorize internal calls if Research `ACTION_TOKEN` is enabled; may use the same secret value as Research Action auth.
- `ODDS_API_KEY` — Nick's existing The Odds API key.

No additional paid data vendor is required for base V1.

## 4. Runtime model assets

Required committed files after successful CI promotion:
- `nba_player_props_v1/data/promoted_assists_qbase.json`
- `nba_player_props_v1/data/promoted_rebounds_qbase.json`
- `nba_player_props_v1/data/runtime_prior_pack.json`
- `nba_player_props_v1/data/manifest.json`

The CI promotion chain must:
1. rebuild accepted history;
2. reproduce the challenge twice byte-for-byte;
3. independently promote Assists and Rebounds;
4. build runtime prior pack;
5. stage the four files;
6. commit them only when changed;
7. on the generated promotion commit, rebuild and require zero diff.

Research runtime then verifies:
`deployment Git commit -> manifest -> exact raw file SHA -> promotion/prior lineage`.

Do not deploy a Worker whose `/health` source commit points to a Git commit without these runtime assets.

## 5. Custom GPT

Name: **Nick NBA Assists + Rebounds**

Knowledge files:
- `NBA_ASSISTS_REBOUNDS_4_LAYER_MASTER_PRODUCTION_V1.0.md`
- optional install/launch references as desired.

Instructions:
- copy `GPT_INSTRUCTIONS_PRODUCTION_V1.0.md` exactly unless a later accepted version replaces it.

### Research Action
Schema: `openapi_v1.yaml`  
Base URL must resolve to the live Research Worker.  
Configure Bearer/API-key auth to send `Authorization: Bearer <ACTION_TOKEN>` if the Worker secret is enabled.

### Market Action
Schema: `market_openapi_v1.yaml`  
Base URL must resolve to the live Market Worker.  
Configure Bearer/API-key auth to send `Authorization: Bearer <ACTION_TOKEN>` if enabled.

### Bet Tracker Action
Use the existing production Bet Tracker Action/schema already used by Nick's production betting GPTs. Do not fork tracker storage for NBA.

Required preflight expectation:
- tracker `status=ok`;
- current tracker schema (currently 2.1.0 in the established workflow).

NBA identity:
- `sport=nba`
- `league=nba`
- `model_name=Nick NBA Assists + Rebounds`
- `model_version=1.0`

## 6. Cloudflare health acceptance

Research `/health` must show:
- `ok=true`;
- `market_data=false`;
- service name `nba-player-props-research-freeze`;
- `source_commit_ready=true`;
- Durable Object binding true.

Market `/health` must show:
- `ok=true`;
- `post_freeze_only=true`;
- Research service binding true;
- Market Durable Object binding true;
- Odds API key configured true.

## 7. Security / boundary checks

Before production acceptance confirm:
- Research endpoint rejects sportsbook/market fields in checkpoints.
- Market `/refresh` fails on an unfrozen run before any Odds API request.
- Market service cannot change `frozen_at` or `freeze_receipt_sha256`.
- manual screenshot refresh rejects a mismatched freeze receipt.
- manual/API markets cannot interpolate an unavailable frozen threshold.
- invalidated games are excluded by fresh market grants.
- runtime secrets do not appear in Git, response bodies or logs.

## 8. Live acceptance sequence

Run `PRODUCTION_ACCEPTANCE_PROMPT_V1.0.md` against one real future slate:
1. preflight;
2. ET fixture slate;
3. new persistent run;
4. all 1–2 game research checkpoints;
5. atomic freeze;
6. real Odds API refresh;
7. Layer 4 ranking;
8. Tracker model run;
9. post-freeze Bet365 screenshot refresh;
10. verify same `run_id`, `frozen_at`, `freeze_receipt_sha256`, no research rerun and no P_model mutation.

Only after all steps pass may PR #20 be considered for merge and V1 labelled production-ready.
