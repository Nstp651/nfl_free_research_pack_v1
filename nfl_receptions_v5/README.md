# NFL Receptions V5 — Betting Platform V1 Migration

## Status
BUILD CANDIDATE. Both Cloudflare Workers are connected to the V5 feature branch and deployed; live acceptance is in progress. Not season-locked yet.

V5 preserves NFL Receptions V4.2 football/research methodology and moves orchestration, numerical execution, freeze state and market integration onto Betting Platform V1.

## Components
- `worker/` — authoritative pre-market control plane + Durable Object run state + deterministic Layer 2 engine.
- `market_worker/` — post-freeze Australian NFL receptions gateway + exact frozen threshold integration/ranking.
- `openapi.yaml` — GPT Action contract for Layers 0–2 and frozen artifact retrieval.
- `market_openapi.yaml` — GPT Action contract for Layers 3–4.
- `tracker_openapi.yaml` — GPT Action contract for downstream tracker-run persistence and user-confirmed NFL bet recording in the existing Nick Bet Tracker.
- `SOURCE_LOCK_CONTRACT.md` — content-addressed source-lock contract used by NFL V5 and future Platform V1 models.

## Run lifecycle
1. `POST /v1/runs` locks the exact fixture, `pack_revision`, manifest bytes and game-pack bytes using SHA-256 receipts. Runtime does not depend on GitHub's REST commit API.
2. `GET /v1/runs/{run_id}/research` retrieves the entire locked player pack in pages.
3. GPT completes V4.2 deep current research and submits one complete checkpoint with evidence IDs and both four-part defensive profiles, bound to the exact `source_anchor_sha256`.
4. `POST /v1/runs/{run_id}/compute` submits only the Layer 2 parameter artifact. The Worker validates exact player/evidence bindings, target allocation, scenario weights and ladders, then publishes one atomic freeze.
5. `GET /v1/receptions?run_id=...` on the market Worker first verifies both frozen status and the immutable freeze receipt. Only then can it call The Odds API.
6. The market Worker resolves the exact event, ingests `player_receptions` + `player_receptions_alternate`, exact-maps to frozen thresholds, keeps the best price, computes fair price/edge/ROI and ranks positive edges.
7. After Layer 4, the GPT writes one downstream tracker model-run record containing the frozen reception selections and preserves returned tracker selection IDs. This is bookkeeping only and cannot alter Platform V1 state.
8. Only after the user explicitly confirms a placed wager does the GPT record the actual bet against the exact stored tracker selection ID.
9. Existing production tracker auto-settlement is responsible for supported NFL reception results; ambiguous or unavailable official results remain pending rather than being guessed.

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

## GPT production wiring
The production NFL GPT requires three Actions:
1. `openapi.yaml` — control/research/freeze.
2. `market_openapi.yaml` — frozen market integration/ranking.
3. `tracker_openapi.yaml` — tracker health, frozen run persistence and confirmed bet logging.

Tracker authentication uses the existing server-side `X-GPT-Action-Key`. Never commit or paste the key into this public repository.

## Pre-production gates
- unit/contract tests pass;
- Wrangler dry-runs pass;
- Cloudflare control + market Workers connected by native Git deployment;
- live health + pre-freeze market-block acceptance passes;
- all three real Action schemas accepted in the GPT;
- fresh pre-market dry-runs for NE @ SEA and SF @ LA;
- V4.2 vs V5 parameter-parity audit on the same research snapshot;
- paid Odds API acceptance only after frozen state;
- tracker run-write and confirmed-bet write acceptance pass;
- NFL reception result-source and automatic-settlement acceptance pass;
- V4.2 remains immutable rollback until V5 acceptance passes;
- only then tag the 2026 season lock.
