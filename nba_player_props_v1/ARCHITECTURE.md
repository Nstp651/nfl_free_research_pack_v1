# NBA Assists + Rebounds V1 Architecture

Status: **PRODUCTION CANDIDATE — LIVE ACCEPTANCE PENDING.** PR #20 remains draft. NBA is isolated under `nba_player_props_v1/`; NBL production is unchanged.

## 1. Platform shape

NBA V1 adapts the proven platform pattern to one complete NBA `America/New_York` league-date slate:

- GitHub-authored immutable source/model assets;
- separate Research/Freeze and Market Workers;
- persistent Durable Object runs;
- server-enforced 1–2 game research batches;
- `market_data=false` through Layers 0–2;
- independently promoted Assists/Rebounds QBASE heads;
- typed server current-role transforms;
- atomic **whole-slate** freeze;
- exact count probability grids including integer pushes;
- per-head, per-player and whole-slate integrity hashes;
- post-freeze market access only;
- downstream-only shared Bet Tracker.

Production deployment ownership remains Cloudflare-native Git. GitHub Actions verifies/builds/promotes assets; it is not a competing Worker deployment owner.

## 2. Services

### Research / Freeze Worker
Name: `nba-player-props-research-v1`

Durable Object:
- binding `SLATE_RUNS`
- class `NbaSlateRun`

Responsibilities:
- sanitized fixture discovery;
- current roster/status source;
- runtime asset loading from exact deployed Git commit;
- persistent slate lock;
- research queue/checkpoints;
- server historical priors;
- server QBASE/current-role scoring;
- atomic freeze;
- invalidation state;
- market-access grant.

Actual routes:
- `GET /health`
- `GET /v1/fixtures?date=YYYY-MM-DD`
- `POST /v1/runs`
- `GET /v1/runs/{run_id}`
- `GET /v1/runs/{run_id}/research/next`
- `POST /v1/runs/{run_id}/research/checkpoint`
- `POST /v1/runs/{run_id}/freeze`
- `GET /v1/runs/{run_id}/freeze`
- `POST /v1/runs/{run_id}/invalidate`
- `GET /v1/runs/{run_id}/market-access`

### Market Worker
Name: `nba-player-props-market-v1`

Durable Object:
- binding `MARKET_RUNS`
- class `NbaMarketRun`

Service binding:
- `RESEARCH_SERVICE -> nba-player-props-research-v1`

Responsibilities:
- obtain fresh server market grant before each operation;
- resolve The Odds API events to exact frozen fixtures;
- ingest only approved Assists/Rebounds standard/alternate props;
- accept post-freeze sportsbook screenshots;
- bind market rows to exact frozen player/head/threshold;
- replace stale current snapshots;
- best-price merge;
- push-aware EV/global ranking.

Actual routes:
- `GET /health`
- `POST /v1/runs/{run_id}/refresh`
- `POST /v1/runs/{run_id}/manual-quotes`
- `GET /v1/runs/{run_id}/rankings`
- `GET /v1/runs/{run_id}/state`

## 3. League-date / fixture identity

`slate_date_et` is canonical and represents `America/New_York` league date, not UTC or Sydney calendar date.

Fixture discovery uses a sanitized non-market ESPN scoreboard fallback because the official NBA schedule endpoint has been HTTP-blocked in the source probes. Raw schedule payload fields that could include market material are not propagated into the research state.

Each eligible fixture lock contains:
- ESPN `game_id`;
- season;
- exact UTC start time;
- home ESPN team ID/name;
- away ESPN team ID/name.

Only not-yet-started returned games are eligible at run creation. Fixture metadata is persisted into the run and then into the immutable game freeze. A research checkpoint cannot change matchup/season/kickoff while retaining the same game ID.

## 4. Persistent run state

Current states:
- `RESEARCH_IN_PROGRESS`
- `RESEARCH_COMPLETE`
- `FROZEN`
- `FROZEN_BUT_INVALIDATED`

`FROZEN_BUT_INVALIDATED` does not alter the stored freeze object. It records affected game IDs/reasons and causes subsequent market grants to exclude those scopes.

A changed P_model always requires a new run.

## 5. Research queue

`GET /v1/runs/{run_id}/research/next` exposes only the first 1–2 pending game IDs and their research seeds.

`POST /v1/runs/{run_id}/research/checkpoint` accepts only 1–2 games from the current queue head. Completed IDs are persisted before later pending IDs can be exposed.

This makes long NBA slates resumable and prevents the GPT from researching/preloading the full remaining slate without server checkpoints.

## 6. Research contract

Every checkpoint is `nba_game_research_v1` and must declare `market_data=false`.

It binds:
- run mode / slate date / game / exact fixture;
- evidence rows with HTTPS URL, title, checked time, tier, evidence type;
- specialist metric status registry;
- exact player and team IDs;
- availability;
- current role state;
- projected minutes low/mean/high;
- expected starter probability;
- confidence/fragility inputs;
- requested-head causal pathways;
- current head-specific opportunity values.

Current opportunity accepted by the Worker is intentionally narrow.

Assists:
- expected assist share;
- expected team assists;
- expected possessions.

Rebounds:
- expected rebound share;
- expected team rebounds;
- expected possessions.

These are researched basketball-state inputs, not client-entered final player means.

The checkpoint validator rejects market keywords/fields, invalid identities, incomplete requested heads, unsupported opportunity fields and missing evidence bindings.

## 7. Historical authority / source acceptance

Historical backbone: **SportsDataverse/hoopR** pinned release assets with deterministic receipts.

Original normalized build:
- 139,809 player-games.

Independent final-box adjudication identified 14 inconsistent games. Source correction removes each entire game, producing:
- 139,529 accepted player-games;
- accepted history SHA `2e6926aa87ccebafbf938322f8facefeb54de63eb22f924dc2793afc61750b25`.

No individual stat patching or team-only removal is permitted.

Specialist metrics remain explicitly feature-gated as:
`AVAILABLE / PARTIAL / UNAVAILABLE / BLOCKED / NOT_RELIABLE`.

Base V1 uses `BASE_V1_WITHOUT_SPECIALIST_METRICS`; missing metrics are omitted, never represented as zero.

## 8. QBASE promotion

Assists and Rebounds are independent count-model challenges.

Temporal protocol:
- expanding 2024/2025 validation;
- 2026 untouched holdout;
- fixed head-specific count threshold grids;
- selection by validation Brier with early-season cohort non-regression versus the locked baseline;
- holdout pass/fail review only; never holdout family reselection.

Both corrected-history heads currently pass `PROMOTED_CORE_V1`:
- `NBA_ASSISTS_QBASE_V1.0.0`
- `NBA_REBOUNDS_QBASE_V1.0.0`

Runtime artifact promotion is fail-closed. CI quantizes exported production numeric parameters, forces single-thread numerical execution, reruns the challenges twice and requires byte-identical evidence before assets can be committed.

## 9. Runtime prior pack

The deterministic runtime prior pack contains accepted-history player and team state keyed by ESPN identities.

Player prior includes:
- last team / opponent / game / season;
- career and season game counts;
- rolling minutes/start rate;
- rolling Assists/Rebounds rates/shares and related head features.

Team prior includes:
- team possessions;
- team assists/rebounds;
- assists/rebounds allowed;
- season game counts.

At a new season, season/team game counts reset to zero while historical rolling role values remain prior evidence. Team changes are detected by ESPN team ID. Prior timestamps at or after target kickoff are rejected.

Research seed exposes compact player and team environment priors plus server historical QBASE prior means. Every value is explicitly labelled historical prior only.

## 10. Server-authoritative current-role translation

The client cannot submit a free-form final mean.

Implemented transform types:
- `QBASE_RUNTIME_SCORE`
- `MINUTES_RECOMPUTE`
- `ROLE_OPPORTUNITY_RECOMPUTE`
- `LINEUP_DEPENDENCY_RECOMPUTE`

All transform inputs are whitelisted and bounded. Head-inappropriate fields are rejected.

The server composes historical base features with evidence-bound current research, then scores the promoted QBASE artifact.

### Prior competition
The prior-competition framework requires a separately `PROMOTED` explicit competition route with minimum sample and uncertainty controls. There is no universal NCAA/G League/Euro/NBL fallback multiplier.

Without a promoted route, a rookie/new-to-NBA player may be researched for teammate context but is excluded from that player's P_model as `NO_PROMOTED_PRIOR_COMP_TRANSLATION`.

## 11. Exact distributions

Runtime QBASE produces count means and dispersion. Probability grid is Poisson when dispersion is effectively zero, otherwise NB2.

Each frozen head stores:
- final mean;
- dispersion alpha;
- exact count PMF;
- tail-above-grid probability;
- at-least ladder;
- half-point Over/Under grid;
- integer Over/Push/Under grid;
- quantitative receipts;
- `head_model_sha256`.

Each frozen player stores `player_model_sha256`.

The slate stores an `integrity_index` of game receipts, player hashes and requested head hashes before its own `freeze_receipt_sha256` is calculated.

## 12. Whole-slate freeze

`POST /v1/runs/{run_id}/freeze` accepts an empty body and is valid only at `RESEARCH_COMPLETE`.

The client never submits final projections to this endpoint. The Worker rebuilds player priors, applies current-state transforms and computes the complete requested-head slate server-side.

Freeze is one immutable publication:
- all eligible games represented;
- modeled players / objective exclusions;
- exact grids;
- exact fixture identities;
- original `frozen_at`;
- QBASE lineage;
- integrity index;
- whole-slate receipt.

No market-access grant can exist before this state.

## 13. Late-news invalidation

`POST /v1/runs/{run_id}/invalidate` accepts affected game IDs plus reason only after freeze.

The original freeze object, timestamp, player/head hashes and probabilities remain untouched. The run becomes `FROZEN_BUT_INVALIDATED` and new market grants exclude affected game IDs.

Price movement alone is not basketball-news invalidation evidence.

## 14. Market access boundary

The Market Worker obtains `nba_market_access_grant_v1` from Research before each state/read/refresh operation.

Grant binds:
- run ID;
- slate date;
- run mode;
- frozen timestamp;
- freeze receipt;
- allowed games;
- invalidated games.

Pre-freeze calls fail before any Odds API request.

## 15. The Odds API

Sport key: `basketball_nba`.

V1 market keys only:
- `player_assists`
- `player_assists_alternate`
- `player_rebounds`
- `player_rebounds_alternate`

Default region is `au`, one region only, to align the production Australian bookmaker stack and minimize credit multiplication.

Event discovery occurs first. Frozen fixture → Odds API event mapping requires exactly one match on normalized home team, normalized away team and kickoff within strict tolerance.

Player mapping is then restricted to the frozen game. Ambiguous or unmodeled names are skipped/reported, never guessed.

Only Overs are retained for V1 ranking.

## 16. Market snapshots / screenshots

Current ranking uses only:
- latest API snapshot;
- latest manual screenshot snapshot.

Previous snapshot receipts remain in history but stale prices do not compete in the current best-price merge.

Any market snapshot must have `captured_at >= frozen_at`.

Bet365/manual rows are post-freeze only and bind to:
- exact freeze receipt;
- allowed game;
- frozen player;
- frozen head;
- exact player/head hashes;
- exact integer/half threshold.

No interpolation.

## 17. EV / rankings

Half-point:
- no push.

Integer:
- exact `P_win / P_push / P_loss`.

EV:
`P_win * (decimal_odds - 1) - P_loss`

Fair decimal price:
`(1 - P_push) / P_win`

Tracker-compatible push-adjusted market probability:
`(1 - P_push) / decimal_odds`

Push-adjusted probability edge:
`P_win - push_adjusted_market_probability`

EV remains the positive-selection/ranking authority.

Outputs:
- BEST SINGLE or NO BET;
- Top 10 combined positive EV;
- Assists positives;
- Rebounds positives.

## 18. Bet Tracker

Existing production tracker is reused.

Identity:
- `sport=nba`
- `league=nba`
- `model_name=Nick NBA Assists + Rebounds`
- `model_version=1.0`

Create one tracker model run only after the first completed Layer 4. Price/screenshot refreshes do not create a new canonical model run.

Actual `recordBet` occurs only after explicit confirmation of exact selection, bookmaker, accepted odds and stake.

## 19. Runtime asset integrity

Cloudflare build runs `worker/build_source_commit.mjs`, replacing the checked-in `UNBUILT` placeholder with exact deployed Git HEAD.

Runtime loading chain:
`deployment Git commit -> manifest -> exact raw-file SHA-256 -> promoted QBASE/prior lineage`.

Python promotion receipt hashes are treated as opaque lineage identities across languages. JavaScript does not pretend Python float serialization hashes are portable; exact raw file SHA is the transport authority.

## 20. Production acceptance gates

V1 must not be called production-ready until all pass:

1. accepted corrected source history;
2. deterministic source rebuild;
3. independent Assists promotion;
4. independent Rebounds promotion;
5. repeated byte-identical challenge rebuild;
6. promoted runtime assets committed;
7. generated asset commit reproduces with zero diff;
8. all Python/JS CI green;
9. NBL isolation green;
10. Cloudflare Research Worker live with exact Git source pin + Durable Object;
11. Cloudflare Market Worker live with Durable Object + Research service binding + Odds API secret;
12. real future ET slate fixture resolution;
13. full server-enforced Layer 1 batch/checkpoint loop;
14. atomic whole-slate Layer 2 freeze;
15. proof no market access before freeze;
16. real Odds API retrieval and exact event/player binding;
17. Layer 4 global ranking;
18. Tracker model-run acceptance after Layer 4;
19. post-freeze Bet365 screenshot refresh preserving the same `run_id`, `frozen_at`, `freeze_receipt_sha256`, player/head hashes and probabilities;
20. no unresolved integrity/control failure.

Synthetic tests and green CI are necessary but do not replace the live acceptance sequence.
