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
- `ODDS_API_REGIONS=au`

Use one Australian region by default because the production betting stack is Australian and each additional Odds API region multiplies credit usage. A request may explicitly override the region when required for a controlled acceptance/debug case.

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

Required committed files:
- `nba_player_props_v1/data/promoted_assists_qbase.json`
- `nba_player_props_v1/data/promoted_rebounds_qbase.json`
- `nba_player_props_v1/data/runtime_prior_pack.json`
- `nba_player_props_v1/data/manifest.json`

The committed assets were produced by the independent promotion chain. Production CI is now deliberately **non-mutating**. Every CI run must:
1. rebuild accepted corrected history from pinned receipts;
2. reproduce the temporal challenge twice byte-for-byte;
3. independently re-run Assists promotion;
4. independently re-run Rebounds promotion;
5. rebuild the runtime prior pack;
6. rebuild the runtime manifest;
7. require all four rebuilt files to be byte-identical to the committed runtime assets;
8. fail rather than commit or silently replace any drifted asset.

This prevents GitHub Actions bot commits from becoming a second deployment/promotion owner and makes one Git commit a fully verifiable production input.

Research runtime verifies:
`deployment Git commit -> manifest -> exact raw file SHA -> promotion/prior lineage`.

Do not deploy a Worker whose `/health` source commit points to a Git commit without the exact committed runtime assets.

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

The GPT must preserve the Research start `request_id` and use exact-payload retry semantics for start/checkpoint/freeze recovery. This is separate from any Bet Tracker idempotency key.

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
- `default_regions=au`;
- Research service binding true;
- Market Durable Object binding true;
- Odds API key configured true.

## 7. Security / boundary checks

Before production acceptance confirm:
- Research endpoint rejects sportsbook/market fields in checkpoints.
- a stable start request_id is deterministic/idempotent and cannot silently create a duplicate run after a lost response.
- an exact persisted checkpoint retry is idempotent; a changed retry or mixed old/new batch is rejected.
- repeated freeze returns the original immutable `frozen_at`, receipt and P_model without recomputation.
- research checkpoints require evidence-bound role audit and current opponent assists/rebounds environment.
- research-driven quantitative role/opportunity/lineup values are constrained by the promoted empirical transform envelope.
- Market `/refresh` fails on an unfrozen run before any Odds API request.
- Market service cannot change `frozen_at` or `freeze_receipt_sha256`.
- manual screenshot refresh rejects a mismatched freeze receipt.
- market observations predating `frozen_at` are rejected.
- frozen player/head hashes are preserved through market evaluation.
- manual/API markets cannot interpolate an unavailable frozen threshold.
- invalidated games are excluded by fresh market grants.
- runtime secrets do not appear in Git, response bodies or logs.

## 8. Live acceptance sequence

Run `PRODUCTION_ACCEPTANCE_PROMPT_V1.0.md` against one real future slate:
1. preflight;
2. ET fixture slate;
3. idempotent new persistent run lock;
4. all 1–2 game research checkpoints with persisted receipts and retry control;
5. atomic freeze plus immutable retry check;
6. real Odds API refresh;
7. Layer 4 ranking;
8. Tracker model run;
9. post-freeze Bet365 screenshot refresh;
10. verify same `run_id`, `frozen_at`, `freeze_receipt_sha256`, player/head hashes, no research rerun and no P_model mutation.

Only after all steps pass may PR #20 be considered for merge and V1 labelled production-ready.
