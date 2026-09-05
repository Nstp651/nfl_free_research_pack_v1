# Nick NCAA Football Totals Model — V1 Architecture

Status: DESIGN / BUILD. This document defines the target production architecture. Calibration and live acceptance are separate gates.

## Purpose

Build a fully automated, full-slate NCAA Football FBS-v-FBS game totals model with the same market-blind freeze discipline and auditability as the NFL Receptions production model, but with an NCAA-specific quantitative research and scoring engine.

The model estimates true game-total probabilities first. The market determines value second.

## Scope

Supported initial market:
- full-game game totals (`totals`) only
- Over and Under both modelled mathematically
- AU bookmaker prices retrieved only after the entire slate P_model is frozen

Initial eligibility:
- FBS vs FBS only
- regular-season and postseason can be supported, but postseason is separately tagged
- exclude FBS-v-FCS from V1 betting selection
- no live/in-game totals
- no first-half/quarter totals
- no player props

## Core architecture

Layer 0 — Slate / fixture validation and eligibility
Layer 1 — Verified NCAA Full-Slate Research Pack
Layer 2 — Market-Blind Scoring / Total Probability Engine
`COMPLETE_MODEL_INTEGRITY_CONFIRMED`
`P_MODEL_STATUS: FROZEN`
Layer 3 — Australian totals market integration
Layer 4 — Full-slate single-play ranking

## Layer 0 — Slate validation

Inputs:
- season
- target NCAA week
- Australia/Sydney run date

Validate from schedule data:
- canonical game_id
- home/away
- kickoff UTC
- Australia/Sydney kickoff
- venue / neutral site
- season type
- FBS-v-FBS eligibility

The research service may expose all target-week FBS-v-FBS games. The model independently excludes already-started games and any fixture outside the intended run window.

## Layer 1 — research stack

### 1A. Structured quantitative pack — every game

For each team, retain current as-of and prior evidence separately.

Core current-season families where available:
- plays/game and offensive play volume
- drives/game / points per drive / drive efficiency
- EPA/play offense and defense
- pass/rush EPA
- success rate offense and defense
- pass/rush success rate
- explosive-play creation/prevention
- havoc / sack / pressure proxies where definitions are usable
- finishing-drive / red-zone proxies where available
- turnover rates, but treated carefully because turnover conversion is noisy
- pass/rush tendency
- special-teams efficiency where the source definition is stable
- opponent-adjusted offensive / defensive strength
- alternative ratings system for cross-checking
- games played / sample size

Early-season priors:
- previous-season efficiency, separated from current data
- team talent composite / blue-chip ratio when available
- returning production when available
- preseason rating context when available
- coach/QB/system changes are NOT inferred from last-season numbers; live research handles structural translation

### 1B. Matchup construction — every game

Translate team profiles into football pathways rather than add arbitrary bonuses:
- expected offensive play volume / possessions
- offense vs opposing defense efficiency interaction
- pass/rush style interaction
- explosiveness creation vs prevention
- havoc/protection interaction
- finishing-drive interaction
- neutral-site / home context
- rest / bye context

Do not call a raw difference a causal adjustment. Preserve component receipts and denominators.

### 1C. Current-information scan — every game

Current web research is required for information structured data cannot reliably know:
- starting QB identity / status
- significant backup-QB risk
- major offensive-line absences
- meaningful skill-player losses only when they change team efficiency/pace/scoring pathways
- major defensive personnel losses
- coordinator / play-caller / head-coach changes
- suspensions
- current depth-chart / transfer-role changes early season
- weather / roof / surface
- unusual travel/rest/context

No sportsbook lines, bookmaker previews, consensus totals or betting percentages may enter Layer 1.

### 1D. Deep-research trigger — targeted only

A matchup receives an intensified second pass when any applies:
- QB uncertainty
- new coach/coordinator/system
- low current-season sample
- current/prior statistical conflict
- large transfer/roster reset
- material OL/defensive injury cluster
- extreme weather
- extreme pace/style interaction
- model input missingness
- high sensitivity to one assumption
- cross-rating disagreement beyond a validated threshold

This is how the model scales to a large NCAA slate without pretending every game needs the same browsing depth.

## As-of / anti-leakage contract

For a target game in week W:

`current_season_data_through_week <= W - 1`

Never use results from the target week itself to model a target-week game. A regenerated pack is not automatically a historical point-in-time backtest unless its source snapshot is also as-of the simulated run date.

Week 1:
- current-season performance is unavailable, not zero
- use translated prior-season efficiency + preseason structural context + current personnel research

Weeks 2–4:
- current data receives meaningful but limited authority
- current role/QB/system truth can override stale prior structure
- rate estimates remain shrunken / uncertainty widened

Later season:
- current-season evidence progressively dominates when sample and structural continuity support it

No fixed week weights are hard-coded until validated walk-forward.

## Source quality and contradiction rules

- Missing metric != zero.
- Current structural truth outranks stale historical averages.
- A source timestamp is not proof every underlying metric is fresh.
- Two differently constructed rating systems are cross-checks, not duplicate votes.
- Opponent-adjusted fields must pass source-quality checks; a failed adjustment cannot be silently relabelled as adjusted.
- Betting-line fields in an upstream dataset are prohibited pre-freeze even if convenient.

## Layer 2 — total probability engine

Layer 2 uses ONLY the closed Layer 1 snapshot.

Preferred V1 modelling chain:

`EXPECTED POSSESSIONS / PLAYS`
→ `TEAM OFFENSIVE EFFICIENCY vs OPPOSING DEFENSE`
→ `TEAM SCORING MEAN / DISTRIBUTION`
→ `HOME + AWAY JOINT TOTAL DISTRIBUTION`
→ `P(total > line)` / `P(total < line)` for a precomputed threshold grid

The final production engine must be chosen by walk-forward validation, not by narrative preference.

Candidate families to compare:
1. predictive regression / gradient boosting on leak-free as-of team features with residual-distribution calibration
2. drive-level scoring model
3. hierarchical simulation using possessions × scoring efficiency
4. ensemble only if it improves temporal out-of-sample calibration and error

The upstream cfbfastR pregame work may be used as a benchmark, not automatically adopted as Nick's model.

### Threshold grid

Before any market access generate a broad full-game total grid sufficient to map common sportsbook lines exactly, e.g. half-points from 30.5 through 85.5 where the predictive distribution has practical support.

Exact grid/range is validated from market history and can be widened. No missing threshold may be inferred post-freeze.

### Required outputs per fixture

- expected home points
- expected away points
- expected total
- total variance / distribution method
- key scenario assumptions
- exact probabilities for each supported total threshold, both Over and Under as complements where the same continuous/discrete settlement convention applies
- Confidence
- Fragility
- source/revision hashes

### Numerical execution

Actual code execution is mandatory for every slate.

Record:
- parameter/input object
- model version
- distribution method
- random seed/draw count if simulated
- output object
- input/result SHA-256 hashes
- numerical audit results

Do not claim simulation, calibration or PASS without execution evidence.

## Pre-freeze integrity audits

At minimum:
- every fixture unique and canonical
- every current-season team input respects W-1 cutoff
- home/away IDs and profile IDs reconcile
- no market/betting field present in Layer 1/2
- no NaN/inf model parameter silently coerced to zero
- current/prior evidence kept distinguishable
- expected total in plausible support
- probability grid bounded [0,1]
- Over probability is monotonic decreasing as threshold rises
- Under probability is monotonic increasing as threshold rises
- Over/Under complement convention reconciles exactly for each non-push half-point
- scenario weights sum to 100% when scenarios exist
- sensitivity/fragility completed

Only then print:

`COMPLETE_MODEL_INTEGRITY_CONFIRMED`
`P_MODEL_STATUS: FROZEN`

Freeze the entire slate at one timestamp/research revision before any price access.

## Layer 3 — market integration

Post-freeze only.

Target production sequence:
1. list NCAA events through the existing betting gateway / Odds API adapter
2. resolve exact fixture by both teams + Australia/Sydney date + commence time
3. retrieve full-game `totals` for AU books
4. verify fixture and market family
5. map exact total threshold to exact frozen P_model
6. select best current price deterministically

For each side:
- P_break_even = 1 / decimal_odds
- Fair Price = 1 / P_model
- Price Edge = P_model - P_break_even
- Expected ROI = P_model * decimal_odds - 1

No P_model value may change after market access.

## Layer 4 — ranking

Rank every positive-edge eligible full-game total on the weekly slate.

Primary ordering:
1. expected ROI
2. price edge
3. frozen fragility / sensitivity
4. research/data quality
5. price freshness
6. Confidence as tie-breaker

Do not force a bet.

Output target:
- BEST SINGLE
- Top 10 positive-edge NCAA totals
- other meaningful positives
- passed/tight core games
- coverage / freshness warnings

The model can mathematically rank Unders even if the user's execution preference later favors Overs. User preference must not alter the pre-market probability model.

## Full-slate scale design

The critical design difference from NFL Receptions is grain:

NFL: one fixture + paginated players.
NCAA: one weekly slate + paginated games.

The research Worker returns a compact game record with both team profiles and receipts. GPT consumes all pages at ONE slate revision. Team profiles may repeat across neither side of a game; one game contains exactly two canonical team states.

The live-research layer is a funnel:
- every game: structured pack
- every game: lightweight current-info scan
- triggered games: deep research

This prevents a 50+ game Saturday from becoming 50 independent long-form research jobs.

## Infrastructure target

GitHub:
- source-controlled builder / schema / tests
- scheduled pack refresh
- generated current data
- Worker source
- Cloudflare dry-run/deploy workflow

Cloudflare Worker:
- read-only research API
- no odds data
- immutable revision checks
- freshness / source health
- Action-safe pagination

Cloudflare storage is not required for V1 if GitHub-generated JSON remains comfortably within source and request limits. Add KV/R2/D1 only when an observed scaling need justifies it; do not add infrastructure complexity by default.

## Production validation / governance

Before betting use:
- backtest totals prediction walk-forward by season/week
- MAE/RMSE of expected total
- log loss/Brier by threshold
- calibration by probability bucket
- calibration by total range
- performance early vs late season
- ablation: prior carryover, talent, returning production, pace, opponent-adjustment, weather, QB change, rest
- compare against a simple benchmark and cfbfastR's published pregame baseline
- never train/tune on sportsbook current prices

Betting performance (ROI/CLV) is evaluated only after the predictive model is frozen and historically joined to as-of market snapshots.
