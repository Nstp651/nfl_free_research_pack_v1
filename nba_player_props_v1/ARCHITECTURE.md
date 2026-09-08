# NBA Assists + Rebounds V1 Architecture

Status: BUILDING. This is an isolated NBA implementation; NBL production is unchanged.

## 1. Architectural baseline

The platform baseline is `nbl_player_props_v1/`: GitHub-authored immutable assets, separate Research/Freeze and Market Workers, persistent Durable Object runs, exact source pinning, server-authoritative QBASE, research receipts, atomic freeze, per-player hashes, exact probability grids, market-to-freeze binding, and downstream-only Bet Tracker.

NBA changes the unit of work from **one matchup** to **one complete NBA league-date slate**.

A second proven platform pattern is reused from `ncaaf_totals_v1/`: the Research Worker exposes only the current small pending batch, requires its checkpoint before advancing the queue, and publishes frozen outputs atomically only after every eligible game is complete.

## 2. NBL → NBA transfer matrix

| Area | Decision | NBA V1 implementation |
|---|---|---|
| GitHub source/model authority | KEEP | NBA assets live only under `nba_player_props_v1/`; exact source commit pinned per run. |
| Cloudflare native Git deployment | KEEP | GitHub Actions verify/dry-run; Cloudflare Git integration is sole production deployment owner. |
| Combined GPT, independent assists/rebounds heads | KEEP | Default BOTH; each head has separate QBASE, calibration, distribution and player/head hash. |
| Separate Research/Freeze and Market Workers | KEEP | No Odds API credentials or market fetch paths exist in Research Worker. |
| Persistent Durable Object run | ADAPT | One `NbaSlateRun` owns an entire NBA league-date slate. |
| One research payload per matchup | REPLACE | Server queue returns at most 2 games; each checkpoint is persisted separately. |
| Atomic BOTH freeze | ADAPT | Atomic **requested-head, whole-slate** publication. No game/player grid is market-readable before global freeze. |
| Historical prior snapshot | ADAPT | NBA multi-season prior plus richer lagged role/opportunity features and identity crosswalks. |
| NBL Rosetta/nblR source spine | REPLACE | SportsDataverse release backbone + official NBA enrichment with deterministic receipts. |
| QBASE feature set | REPLACE | NBA-specific, leak-safe feature challenge; richer tracking/lineup inputs only when validated. |
| Temporal walk-forward validation | KEEP+ADD | Season/date-forward only; explicit early-season buckets and team-change/role-change slices. |
| NB2 exact distribution contract | KEEP AS CANDIDATE | Distribution family is re-challenged using OOS probability calibration; exact count and push contract remains. |
| GPT-supplied scenario means | REPLACE | No free-form mean override for returning NBA players. Current-role translation must use typed server-audited transforms. |
| Prior-competition translation | ADAPT | Explicit NCAA/G League/international/Summer League/preseason evidence with uncertainty; no universal multiplier. |
| Research contract | ADAPT | Game-scoped checkpoints, evidence tier/recency/materiality, descriptive-vs-causal tags, objective fragility components. |
| Per-player model hashes | KEEP+ADD | Hash each full player plus each requested head; slate receipt commits to ordered game/player/head hashes. |
| Material late-news handling | ADD | Explicit immutable invalidation/supersession protocol; no frozen probability mutation. |
| Odds API market layer | ADAPT | NBA event-level prop pulls, request-credit budgeting, event↔fixture binding, exact market merge, global slate ranking. |
| Screenshot support | KEEP | Post-freeze Bet365/manual screenshots only; exact thresholds; best valid current price wins. |
| Bet Tracker separation | KEEP | Recommendations are never wagers; log only explicit confirmed bets. |

## 3. Daily-slate identity and lock

### 3.1 Canonical date

A run is keyed by `slate_date_et` (`America/New_York`, YYYY-MM-DD), because the NBA schedule is grouped by league date and games can cross UTC/Sydney dates. The API also returns all exact UTC start times and a Sydney display date/time.

The Worker never derives membership by UTC calendar date alone.

### 3.2 Run initialization

`POST /v1/slate-runs`

Input:

- `slate_date_et`
- `run_mode`: BOTH | ASSISTS_ONLY | REBOUNDS_ONLY

Server locks:

- exact eligible `game_ids` and ordered fixture identities;
- source commit;
- asset revision;
- prior snapshot revision;
- assists and/or rebounds QBASE revisions;
- source receipt hashes;
- eligibility timestamp;
- schedule snapshot hash;
- requested heads.

Eligibility requires an exact future NBA fixture. Started/completed games are excluded at initialization and cannot later be added to the run.

## 4. Research queue and checkpoints

### 4.1 States

`RESEARCH_IN_PROGRESS` → `RESEARCH_COMPLETE` → `FREEZE_COMPUTING` → `FROZEN`

Terminal/safety states:

- `EXPIRED`
- `INVALIDATED`

A frozen run is immutable.

### 4.2 Queue discipline

`GET /v1/slate-runs/{run_id}/research` returns **only the first 1–2 pending game_ids** and their locked seed/QBASE anchors. It does not accept pagination or arbitrary game selection.

`POST /v1/slate-runs/{run_id}/research` accepts only complete checkpoints for games in the current queue head. The transaction persists each checkpoint under `research:{game_id}` with its SHA-256 receipt.

Only after persistence do those game IDs move to `completed_game_ids`; the next GET may then reveal the next pending batch.

This prevents preloading/researching later games without checkpointing earlier work, keeps each Durable Object value small, and makes long daily slates resumable.

### 4.3 Research checkpoint contract

Each game checkpoint binds:

- run_id / slate_date_et / game_id / fixture hash;
- source_commit / pack_revision / QBASE revisions;
- checkpointed_at;
- evidence list: URL, title, checked_at, source tier, evidence type, published_at when available;
- current team availability state;
- expected starters/rotation;
- relevant player records;
- minutes low/mean/high;
- current role vs historical role;
- closing likelihood;
- creator/frontcourt hierarchy;
- teammate competition / lineup dependencies;
- role breakpoints;
- stat-specific causal pathways;
- validated specialist-metric availability statuses;
- Confidence inputs and Fragility inputs;
- explicit market boundary assertion (`market_data=false`).

Market keywords/keys and sportsbook-derived projections are rejected during Layers 0–2.

## 5. Server-authoritative quantitative model

### 5.1 Historical QBASE

Each head is trained independently. All player/team/opponent rolling values are pregame-only and use `shift(1)` or an equivalent strict timestamp cutoff.

Candidate selection hierarchy:

1. probability calibration at bettable thresholds (Brier/log loss/calibration slope/intercept/reliability);
2. tail calibration and ladder monotonicity/coherence;
3. bias and count deviance;
4. MAE/RMSE as secondary diagnostics.

Validation is temporal only. It includes explicit slices for:

- season games 0–2;
- 3–7;
- 8+;
- team changers;
- starter/bench role changes;
- low-history players;
- back-to-backs/rest;
- high/low projected-minutes bands.

### 5.2 Current-role translation

GPT narrative cannot submit a free-form final mean for a returning NBA player.

Allowed server transformations are typed and receiptized, for example:

- `QBASE_REFERENCE`
- `MINUTES_RECOMPUTE`
- `ROLE_OPPORTUNITY_RECOMPUTE`
- `LINEUP_DEPENDENCY_RECOMPUTE`
- `PRIOR_COMP_TRANSLATION`

Each transform has fixed required numeric inputs, bounded domains, evidence IDs and a deterministic server implementation. One REFERENCE state at weight 1.0 is default. Multiple states are allowed only when the research checkpoint records objective routine mixture evidence and the server validates weights and state definitions.

### 5.3 Assists causal engine

Historical/current opportunity chain:

`minutes → on-ball creation opportunity → potential-assist/pass/touch environment → teammate finishing environment → assists count distribution`

Validated tracking features can include lagged touches, passes, secondary assists, potential assists, drives, time of possession, AST%, usage, lineup creation share and teammate finishing. Unvalidated fields are omitted, never zero-imputed as if observed.

### 5.4 Rebounds causal engine

Historical/current opportunity chain:

`minutes + position → opponent/team missed-shot environment → rebound chances → teammate competition/capture rate → rebounds count distribution`

Validated features can include lagged offensive/defensive/total rebound chances, ORB%/DRB%/TRB%, lineup rebound share, teammate competition, shot-location/miss environment and pace.

### 5.5 Exact probability contract

Every frozen head provides a coherent exact non-negative integer count distribution and exact grids for every supported threshold.

- half-point line: over/under, no push;
- integer line: over/push/under with exact-count push;
- no interpolation;
- monotonic ladder audit;
- total probability audit;
- OOS-calibrated dispersion cannot be silently narrowed by research narrative.

## 6. Whole-slate freeze

`POST /v1/slate-runs/{run_id}/compute`

Preconditions:

- no pending games;
- all requested game checkpoints pass binding checks;
- all requested player/head transforms pass modelability and evidence checks;
- no market access token exists for this run;
- run not expired/invalidated.

The server computes all modelable requested heads and stages them. Publication is one Durable Object transaction:

- write all frozen player records;
- write all player/head hashes;
- write compact slate receipt;
- transition `RESEARCH_COMPLETE` → `FROZEN`.

No player probability grid is retrievable until the transaction completes.

The receipt includes:

- `freeze_receipt_sha256`;
- `frozen_at`;
- source/QBASE/snapshot revisions;
- ordered eligible game IDs;
- ordered frozen player/head hashes;
- exclusions with objective reasons;
- global integrity audit.

Freeze retry returns the original immutable receipt and timestamp.

## 7. Late-news invalidation

Frozen probabilities are never mutated.

Material news is anything that changes a model input beyond a configured tolerance, including OUT/IN status, starter change, meaningful minutes restriction, role-changing teammate status, or material lineup dependency.

Protocol:

1. append an immutable invalidation event with source/evidence hash;
2. mark affected `game_id`, player IDs and affected heads invalid;
3. Market Worker rejects those scopes immediately;
4. unaffected frozen scopes may remain eligible only if the slate receipt exposes the invalidation registry and Market Worker confirms the exact scope is unaffected;
5. if a fresh P_model is needed, create a **new slate run** and repeat full market-blind Layers 0–2 before its first market access. Never recompute a market-exposed run.

## 8. Data source architecture

### 8.1 Production backbone

SportsDataverse release assets are the preferred historical base because they are GitHub-hosted, automation-friendly, multi-season, and explicitly licensed. Pin release asset URLs/checksums in a source receipt and normalize into canonical NBA player-game/team-game tables.

### 8.2 Official enrichment

NBA official sources are enrichment, not unchecked hard dependencies. Each enrichment endpoint must pass:

- HTTP reliability gate;
- schema fingerprint gate;
- game/player identity gate;
- non-null/completeness gate;
- date coverage gate;
- duplicate gate;
- cross-source reconciliation gate.

Tracking fields that pass are material NBA advantages. Fields that fail are classified `PARTIAL`, `BLOCKED`, `NOT_RELIABLE`, or `UNAVAILABLE` and are not model features.

### 8.3 Current schedule/identity

Use official NBA CDN schedule/scoreboard where reliable, with SportsDataverse/ESPN schedule as independent reconciliation. Lock exact NBA/ESPN IDs and UTC timestamps; reject unresolved identity ambiguity.

### 8.4 Current information hierarchy

Tier 0 — official NBA injury reports / official transaction records / official team status releases.

Tier 1 — official team coach/practice/shootaround reports and confirmed starting information.

Tier 2 — established beat reporters with direct team access.

Tier 3 — reputable national reporting useful for context.

Excluded from Layers 0–2 — betting-tip sites, sportsbook prices, market consensus, prop projections derived from markets.

## 9. Market Worker

Market Worker owns no modelling code and cannot mutate Research Worker storage.

It requires:

- run status `FROZEN`;
- exact `freeze_receipt_sha256`;
- no invalidation covering the market scope;
- exact slate game identity;
- market observation `captured_at >= frozen_at`;
- exact frozen player/head hash;
- exact threshold in frozen probability grid.

### Odds API

The Odds API NBA sport key is `basketball_nba`. Player props use event-level additional markets. V1 requests only the requested market keys for the games in the frozen slate and logs response usage headers. Empty data are not retried aggressively.

Market keys:

- `player_assists`
- `player_assists_alternate`
- `player_rebounds`
- `player_rebounds_alternate`

Requests are grouped to minimize the number of unique returned markets × regions. The default production region is the minimum set needed to cover the user's active books; additional regions are opt-in because they multiply credits.

Manual screenshot rows remain supported post-freeze. Duplicate exact market keys (`game|player|head|side|threshold`) are merged by highest valid current decimal price with deterministic timestamp/bookmaker tie-breaks.

Final outputs: BEST SINGLE across both heads, separate ranked assists/rebounds lists, combined positive-edge Top 10, all positives on request, and NO BET when none pass.

## 10. Modelability

A player/head is frozen only if one route succeeds:

**Returning NBA:** sufficient timestamped NBA history for QBASE plus current-role translation inputs within supported ranges.

**Changed role/team:** NBA QBASE remains authority; current opportunity is translated through typed transforms.

**Rookie/new-to-NBA:** explicit prior-competition translation artifact with source competition, sample/minutes, role, pace/context fields, uncertainty and translation receipt. No universal league multiplier.

Objective exclusion reasons include unresolved identity, unavailable/contradictory status, minutes uncertainty above configured maximum, insufficient prior translation, unsupported role break, or failed source-quality gates.

## 11. Day-one improvements over NBL

1. Slate-global freeze and batch research checkpoints instead of one-match runs.
2. Explicit invalidation registry enforced by the Market Worker.
3. Head-level hashes in addition to full-player hashes.
4. Typed server role transforms; no arbitrary externally supplied returning-player mean.
5. Server-derived Fragility components rather than purely narrative labels.
6. Source-quality/recency/materiality fields and contradiction ledger in research checkpoints.
7. Specialist metric availability registry so missing advanced data cannot become silent zeros.
8. Broader QBASE model-family challenge and probability-calibration-first selection.
9. Early-season promotion gates stricter than full-season aggregate gates.
10. Odds API credit budget/usage receipt attached to each market snapshot.
11. Explicit league-date/timezone contract and cross-source game identity crosswalk.

## 12. Production acceptance gates

Production status is prohibited until all pass:

- deterministic source rebuild from pinned receipts;
- source/release/normalized-table hashes;
- identity and duplicate audits;
- timestamp coverage audit;
- leak-safe feature tests and `shift(1)`/cutoff assertions;
- temporal walk-forward backtest and early-season slices;
- reproducible QBASE artifacts;
- server-authoritative returning-player scoring;
- prior-competition translation tests;
- research market-boundary rejection;
- server-enforced 1–2 game queue and resumable checkpoint recovery;
- wrong-game/out-of-order checkpoint rejection;
- atomic whole-slate requested-head freeze;
- immutable retry and original timestamp;
- exact probability-grid audits including integer pushes;
- per-player + per-head hash verification;
- pre-freeze Market Worker rejection;
- wrong receipt/hash/game rejection;
- invalidated-scope rejection;
- post-freeze Odds API/screenshot evaluation;
- exact threshold/no-interpolation tests;
- best-price deterministic merge;
- positive-edge global ranking + NO BET;
- tracker health and no recommendation-as-wager tests;
- Cloudflare live Research/Freeze + Market acceptance;
- final Custom GPT Action acceptance.