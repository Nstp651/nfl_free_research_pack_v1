# A-League Player Volume V1 — Source Policy

## Principle
Use the richest reliable evidence stack we can support without making production depend on brittle/unapproved scraping or a paid feed Nick has not approved.

## Core machine source — API-Football

API-Football / API-Sports is the primary V1 structured ingestion candidate.

A-League Men uses league id `188`. The provider exposes fixtures, team statistics and per-fixture player statistics. The player fixture payload includes minutes, position, total shots, shots on target and goalkeeper saves, which maps directly to the three V1 heads.

The free tier currently provides 100 requests/day with all endpoints/competitions but limited historical seasons. V1 therefore uses quota-efficient batching, immutable local/canonical caching and explicit coverage checks. Historical depth must be measured from the live API before production acceptance; it must never be assumed.

The API credential must be stored as `API_FOOTBALL_KEY` in GitHub Actions/Cloudflare secrets and must never be committed.

Runtime still consumes published canonical assets, not the live API.

## Open advanced layer — SkillCorner Open Data

SkillCorner's public `opendata` repository is MIT-licensed and currently contains a sample of ten 2024/25 Australian A-League matches with broadcast tracking, Dynamic Events and phases of play, plus season-level Physical, Off-Ball Runs and Passing aggregates.

This is valuable for:

- designing role/position feature families;
- testing whether off-ball/physical profiles separate high-volume shooters from nominally similar players;
- creating qualitative priors for import/role translation;
- validating tactical hypotheses.

It is **not** large enough to serve as the primary historical outcome dataset and must not be overfit.

## Official A-Leagues / clubs
Use as the preferred current-information evidence for fixtures, squad announcements, injuries/suspensions, transfers, manager/system changes and role quotes. Automate only stable approved routes; otherwise consume as Layer 1 research evidence.

## FBref — research/reconciliation only
FBref remains useful for human spot checks and historical context, but it is **not an automated ingestion source for V1**. Sports Reference's current data-use terms restrict automated access/use and it announced the loss/removal of its advanced soccer data provider in January 2026. V1 therefore does not build or refresh its predictive database from FBref.

## FotMob — research only
FotMob can be useful for live research context such as xG/xA, shot maps, box touches and chance creation when visible. Do not create an unattended V1 scraper dependency.

## Transfermarkt — research only initially
Useful for transfer history, prior clubs and role context. Do not schedule extraction unless a separately approved route is established.

## Paid advanced feeds — optional
Stats Perform/Opta, Wyscout, Hudl StatsBomb/SkillCorner commercial products or equivalent could materially improve event/tracking depth. They are not required for V1 and must not create an unapproved cost.

## Market-source separation
Sportsbook/Odds API market data is prohibited from Layers 0–2. It is accepted only by the physically separate post-freeze market service.

## Anti-leakage requirement
Historical QBASE generation may use only information that existed before the target fixture. Retrieval timestamps do not make retrospective season aggregates safe. Builders reconstruct rolling pre-match features from fixture/player-match history and test that future-event mutations cannot change prior snapshots.
