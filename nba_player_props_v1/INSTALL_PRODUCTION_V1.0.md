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

Use one Australian region by default because each additional Odds API region multiplies credit usage. A request may explicitly override the region only for a controlled acceptance/debug case.

## 3. Secrets

Never commit secret values.

Research Worker:
- `ACTION_TOKEN` — optional in code but required for secured production Action access.

Market Worker:
- `ACTION_TOKEN` — secured production Action access.
- `RESEARCH_ACTION_TOKEN` — authorizes internal Market -> Research calls when Research auth is enabled; it may use the same secret value as Research Action auth.
- `ODDS_API_KEY` — Nick's existing The Odds API key.

No additional paid data vendor is required for base V1.

## 4. Runtime model assets / reproducible toolchain

Required committed files:
- `nba_player_props_v1/data/promoted_assists_qbase.json`
- `nba_player_props_v1/data/promoted_rebounds_qbase.json`
- `nba_player_props_v1/data/runtime_prior_pack.json`
- `nba_player_props_v1/data/manifest.json`

The committed assets are produced by the independent promotion chain. Production CI is deliberately non-mutating. Every CI run must:
1. use the exact pinned Python/numeric environment in `requirements.txt` plus pinned CI Python/Node versions;
2. rebuild accepted corrected history from pinned source receipts;
3. before NumPy/SciPy import, force one numerical thread and `OPENBLAS_CORETYPE=Haswell` on x86_64/amd64 so GLM training uses one deterministic OpenBLAS dynamic-architecture kernel across GitHub runner CPU models;
4. retain 9-decimal canonical serialization as a secondary guard against immaterial floating-point noise;
5. record the fixed-kernel/thread contract in challenge evidence;
6. reproduce the temporal challenge twice byte-for-byte;
7. independently re-run Assists promotion;
8. independently re-run Rebounds promotion;
9. rebuild the runtime prior pack and manifest;
10. require all four rebuilt files to be byte-identical to committed runtime assets;
11. run both Worker configs through `wrangler@4.128.0 deploy --dry-run`;
12. enforce Research, Market and NBA Tracker Action contracts, including GPT Instructions under 8,000 bytes;
13. fail rather than commit or silently replace any drifted asset.

Deployment-contract CI separately bundles/resolves all three OpenAPI 3.1 schemas, tests the post-deploy preflight harness, and enforces auth/idempotency/write-consequence/identity boundaries.

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
The schema declares HTTP Bearer auth. Configure the Action to send `Authorization: Bearer <ACTION_TOKEN>`.

The GPT must preserve the Research start `request_id` and use exact-payload retry semantics for start/checkpoint/freeze recovery. This is separate from Market and Bet Tracker idempotency keys.

### Market Action
Schema: `market_openapi_v1.yaml`  
Base URL must resolve to the live Market Worker.  
The schema declares HTTP Bearer auth. Configure the Action to send `Authorization: Bearer <ACTION_TOKEN>`.

Every genuine Odds API or manual screenshot observation gets a new `refresh_request_id`. Reuse a refresh_request_id only after an uncertain/lost response for the exact same operation. A current API retry must replay the persisted snapshot without another Odds API call/credit spend; a superseded or payload-conflicting request ID is rejected.

Manual quotes require `player_id` or `player_name`, then the Worker resolves strict frozen player identity and rejects ambiguity.

### Bet Tracker Action
Schema: `tracker_openapi_v1.yaml`  
This is an NBA-specific Action contract over Nick's **existing** production Bet Tracker at `nick-betting-api`; it does not create or fork tracker storage.

Configure `X-GPT-Action-Key` using the existing Bet Tracker Action secret.

The NBA schema is deliberately narrower than the shared backend:
- `sport=nba` only;
- `league=nba` only;
- `model_name=Nick NBA Assists + Rebounds`;
- `model_version=1.0`;
- Assists/Rebounds selections only;
- `side=over` only;
- exact player/market/threshold/integration identity required for stored selections;
- mandatory `request_id` for every tracker write;
- `createModelRun` is non-consequential bookkeeping;
- `recordBet` is consequential;
- `bet_type=single` and exactly one leg for wager logging.

If first Layer 4 is `NO BET`, do not fabricate a tracker selection and do not create a tracker model run. If a later post-freeze price refresh creates the first actionable positive edge, create the one model run then using the same immutable freeze identity.

Required preflight expectation:
- tracker `status=ok`;
- current tracker schema (currently 2.1.0 in the established workflow).

## 6. Cloudflare post-deploy preflight

Before a real slate run, execute `scripts/post_deploy_preflight.mjs` exactly as documented in `POST_DEPLOY_PREFLIGHT.md` against the exact deployed Git SHA.

Require a PASS receipt proving:
- Research and Market authentication is required;
- exact Research source commit;
- Research/Market Durable Object bindings;
- Market -> Research service binding;
- Odds API key configured without disclosure;
- default region `au` and exact market allowlist;
- shared Tracker health/schema;
- unknown/unfrozen market refresh rejected at the Research grant boundary before any Odds API request;
- no wager and no tracker model run written by preflight.

Do not proceed to full live acceptance if this preflight fails.

## 7. Cloudflare health acceptance

Research `/health` must show:
- `ok=true`;
- `market_data=false`;
- service name `nba-player-props-research-freeze`;
- `source_commit_ready=true`;
- exact expected deployment Git SHA;
- Durable Object binding true.

Market `/health` must show:
- `ok=true`;
- `post_freeze_only=true`;
- `default_regions=au`;
- Research service binding true;
- Market Durable Object binding true;
- Odds API key configured true.

## 8. Security / boundary checks

Before production acceptance confirm:
- Research endpoint rejects sportsbook/market fields in checkpoints.
- stable start request_id is deterministic/idempotent and cannot silently create a duplicate run after a lost response.
- exact persisted checkpoint retry is idempotent; changed retry or mixed old/new batch is rejected.
- repeated freeze returns original immutable `frozen_at`, receipt and P_model without recomputation.
- research checkpoints require evidence-bound role audit and current opponent assists/rebounds environment.
- research-driven quantitative role/opportunity/lineup values are constrained by promoted empirical transform envelopes.
- Market `/refresh` fails on an unfrozen/unknown run before any Odds API request.
- exact API refresh retry replays without second Odds API call; superseded/payload-conflicting refresh_request_id reuse is rejected.
- manual screenshot exact retry does not duplicate snapshot history; changed payload under same refresh ID is rejected.
- Market service cannot change `frozen_at` or `freeze_receipt_sha256`.
- manual screenshot refresh rejects mismatched freeze receipt and ambiguous/missing player identity.
- market observations predating `frozen_at` are rejected.
- frozen player/head hashes are preserved through market evaluation.
- manual/API markets cannot interpolate an unavailable frozen threshold.
- invalidated games are excluded by fresh market grants.
- Tracker Action cannot submit non-NBA identity, Unders or multi-leg bets.
- tracker writes without request_id are rejected by the Action contract.
- runtime secrets do not appear in Git, response bodies or logs.

## 9. Live acceptance sequence

Run `PRODUCTION_ACCEPTANCE_PROMPT_V1.0.md` against one real future slate:
1. post-deploy preflight;
2. ET fixture slate;
3. idempotent new persistent run lock;
4. all 1–2 game research checkpoints with persisted receipts/retry control;
5. atomic freeze plus immutable retry check;
6. real Odds API refresh plus no-double-spend retry control;
7. Layer 4 ranking;
8. if actionable positives exist, one shared-Tracker NBA model run; if NO BET, explicit tracker skip with no fabricated selection;
9. post-freeze Bet365 screenshot refresh plus idempotent write retry;
10. rerun Layer 3/4 only and apply the same actionable-only tracker rule if the first positive board appears after refresh;
11. verify same `run_id`, `frozen_at`, `freeze_receipt_sha256`, player/head hashes, no research rerun and no P_model mutation.

Only after all steps pass may PR #20 be considered for merge and V1 labelled production-ready.
