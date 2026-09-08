# NBA V1 Free Data Source Audit

Audit date: 2026-09-08

This document records the initial production-source decision. Every source still has to pass executable acceptance tests before its fields can enter QBASE.

## Decision

Use a **two-layer source spine**:

1. **Licensed historical backbone — SportsDataverse/hoopR release assets**
   - schedule
   - player box scores
   - team box scores
   - play-by-play
   - rosters / game rosters / player crosswalks where available
2. **Official NBA enrichment — NBA CDN + maintained NBA Stats V3 endpoints**
   - official current schedule/scoreboard identity
   - traditional/advanced/player-tracking box endpoints
   - rotation/lineup-capable endpoints where reliability gates pass
   - specialist tracking only after coverage/schema acceptance

Do not make a community dump the production authority when its redistribution/license status is unclear. Community sources can be independent QA comparators.

## Candidate matrix

| Source | Depth | Freshness | Identity | Richness | Automation | License/access | Maintenance risk | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| SportsDataverse / hoopR processed NBA releases | 2002→current for core ESPN NBA datasets | automated | strong ESPN IDs + crosswalk tooling | box + PBP + schedule | excellent GitHub release consumption | explicit open data licensing | low/moderate | **PRIMARY BACKBONE** |
| NBA official CDN live/static data | current season + per-game live data | official/current | canonical NBA game/team/player IDs | schedule, scoreboard, live box/PBP | good with browser-like headers | public official endpoint; terms must be respected | low/moderate | **PRIMARY CURRENT IDENTITY** |
| NBA Stats / `nba_api` V3 endpoints | multi-season varies by endpoint | official/current when endpoint healthy | canonical NBA IDs | advanced + tracking | workable in GitHub Actions, but endpoint-specific reliability | public endpoint, throttling/schema risk | moderate/high | **RECEIPTIZED ENRICHMENT** |
| SportsDataverse `hoopR-nba-stats-data` | NBA Stats-backed historical pipeline | actively maintained | NBA IDs | PBP/lineup/traditional and expanding | strong pipeline pattern | open repository; dataset license must be recorded per consumed asset | moderate | **PREFERRED ENRICHMENT CACHE WHERE COVERAGE FITS** |
| `llimllib/nba_data` | 2009-10→current; rich parquet | every ~4h workflow | NBA IDs | player game advanced stats + ESPN analytics | excellent | no explicit production data license confirmed in initial audit | moderate | **QA ONLY UNTIL LICENSE GATE PASSES** |
| direct ad-hoc scraping of NBA.com pages | variable | current | variable | potentially rich | brittle | page/access drift | high | **REJECT AS DATA SPINE** |
| betting/tip/projection sites | irrelevant | current | variable | market-contaminated | variable | variable | high | **PROHIBITED LAYERS 0–2** |

## Canonical historical normalized table

`nba_player_games_v1` grain: one NBA player × game.

Required core columns:

- source season
- season type
- game_id_nba (nullable only when source genuinely lacks it)
- game_id_espn
- game_start_utc / game_date_et
- player_id_nba
- player_id_espn
- player_name canonical + source names
- team_id_nba / team_id_espn
- opponent IDs
- home flag
- started flag when available
- minutes
- assists
- rebounds_total
- rebounds_offensive
- rebounds_defensive
- turnovers
- FGM / FGA / 3PM / 3PA / FTM / FTA
- team/opponent totals needed for possession/miss context
- provenance record IDs

Every row must be uniquely keyed and carry enough source metadata to reproduce its join path.

## Specialist metric registry

The builder writes `specialist_metric_registry.json`. A metric cannot be a production feature unless its status is `AVAILABLE` for the training interval used by that model version.

Allowed statuses:

- `AVAILABLE` — accepted coverage/schema/reconciliation for intended training/runtime use.
- `PARTIAL` — valid only for a subset; can be research evidence or a separately missingness-aware experiment, not silently treated as universally observed.
- `UNAVAILABLE` — source does not provide it.
- `BLOCKED` — endpoint/access currently prevents reliable automation.
- `NOT_RELIABLE` — observed but fails stability/completeness/reconciliation gates.

### Initial metric hypotheses — not final acceptance

| Metric | Initial status | Intended path / note |
|---|---|---|
| minutes / starts | AVAILABLE | core box/schedule; starts cross-checked where present |
| assists / rebounds / ORB / DRB / turnovers / FGA / FGM | AVAILABLE | core player box |
| possessions / pace | AVAILABLE_DERIVED candidate | deterministic team box formula / accepted advanced box |
| AST% / usage / ORB% / DRB% / TRB% | AVAILABLE_DERIVED candidate | lagged box-derived or official advanced box; formula/version pinned |
| touches | PARTIAL pending gate | NBA player-track V3 exposes per-game touches |
| passes | PARTIAL pending gate | NBA player-track V3 exposes per-game passes |
| secondary assists | PARTIAL pending gate | NBA player-track V3 exposes per-game secondary assists |
| rebound chances O/D/total | PARTIAL pending gate | NBA player-track V3 exposes per-game chance counts |
| potential assists | PARTIAL pending gate | official NBA tracking metric exists; endpoint/history/reliability must be proven |
| time of possession | PARTIAL pending gate | official NBA tracking metric exists; endpoint/history/reliability must be proven |
| drives | PARTIAL pending gate | official NBA tracking metric exists; endpoint/history/reliability must be proven |
| box-outs | PARTIAL/UNRESOLVED | use only if a maintained official endpoint passes game-level historical coverage gates |
| contested rebound chances | UNRESOLVED | distinguish actual contested/uncontested rebounds from chance fields; do not conflate |
| PnR ball-handler role | NOT_RELIABLE for V1 QBASE until proven | play-type/Synergy-style data are not assumed freely/stably available |
| lineup-specific creation share | AVAILABLE_DERIVED candidate | derive from PBP/on-court or validated lineup data; sample-shrunk |
| lineup-specific rebound share | AVAILABLE_DERIVED candidate | derive from PBP/on-court/box context; sample-shrunk |
| teammate shot conversion | AVAILABLE_DERIVED candidate | lagged teammate/team finishing; passing-recipient data only if accepted |
| opponent miss / shot-location environment | AVAILABLE_DERIVED candidate | box/PBP/shot locations where present |
| rest / B2B / home-away | AVAILABLE_DERIVED | deterministic from locked schedule |
| travel | PARTIAL_DERIVED | venue sequence and distance only if venue coordinates are versioned; otherwise rest/home remain |
| injuries / availability | AVAILABLE_CURRENT, not historical-QBASE by default | official injury report + current research receipt |

`AVAILABLE_DERIVED candidate` is an audit notation only; code promotion requires deterministic formula tests and temporal cutoff tests.

## Why player-track V3 matters

The maintained V3 player tracking box schema contains per-player:

- minutes
- rebound chances offensive
- rebound chances defensive
- rebound chances total
- touches
- secondary assists
- free-throw assists
- passes
- assists
- contested/uncontested field-goal fields

This is a material upgrade over the NBL historical feature set if historical completeness passes. It does **not** by itself provide every desired metric (for example potential assists/time of possession/drives), so those remain separately gated.

## Identity design

Production uses a deterministic crosswalk table:

`nba_identity_crosswalk_v1`

Keys include:

- nba_game_id ↔ espn_game_id
- nba_team_id ↔ espn_team_id ↔ canonical team code
- nba_player_id ↔ espn_player_id ↔ canonical normalized name + date-valid team membership

Matching priority:

1. exact published crosswalk ID;
2. exact game/team/date constrained ID join;
3. normalized name only when team/date makes the match unique;
4. otherwise reject unresolved ambiguity.

A fuzzy name match alone is never production identity authority.

## Immutable source receipt

Each source build emits `data/source_receipt.json` containing at minimum:

- schema version
- built_at_utc
- market_data=false
- builder git commit
- upstream source names
- upstream immutable release/tag/commit identifiers
- each downloaded asset URL + byte SHA-256 + size
- row counts by season/source
- unique games/players/teams
- duplicate counts
- timestamp non-null rates
- identity resolution rates
- specialist metric registry hash
- normalized player-game table SHA-256
- latest completed game timestamp
- current-season freshness
- exclusions/errors

Runtime assets publish only after this receipt passes source acceptance.

## Source acceptance gates

Core historical promotion requires:

- deterministic rebuild hashes for pinned inputs;
- ≥99.9% unique canonical player-game key after legitimate multi-team normalization rules;
- zero unresolved duplicate canonical player-game rows;
- ≥99.9% game timestamp coverage in training rows;
- exact assists/rebounds/core-box reconciliation on sampled games across every training season;
- current-season source freshness within configured refresh SLA during season;
- identity coverage threshold set before model training;
- explicit season-by-season row/game/player counts;
- no future timestamp leaking into pregame features;
- all specialist fields separately coverage-audited.

## Current research/news hierarchy

1. Official NBA injury report.
2. Official NBA/team transactions and roster status.
3. Official team practice/shootaround/coach/status reporting.
4. Confirmed lineup information from official/reputable direct sources.
5. Established team beat reporters.
6. Reputable national reporting for context.

Every evidence record stores URL, title, checked_at, published_at when known, source tier, evidence type, subject and contradiction status.

## Odds API market source

Post-freeze only.

NBA keys to request:

- `player_assists`
- `player_assists_alternate`
- `player_rebounds`
- `player_rebounds_alternate`

For the **current** event-odds endpoint, the official quota formula is `unique returned markets × regions`. Therefore four returned NBA prop keys in one region cost at most 4 credits per event; a 10-game slate is at most 40 credits before any targeted refreshes. The `10 ×` multiplier applies to historical event-odds, which this production market workflow does not need. V1 budget policy:

- obtain event IDs from the quota-free current events endpoint;
- one canonical full-slate event-odds pull after global freeze;
- default one required region, not multiple redundant regions;
- record `x-requests-last`, `x-requests-used`, `x-requests-remaining` on every pull;
- targeted refreshes only for shortlisted/requested games rather than blind repeated whole-slate refreshes;
- screenshot support for Bet365/manual books remains credit-free and post-freeze.

## Rejected shortcuts

- No market odds in historical features.
- No betting consensus as injury/role evidence.
- No universal NCAA/G League/international translation factor.
- No zero fill for unavailable tracking fields.
- No direct Cloudflare runtime dependency on fragile bulk historical endpoints.
- No model promotion merely because a richer feature reduces MAE; it must improve temporal OOS betting-threshold calibration without leakage.