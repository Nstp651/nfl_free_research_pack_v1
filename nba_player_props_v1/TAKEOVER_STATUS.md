# NBA V1 takeover evidence

Status: **PRODUCTION CANDIDATE — NOT PRODUCTION READY. PR #20 remains draft/unmerged.**

This file records the current takeover state after source correction, quantitative promotion, runtime/Worker implementation and production-artifact authoring. NBL production remains unchanged.

## Accepted source / historical state

The pinned five-season build originally produced 139,809 validated NBA player-games with zero duplicate ESPN player/game keys and complete timestamps.

Independent source reconciliation plus final-box adjudication identified 14 inconsistent complete games. The production source gate removes the **entire game** for every adjudicated inconsistency; it never patches one player/stat or removes one team only.

Corrected accepted history:
- rows: **139,529**
- rows removed: **280**
- complete games removed: **14**
- history SHA-256: `2e6926aa87ccebafbf938322f8facefeb54de63eb22f924dc2793afc61750b25`
- deterministic source acceptance receipt: `ecb23250f2c9ec8e3ed6bfd72034d195fc39f97e93f24c8c14f66563c6937350`

The official NBA schedule endpoint remained HTTP-blocked in the source probes; the market-blind ESPN scoreboard source passed as the current fixture fallback. Player-tracking specialist endpoints were blocked/timed out and remain feature-gated rather than treated as zero or required for base V1.

## Independent QBASE promotion

Both heads were rerun on corrected history under the locked temporal protocol:
- expanding 2024/2025 validation folds;
- 2026 untouched holdout;
- no holdout model-family reselection;
- early-season cohort non-regression requirement;
- specialist metrics excluded unless separately promoted.

Both selected `glm_nb` and passed `PROMOTED_CORE_V1` with no restricted cohorts.

### Assists
- model version: `NBA_ASSISTS_QBASE_V1.0.0`
- corrected-history holdout Brier ~0.05907 vs shrunk-Poisson baseline ~0.06126
- corrected-history holdout NLL ~1.7959 vs baseline ~1.8540
- holdout sample ~28.2k player-games

### Rebounds
- model version: `NBA_REBOUNDS_QBASE_V1.0.0`
- corrected-history holdout Brier ~0.05217 vs baseline ~0.05424
- corrected-history holdout NLL ~2.2089 vs baseline ~2.3026
- holdout sample ~28.2k player-games

These metrics are probability/count diagnostics on a fixed threshold grid, not betting-return claims.

## Reproducibility hardening

A subsequent audit found microscopic solver/BLAS differences across otherwise identical CI events. That was treated as an integrity issue rather than ignored.

The current challenge pipeline now:
- quantizes exported production numeric parameters to 10 decimal places;
- scores validation/holdout from the exact exported parameters;
- forces single-thread numerical libraries in CI;
- reruns both complete temporal challenges twice;
- byte-compares the two evidence JSON outputs;
- only then permits QBASE promotion/runtime-asset staging;
- commits runtime assets if and only if staged assets differ;
- requires a generated promotion commit to reproduce with zero diff.

The final bot-generated asset commit/follow-up CI still must be observed green before this gate is closed.

## Implemented Research / Freeze runtime

Implemented under `nba_player_props_v1/worker/`:
- sanitized ESPN fixture source with canonical `America/New_York` league-date membership;
- sanitized current roster/status/injury source;
- exact deployment Git source pin;
- manifest/file-SHA runtime asset loader;
- deterministic player/team runtime prior pack;
- season-aware player/team counts and trade detection via ESPN IDs;
- market-blind research seed with player and team environment priors;
- strict research checkpoint contract;
- server-enforced 1–2 game queue;
- persistent `NbaSlateRun` Durable Object;
- exact fixture locks through every checkpoint;
- server typed transforms only: runtime score, minutes, role opportunity, lineup dependency;
- no client/free-form final mean path;
- strict prior-competition translation framework with no universal fallback;
- exact Poisson/NB2 count distributions and integer push grids;
- atomic whole-slate freeze;
- per-head `head_model_sha256`;
- per-player `player_model_sha256`;
- slate integrity index and immutable freeze receipt;
- late-news `FROZEN_BUT_INVALIDATED` state without P_model mutation;
- post-freeze market-access grant.

Cloudflare config exists for Worker name `nba-player-props-research-v1` with `SLATE_RUNS -> NbaSlateRun` Durable Object.

## Implemented Market runtime

Implemented under `nba_player_props_v1/market_worker/`:
- separate `NbaMarketRun` Durable Object;
- Research Worker service binding;
- fresh server market-access grant before any sportsbook request;
- The Odds API NBA event discovery and exact frozen fixture resolution;
- only four approved market keys;
- Australian region default (`au`) to align the production bookmaker stack and minimize credits;
- strict one-to-one frozen player mapping;
- Overs-only ingestion;
- current API snapshot replacement instead of stale-price accumulation;
- post-freeze Bet365/manual screenshot snapshot replacement;
- market capture time must be at/after `frozen_at`;
- exact integer/half threshold lookup only, no interpolation;
- current best exact price merge;
- player/head hash binding through evaluation;
- push-aware EV, push-adjusted market probability and tracker-compatible edge;
- BEST SINGLE, Top 10 combined, Assists positives, Rebounds positives, NO BET.

Cloudflare config exists for Worker name `nba-player-props-market-v1`, `MARKET_RUNS -> NbaMarketRun`, and service binding `RESEARCH_SERVICE -> nba-player-props-research-v1`.

## Production GPT package implemented

- `NBA_ASSISTS_REBOUNDS_4_LAYER_MASTER_PRODUCTION_V1.0.md`
- `GPT_INSTRUCTIONS_PRODUCTION_V1.0.md`
- `openapi_v1.yaml`
- `market_openapi_v1.yaml`
- `TRACKER_INTEGRATION_PRODUCTION_V1.0.md`
- `LAUNCH_PROMPT_PRODUCTION_V1.0.md`
- `INSTALL_PRODUCTION_V1.0.md`
- `PRODUCTION_ACCEPTANCE_PROMPT_V1.0.md`

The established shared Bet Tracker is reused; no new tracker database/Worker was introduced.

## Still-unpassed release gates

1. Final current branch CI must pass after the latest hash/market-region/integrity changes.
2. CI must actually commit the four deterministic runtime assets and the generated promotion commit must rebuild byte-identically with zero diff.
3. Cloudflare account deployment/configuration has not been executed from this session because the Cloudflare integration is not exposed to the current tool session. No account changes have been made.
4. Research and Market Worker live health/bindings/secrets must be verified.
5. One real future NBA ET slate must complete the entire server-enforced Layer 1 checkpoint loop.
6. That same run must atomically freeze Layer 2 before any market access.
7. Real The Odds API player props must resolve/evaluate through the Market Worker.
8. Layer 4 global ranking must complete and the existing Bet Tracker model run must be written after ranking.
9. A post-freeze Bet365/manual screenshot refresh must prove identical `run_id`, `frozen_at`, freeze receipt and frozen player/head hashes, with no Layer 1 rerun or P_model mutation.
10. Only after all required live gates pass may PR #20 be considered for merge and V1 called production-ready.

No green unit/CI suite, synthetic market test or documentation artifact substitutes for the live acceptance gates.
