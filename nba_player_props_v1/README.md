# Nick NBA Assists + Rebounds V1

Status: **PRODUCTION CANDIDATE — LIVE CLOUDFLARE / CUSTOM GPT ACCEPTANCE PENDING**

PR #20 remains draft and unmerged. This directory is an isolated NBA implementation and does not modify NBL production.

## Product

One complete NBA `America/New_York` league-date slate per persistent run, with two independently promoted quantitative heads:

- ASSISTS
- REBOUNDS

Default mode: `BOTH`.

Recommendation scope is player Assists/Rebounds **Overs** only, including exact standard and alternate ladders. There is no points head and no SGM logic. Positive EV is never forced.

## Current accepted quantitative state

The five-season deterministic source build originally contained 139,809 validated player-games. Final-box adjudication identified 14 inconsistent complete games; the source gate removes each entire affected game rather than patching statistics. The accepted model history contains **139,529 player-games** with SHA-256:

`2e6926aa87ccebafbf938322f8facefeb54de63eb22f924dc2793afc61750b25`

Both independent heads have passed the predeclared corrected-history promotion gates as `PROMOTED_CORE_V1`:

- `NBA_ASSISTS_QBASE_V1.0.0`
- `NBA_REBOUNDS_QBASE_V1.0.0`

2026 remains holdout-only for pass/fail review and cannot reselect model family. The runtime asset CI now quantizes exported production parameters, forces single-thread numerical libraries and reruns each challenge twice to require byte-identical evidence before committing promoted assets.

Specialist metrics remain feature-gated. Base V1 is explicitly allowed to operate without unavailable/unreliable tracking metrics; missing data are never zero-filled.

## Implemented services

### `nba-player-props-research-v1`
Implemented under `worker/`:
- sanitized ET league-date fixture discovery;
- current roster/status identity;
- Git-pinned runtime asset loading;
- persistent `NbaSlateRun` Durable Object;
- server-enforced 1–2 game research batches;
- market-blind checkpoint validation;
- current-role/team-opportunity research contract;
- server historical prior assembly;
- typed QBASE runtime transformations;
- exact count distributions including integer pushes;
- per-head and per-player model hashes;
- atomic whole-slate freeze;
- immutable freeze receipt and integrity index;
- late-news invalidation without probability mutation;
- post-freeze market-access grants.

### `nba-player-props-market-v1`
Implemented under `market_worker/`:
- separate `NbaMarketRun` Durable Object;
- service binding back to Research Worker;
- fresh market-access grant before any sportsbook request;
- The Odds API event matching by teams + kickoff;
- only the four approved Assists/Rebounds standard/alternate market keys;
- Australian region default (`au`);
- strict frozen player mapping;
- Overs-only ingestion;
- current API snapshot replacement;
- post-freeze Bet365/manual screenshot snapshots;
- exact frozen-threshold binding with no interpolation;
- frozen player/head hash verification;
- best exact current price;
- push-aware EV and push-adjusted tracker edge;
- global BEST SINGLE / Top 10 / head-specific rankings / NO BET.

### Bet Tracker
The existing production tracker is reused unchanged. NBA identity is:
- `sport=nba`
- `league=nba`
- `model_name=Nick NBA Assists + Rebounds`
- `model_version=1.0`

A model run is created only after Layer 4. An actual wager is recorded only after explicit confirmation of selection, bookmaker, accepted odds and stake.

## Integrity boundary

1. Resolve one exact ET league-date slate and pin runtime assets.
2. Research the entire eligible slate market-blind in server-enforced batches.
3. Checkpoint each current 1–2 game batch before another batch is exposed.
4. GPT supplies evidence-bound basketball state only; it cannot submit a final assists/rebounds mean.
5. Server scores independently promoted QBASE through typed transforms.
6. Atomically freeze the whole requested slate before any market operation.
7. Bind every evaluated market to the exact freeze, player hash, head hash and exact threshold.
8. Reject market observations captured before `frozen_at`.
9. Permit price/screenshot refreshes post-freeze without P_model mutation.
10. Material late news invalidates affected scope; a changed P_model requires a new market-blind run.

## Production package

Current production-candidate artifacts include:
- `NBA_ASSISTS_REBOUNDS_4_LAYER_MASTER_PRODUCTION_V1.0.md`
- `GPT_INSTRUCTIONS_PRODUCTION_V1.0.md`
- `openapi_v1.yaml`
- `market_openapi_v1.yaml`
- `TRACKER_INTEGRATION_PRODUCTION_V1.0.md`
- `LAUNCH_PROMPT_PRODUCTION_V1.0.md`
- `INSTALL_PRODUCTION_V1.0.md`
- `PRODUCTION_ACCEPTANCE_PROMPT_V1.0.md`

## Remaining release gates

Repo/CI must first finish the deterministic runtime-asset promotion and byte-identical follow-up run. Then the still-unpassed gates are Cloudflare account deployment/configuration, live Worker health, a real future whole-slate Layer 0–4 run, real Odds API retrieval, tracker acceptance, and the post-freeze Bet365 screenshot refresh proving the same `run_id`, `frozen_at`, `freeze_receipt_sha256` and P_model.

No live deployment or synthetic test substitutes for those gates. PR #20 stays draft and V1 stays **not production-ready** until every acceptance requirement actually passes.
