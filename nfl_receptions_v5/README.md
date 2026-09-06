# NFL Receptions V5 — Betting Platform V1 Migration

## Status
BUILD CANDIDATE. Both Cloudflare Workers are connected to the V5 feature branch and deployed; live acceptance is in progress. Not season-locked yet.

V5 preserves NFL Receptions V4.2 football/research methodology and moves orchestration, numerical execution, freeze state and market integration onto Betting Platform V1.

## Components
- `worker/` — authoritative pre-market control plane + Durable Object run state + deterministic Layer 2 engine.
- `market_worker/` — post-freeze Australian NFL receptions gateway + exact frozen threshold integration/ranking.
- `openapi.yaml` — GPT Action contract for Layers 0–2 and frozen artifact retrieval.
- `market_openapi.yaml` — GPT Action contract for Layers 3–4.
- `SOURCE_LOCK_CONTRACT.md` — content-addressed source-lock contract used by NFL V5 and future Platform V1 models.

## Run lifecycle
1. `POST /v1/runs` locks the exact fixture, `pack_revision`, manifest bytes and game-pack bytes using SHA-256 receipts. Runtime does not depend on GitHub's REST commit API.
2. `GET /v1/runs/{run_id}/research` retrieves the entire locked player pack in pages.
3. GPT completes V4.2 deep current research and submits one complete checkpoint with evidence IDs and both four-part defensive profiles, bound to the exact `source_anchor_sha256`.
4. `POST /v1/runs/{run_id}/compute` submits only the Layer 2 parameter artifact. The Worker validates exact player/evidence bindings, target allocation, scenario weights and ladders, then publishes one atomic freeze.
5. `GET /v1/receptions?run_id=...` on the market Worker first verifies both frozen status and the immutable freeze receipt. Only then can it call The Odds API.
6. The market Worker resolves the exact event, ingests `player_receptions` + `player_receptions_alternate`, exact-maps to frozen thresholds, keeps the best price, computes fair price/edge/ROI and ranks positive edges.

## V4.2 methodology preserved
- football-first, market-blind research;
- early-season role/roster/system translation;
- both four-part opponent defensive profiles;
- team targetable-pass opportunity;
- Method A (team opportunity × target share) or Method B (routes × TPRR);
- hierarchical target and catch-conversion distributions;
- explicit Other/Unmodelled target pool;
- Confidence and Fragility remain metadata, not probability haircuts;
- standard and alternate Over reception ladders only;
- no forced bet.

## Numerical implementation
The default V4.2 hierarchical beta-binomial chain is executed exactly rather than sampled where the distribution can be represented analytically. This removes Monte Carlo noise without changing the intended target/catch hierarchy. Any future simulation-only extension must retain execution evidence, draw count and seed.

## Pre-production gates
- unit/contract tests pass;
- Wrangler dry-runs pass;
- Cloudflare control + market Workers connected by native Git deployment;
- live health + pre-freeze market-block acceptance passes;
- real Action schemas accepted;
- fresh pre-market dry-runs for NE @ SEA and SF @ LA;
- V4.2 vs V5 parameter-parity audit on the same research snapshot;
- paid Odds API acceptance only after frozen state;
- V4.2 remains immutable rollback until V5 acceptance passes;
- only then tag the 2026 season lock.
