# A-League Player Volume V1

Status: active build on Platform V1. **Not production-ready.**

Current canonical model version: `ALEAGUE_PLAYER_VOLUME_V1_0.3.0`.

## Locked product decision

One market-blind A-League Men attacking-volume engine with three coherent stat heads:

1. `PLAYER_SHOTS` — primary
2. `PLAYER_SHOTS_ON_TARGET` — primary
3. `GOALKEEPER_SAVES` — secondary

The shared latent object is attacking volume. The engine estimates each team shot environment, allocates shot opportunity to players, thins player shots into shots on target, reconstructs team SOT, then converts the **opponent's frozen SOT environment** into goalkeeper save opportunity.

V1 intentionally excludes goalscorers, assists, passes, tackles, cards and corners.

## Production lifecycle

`versioned source pack -> persistent fixture/run lock -> market-blind research -> research checkpoint -> deterministic quantitative inputs -> immutable model-input receipt -> atomic P_model freeze -> immutable freeze receipt -> physically separate market service -> exact EV/ranking`

This module inherits `betting_platform_v1/ARCHITECTURE.md`. No A-League code may weaken shared source-lock, fixture identity, checkpoint, freeze or market-blindness rules.

## Two-Worker security boundary

### Research / freeze Worker

Cloudflare service name: `aleague-player-volume-research-v1`.

Server-owned state machine:

`NEW -> RESEARCH_COMPLETE -> FROZEN`

Implemented routes:

- `GET /health`
- `POST /v1/runs`
- `GET /v1/runs/{run_id}`
- `POST /v1/runs/{run_id}/research`
- `GET /v1/runs/{run_id}/research`
- `POST /v1/runs/{run_id}/freeze`
- `GET /v1/runs/{run_id}/model-inputs`
- `GET /v1/runs/{run_id}/frozen`

A run locks the exact deployment source commit plus pack/QBASE/advanced revisions. Research may be replaced only before freeze. The Worker computes P_model itself; a client cannot submit a finished probability artifact.

At freeze the Worker persists two independent receipts:

- `model_input_receipt_sha256` — exact quantitative inputs that created P_model;
- `freeze_receipt_sha256` — exact immutable probability artifact.

That preserves future exact-replay evidence rather than merely storing the final probabilities.

### Market Worker

Cloudflare service name: `aleague-player-volume-market-v1`.

Implemented routes:

- `GET /health`
- `POST /v1/evaluate`

The market Worker accepts a `run_id` and market rows only. It retrieves the immutable freeze one-way through a Cloudflare service binding to the research Worker, verifies the freeze receipt and every head hash, and then evaluates prices. The research Worker has no route or binding back to market data.

OpenAPI deployment templates live under `openapi/`. Their server host is intentionally a placeholder until Cloudflare deployment has produced the final URLs.

## Market plan

The probability engine is sportsbook-agnostic. Post-freeze adapters may accept:

- Bet365/manual screenshot extraction;
- Odds API rows only if a relevant A-League player market is actually supported at runtime;
- other explicitly approved post-freeze sources.

A market source can never create or alter P_model. Only exact frozen player/stat/threshold combinations are eligible; no post-market probability interpolation is allowed. The evaluator supports milestones, half-point totals and integer push lines, best-price deduplication and joint ranking of Shots/SOT/Saves. Default selection policy is `AT_LEAST` / `OVER`; UNDER is available for audit but not recommended by default.

## Data plan

### Core structured outcome rail

- **API-Football / API-Sports** is the primary structured-feed candidate for fixtures, team shots/SOT, player minutes/shots/SOT and goalkeeper saves. A-League Men is league id `188`.
- Completed fixture details are requested in batches of up to 20 IDs where provider coverage supports embedded statistics/player blocks.
- Raw provider payloads are normalized, reconciled, hash-addressed and published as canonical assets.
- Historical depth is never assumed. A live coverage probe must prove accessible seasons before real backtests are accepted.

### Open advanced layer

- **SkillCorner Open Data** is an approved MIT-licensed advanced-data source pinned to commit `c1e17a0cc3e07e1774b52d929c1a0b85115143fc`.
- A-League role profiles preserve player + team + position-group identity rather than averaging multi-role players together.
- Goalkeeper rows remain source-validated but are excluded from the attacking advanced-feature completeness denominator.
- The live pinned build passes the unchanged 90% attacking three-family completeness gate.
- SkillCorner remains research/feature-discovery support until any fitted advanced coefficient demonstrates out-of-sample value.

### Current-information research

- Official A-Leagues/club sources are preferred for fixtures, squads, availability, suspensions, transfers, expected XI and coaching/system changes.
- FotMob and Transfermarkt remain research-only enrichment unless an approved access route is added.
- FBref is research/reconciliation only and is not an automated predictive database dependency.

See `SOURCE_POLICY.md`, `source_registry.json` and `ADVANCED_DATA.md`.

## Quantitative construction

### Team shot environment

Estimate expected team shots from leakage-safe own attacking volume, opponent shots allowed and current role/system evidence.

### Player shots

`weight_i = qbase_shots_per90_i * projected_minutes_i/90 * role_multiplier_i`

Player weights plus an explicit unmodelled bucket are normalized to the complete frozen team shot mean. Minutes therefore enter only once.

### Player SOT

`mu_sot_i = mu_shots_i * P(SOT | shot)_i`

SOT cannot be entered as an unrelated mean.

### Goalkeeper saves

`mu_saves_gk = opponent_team_sot_mean * P(save | SOT)_gk * projected_minutes/90`

Saves therefore remain coherent with the opponent attacking process.

Count variance currently uses NB2 and is challenged against a same-mean Poisson baseline in historical validation.

## Historical validation architecture

Three evidence levels are deliberately separated.

### 1. Conditional distribution replay

Uses the realised target appearance set only to decide which distributions are scored. All parameters/minutes priors are pre-target. This may calibrate distributions and dispersion, but **cannot** prove player-selection edge or production readiness.

### 2. Persisted pre-match participant replay

Uses a hash-addressed snapshot captured strictly before kickoff for participant inclusion, availability and projected minutes. DNP/no-provider-appearance rows are recorded as void/unsettled rather than fake zero-count losses. Current implementation uses neutral historical role multipliers, so this is stronger selection evidence but still cannot prove final V1 edge.

### 3. Exact model-input replay

Every live production freeze now persists the exact pre-freeze quantitative inputs and their receipt. This is the required forward-going rail for exact reproduction of role multipliers, SOT adjustments, team environments, save rates and confidence/fragility from historical live runs.

## Pre-registered backtest gates

Before seeing the real holdout, V1 registered these initial acceptance thresholds:

- minimum observations: Shots `500`, SOT `500`, Saves `150`;
- maximum threshold ECE: `0.07`;
- maximum absolute mean-bias ratio: `0.12`;
- minimum NLL improvement versus independent baseline: `0.5%`;
- minimum milestone-Brier improvement versus independent baseline: `0.2%`;
- NB2 may not regress versus same-mean Poisson by more than `0.2%` on NLL or milestone Brier.

Any later threshold change requires an explicit model-version change and written rationale; the holdout may not be used to tune the gate after the fact.

## Implemented and CI-verified

- [x] deterministic NB2 count ladders and shrinkage primitives
- [x] leakage-safe player/team/keeper QBASE builders
- [x] API-Football parser, reconciliation and hash-locked publication machinery
- [x] quota-conscious batch historical backfill workflow
- [x] pinned SkillCorner advanced-role builder and live open-data acceptance
- [x] market-blind research contract
- [x] coherent atomic multi-head freeze
- [x] immutable model-input and probability receipts
- [x] persistent Durable Object run/checkpoint/freeze state machine
- [x] physically separate post-freeze market service and one-way binding design
- [x] manual/screenshot market normalization
- [x] exact push-aware pricing, best-price dedupe and cross-head ranking
- [x] leakage-safe backtest/calibration engine with training-only dispersion selection
- [x] conditional historical replay with production-use block
- [x] persisted pre-match participant snapshot contract and participant replay
- [x] research + market Worker Node tests inside the A-League CI suite
- [x] OpenAPI deployment templates

These are implementation milestones, **not production acceptance**.

## Remaining production acceptance gates

- [ ] live API-Football probe confirms required A-League fields and accessible historical seasons
- [ ] real canonical API-Football outcome assets published with coverage PASS
- [ ] stable provider/current-roster identity bridge on real data
- [ ] at least two completed seasons reconstructed if permitted coverage allows
- [ ] real-data rolling-prior leakage audit PASS
- [ ] real-data minutes/role scenario validation PASS
- [ ] team-shot/player-allocation holdout PASS
- [ ] SOT calibration holdout PASS
- [ ] goalkeeper saves calibration holdout PASS
- [ ] NB2 distribution-family challenge PASS
- [ ] historical pre-match lineup/research snapshots sufficient for selection replay, or an explicitly documented limitation remains
- [ ] exact model-input replay acceptance once persisted live-run history exists
- [ ] research/freeze Worker deployed and live health PASS
- [ ] market Worker deployed with one-way service binding and live health PASS
- [ ] manual/screenshot post-freeze market acceptance PASS
- [ ] Odds API A-League player-prop capability probe remains fail-closed if unsupported
- [ ] production-head repository CI PASS
- [ ] final OpenAPI hosts generated and clean Custom GPT schema import PASS
- [ ] live future-fixture end-to-end acceptance PASS

**No production-ready claim is permitted before every applicable production gate passes.**
