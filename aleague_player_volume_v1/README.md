# A-League Player Volume V1

Status: active build on Platform V1. **Not production-ready.**

## Locked product decision
One market-blind A-League Men match engine with three coherent stat heads:

1. `PLAYER_SHOTS` — primary
2. `PLAYER_SHOTS_ON_TARGET` — primary
3. `GOALKEEPER_SAVES` — secondary

The shared latent object is attacking volume. The engine first estimates team shot environments, allocates shot opportunity to players, thins shots into shots on target, and converts the opponent's frozen shots-on-target environment into goalkeeper save opportunity.

V1 does **not** include goalscorers, assists, passes, tackles, cards or corners. Those require distinct event-generation assumptions and are intentionally outside the first calibration surface.

## Production lifecycle

`versioned source pack -> fixture/run lock -> current market-blind research -> research checkpoint -> deterministic P_model -> immutable freeze -> post-freeze market adapter -> exact edge/ranking -> receipts`

This module inherits `betting_platform_v1/ARCHITECTURE.md`. No A-League code may weaken shared source-lock, freeze, identity or market-blindness rules.

## Market plan

The probability engine is sportsbook-agnostic. Post-freeze adapters may accept:

- Bet365/manual screenshot extraction;
- Odds API rows only if a relevant A-League player market is actually supported at runtime;
- other explicitly approved post-freeze sources.

A market source can never create or alter P_model. Only exact frozen player/stat/threshold combinations are eligible; no probability interpolation is permitted after market access. The evaluator supports milestone markets, half-point totals and integer push lines from exact frozen count probabilities. Default selection policy is `AT_LEAST` / `OVER`.

## Data plan

### Core structured outcome rail
- **API-Football / API-Sports** is the primary machine-ingested candidate for fixtures, team shots/SOT, player minutes/shots/SOT and goalkeeper saves. A-League Men is league id `188`.
- Completed fixture details are requested in batches of up to 20 IDs where provider coverage supports embedded statistics/player blocks.
- Raw provider payloads are never the runtime contract. They are normalized into canonical event rows, reconciled, hashed and published as a versioned research pack.
- Free-plan historical depth is never assumed; a coverage gate must prove the seasons available before a backtest is accepted.

### Open advanced layer
- **SkillCorner Open Data** is an approved MIT-licensed advanced-data source. Its 2024/25 A-League release provides ten tracking matches plus season-level Physical, Off-Ball Runs and Passing aggregates.
- V1 derives a pinned advanced-role profile from these aggregates for feature discovery, role similarity and prior-competition/current-role research.
- The open sample is not large enough to justify fitted production coefficients by itself.

### Current-information research
- Official A-Leagues/club sources are preferred for fixture confirmation, squads, availability, suspensions, transfers, expected XI and coaching/system change.
- FotMob and Transfermarkt remain research-only enrichment unless an explicitly approved access route is added.
- FBref is research/reconciliation only and is not an automated predictive database dependency.

See `SOURCE_POLICY.md`, `source_registry.json` and `ADVANCED_DATA.md`.

## V1 quantitative heads

### Team shot environment
Estimate each team's expected shots before player allocation using leakage-safe own attacking volume, opponent shots allowed, home/away, current-role evidence and lineup/system adjustments.

### Player shots
Historical player evidence is represented as a per-90 shot propensity. Current projected minutes enter once at run time:

`weight_i = qbase_shots_per90_i * projected_minutes_i/90 * role_multiplier_i`

Weights are normalized to the frozen team shot environment with an explicit unmodelled/bench bucket. Count variance uses a calibrated Negative Binomial parameterization.

### Player shots on target
Model `P(SoT | shot)` with hierarchical shrinkage plus evidence-supported current-role/shot-quality adjustments. Player SOT mean is generated from the player's frozen shot process, not entered independently.

### Goalkeeper saves
Goalkeeper saves are generated from the **opponent's frozen team SOT mean** and a shrunk `P(save | SoT)` estimate. This preserves cross-head coherence.

## Implemented build foundation

- deterministic Negative Binomial count ladders and shrinkage primitives;
- leakage-safe pre-match team/player/keeper QBASE builders;
- canonical API-Football parsing, reconciliation and hash-locked publication helpers;
- market-blind current-research contract;
- coherent atomic multi-head freeze and receipts;
- strict screenshot/manual market-row normalization;
- exact post-freeze pricing, push-aware EV, best-price deduplication and cross-head ranking;
- pinned SkillCorner advanced-role profile builder;
- dedicated CI/integration workflows.

These are implementation milestones, **not production acceptance**.

## Required acceptance gates

- [ ] live API-Football source probe confirms required A-League coverage and accessible historical seasons
- [ ] source ingestion produces canonical, hashed A-League outcome assets
- [ ] stable API-Football / SkillCorner / current-roster identity bridge
- [ ] historical reconstruction for at least two completed seasons where permitted coverage allows
- [ ] rolling priors generated without future leakage on real data
- [ ] advanced SkillCorner role profiles built and coverage-audited
- [ ] player minutes/role scenario contract validated on real fixtures
- [ ] team-shot and player-allocation out-of-sample backtest
- [ ] SOT conditional calibration backtest
- [ ] goalkeeper saves calibration backtest
- [ ] distribution-family challenge (NB2 vs credible alternatives) passes
- [ ] market-blind research checkpoint Worker
- [ ] immutable multi-head freeze Worker with durable persistence
- [ ] physically separate post-freeze market Worker
- [ ] screenshot/manual market adapter live acceptance
- [ ] Odds API capability probe/adaptor remains fail-closed where A-League player props are unsupported
- [ ] repository CI PASS on production head
- [ ] Cloudflare deployment health PASS
- [ ] clean Custom GPT schema import
- [ ] live future-fixture end-to-end acceptance

No production-ready claim is permitted before every applicable gate passes.
