# A-League Player Volume V1

Status: active build on Platform V1. Not production-ready.

## Locked product decision
One market-blind A-League Men match engine with three coherent stat heads:

1. `PLAYER_SHOTS` — primary
2. `PLAYER_SHOTS_ON_TARGET` — primary
3. `GOALKEEPER_SAVES` — secondary

The shared latent object is attacking volume. The engine first estimates team shot environments, then allocates shot opportunity to players, thins shots into shots on target, and converts opposition shots on target into goalkeeper save opportunity.

V1 does **not** include goalscorers, assists, passes, tackles, cards or corners. Those require distinct event-generation assumptions and are intentionally outside the first calibration surface.

## Production lifecycle

`versioned source pack -> fixture/run lock -> current market-blind research -> research checkpoint -> deterministic P_model -> immutable freeze -> post-freeze market adapter -> exact edge/ranking -> receipts`

This module inherits `betting_platform_v1/ARCHITECTURE.md`. No A-League code may weaken the shared source-lock, freeze, identity, or market-blindness rules.

## Market plan

The probability engine is sportsbook-agnostic. Post-freeze adapters may accept:

- Odds API rows if/when a supported A-League player market is available;
- Bet365/manual screenshot extraction;
- other explicitly approved post-freeze sources.

A market source can never create or alter P_model. Only exact frozen player/stat/threshold combinations are eligible; no interpolation after market access.

## Data plan

### Durable machine-ingested priors
- FBref A-League player/team/opponent standard, shooting and goalkeeper tables where available.
- Official A-League/club fixture, squad and availability evidence where a stable permitted feed or published page can be used.
- Repository-derived rolling and opponent-adjusted features.

### Research-only enrichment
Advanced sites may be used during Layer 1 for human/web research when permitted, but are not automatically promoted into scheduled GitHub ingestion. In particular, FotMob is treated as research enrichment rather than a production scraper dependency unless an approved/licensed access route is added.

See `SOURCE_POLICY.md` and `source_registry.json`.

## V1 quantitative heads

### Team shot environment
Estimate each team's expected shots before player allocation using own attacking volume, opponent shots allowed, home/away, recent/current-role evidence and lineup/system adjustments.

### Player shots
Allocate the team shot environment across projected players using shrunk shot shares, projected minutes and explicit role scenarios. Count variance uses a Negative Binomial parameterization (`mean`, `dispersion`).

### Player shots on target
Model `P(SoT | shot)` with a shrunk player accuracy prior and current role/shot-quality evidence. Under the Poisson-Gamma thinning interpretation, the marginal SoT count retains the parent Negative Binomial dispersion.

### Goalkeeper saves
Model opposition SoT volume and a shrunk save probability, adjusted for expected goalkeeper minutes. The initial V1 count head uses the same thinning-compatible Negative Binomial representation, with calibration challenges required before production sign-off.

## Required acceptance gates

- [ ] source ingestion produces canonical, hashed A-League assets
- [ ] stable player/team identity map
- [ ] historical reconstruction for at least two completed seasons where source coverage permits
- [ ] rolling priors generated without future leakage
- [ ] player minutes/role scenario contract implemented
- [ ] team-shot and player-allocation backtest
- [ ] SoT conditional calibration backtest
- [ ] goalkeeper saves calibration backtest
- [ ] market-blind research checkpoint Worker
- [ ] immutable multi-head freeze with per-player hashes
- [ ] separate post-freeze market Worker
- [ ] screenshot/manual market adapter
- [ ] Odds API capability probe/adaptor (non-authoritative until A-League player markets are confirmed live)
- [ ] repository CI PASS
- [ ] Cloudflare deployment health PASS
- [ ] clean Custom GPT schema import
- [ ] live future-fixture end-to-end acceptance

No production-ready claim is permitted before every applicable gate passes.
