# TENNIS V1 — Production Architecture

## 1. Objective

Price the full singles match from two matchup-specific serve-point probabilities, before sportsbook access, then derive coherent probabilities for match winner, total games and game handicap from the same frozen distribution.

The engine is deliberately **not** three separate market models.

## 2. Four-layer operating model

### Layer 1 — Market-blind quantitative + current research pack

Build a timestamped match pack with only non-market evidence available before the run cutoff.

Structured inputs:
- match history and score;
- ranking/rating history;
- surface and indoor/outdoor designation;
- first-serve in rate;
- first-serve points won;
- second-serve points won;
- return points won;
- aces and double faults;
- break points created/saved/converted where available;
- service games and hold rate;
- return games and break rate;
- match duration;
- opponent strength;
- tournament/round;
- rest days and recent court time;
- qualifying/main-draw workload;
- point-by-point states where licensed.

Current research inputs:
- injury/fitness reporting;
- recent retirement or medical timeout context;
- return from injury;
- qualifying load;
- consecutive long matches;
- travel/time-zone change;
- altitude;
- indoor/outdoor;
- temperature, humidity and wind for outdoor matches;
- surface transition;
- unusual schedule changes.

Every qualitative adjustment requires a timestamped evidence note and must be encoded before freeze.

### Layer 2 — Point model + match distribution

Estimate:

`pA = P(A wins a point on A serve)`

`pB = P(B wins a point on B serve)`

Then build the complete match distribution.

### Layer 3 — Post-freeze market integration

Only after immutable freeze:
- query The Odds API;
- `regions=au`;
- request `h2h,totals,spreads` when available;
- retain bookmaker, line, price and timestamp;
- apply market-depth gates;
- select the best valid price for each identical outcome.

### Layer 4 — Slate ranking + tracking

Rank all eligible outcomes across the complete tournament slate by model EV, subject to integrity, coverage and uncertainty gates. Do not force one bet per match or one market type.

---

## 3. Serve/return model

ATP and WTA are separate model families. Surface baselines are separate, and best-of-5 validation is isolated rather than pooled with best-of-3.

### 3.1 Observation model

For each historical service point or reconstructed service-point aggregate:

`logit(P(server wins point)) = μ[tour,surface] + S[server,t,surface] - R[returner,t,surface] + βX + δ[event]`

Where:
- `μ` = tour/surface server-point baseline;
- `S` = player serve-strength effect;
- `R` = opponent return-strength effect, positive when the returner suppresses serve success;
- `X` = pre-match context features;
- `δ[event]` = current tournament-condition residual.

### 3.2 Player state

Player serve and return effects are estimated independently with hierarchical shrinkage. Recency weighting is applied by age of observation, not by arbitrary last-N matches alone.

Recommended decay grid for validation:
- fast: 30–45 day half-life;
- core: 90–120 day half-life;
- slow prior: 250–365 day half-life.

The final state is a learned blend chosen only from chronological validation.

Surface hierarchy:
1. exact surface prior;
2. indoor/outdoor hard split where data supports it;
3. all-surface player prior;
4. tour baseline.

Players with sparse exact-surface samples receive stronger shrinkage toward broader priors.

### 3.3 Opponent quality

Do not use raw hold/break percentages without opponent adjustment.

Preferred fit: penalized/hierarchical logistic model with server and returner random effects. If only match-level aggregates are available, fit weighted binomial rows using service points won / service points played.

### 3.4 Component features

Use first-serve %, first-serve points won, second-serve points won, ace rate and double-fault rate primarily as explanatory/stability features around total service-point performance. Avoid double-counting them as independent additive evidence when they mathematically compose the same service points.

Useful derived diagnostics:
- first-serve effectiveness = first-in × first-serve-win%;
- second-serve resilience = second-serve points won% adjusted for opponent return quality;
- ace rate per service point;
- double-fault rate per service point;
- break-point performance regression to normal rate;
- pressure residual only if it remains stable out of sample.

### 3.5 Workload and fitness

Pre-freeze workload features:
- minutes in last 24/48/72 hours;
- sets and games in last 48/72 hours;
- qualifying matches in previous 7 days;
- consecutive three-set/five-set matches;
- travel days and surface switch;
- retirement/medical flag.

Fitness adjustments are bounded and uncertainty must increase when evidence is ambiguous. An unresolved acute injury/retirement flag can make a match ineligible rather than create a heroic model adjustment.

---

## 4. Tournament Pace Index (TPI)

TPI is a market-blind empirical-Bayes event condition effect, calculated only from matches completed before the target match cutoff.

### 4.1 Raw event signals

Compare current-event observations with player/opponent/surface expectations for:
- service points won;
- hold rate;
- ace rate;
- break rate;
- first-serve points won;
- second-serve points won;
- rally length / return-depth signals where licensed.

Do not use raw event averages alone because early-round fields contain different player mixes.

### 4.2 Residual construction

For each completed match, calculate expected serve performance from the pre-event player model, then aggregate residuals:

`event_residual = observed_server_point_win - expected_server_point_win`

Convert the weighted residual to logit space and shrink to zero:

`δ_event = reliability(n_points) × raw_event_logit_residual`

A simple starting reliability function is:

`reliability = n_service_points / (n_service_points + K)`

with `K` tuned separately for ATP/WTA and surface in chronological validation.

Auxiliary ace/hold/break residuals may enter a learned TPI regression, but service-point residual remains the anchor.

### 4.3 Leak prevention

For a target match at time T:
- include only event observations timestamped before T;
- never use target-match data;
- never use later-round data;
- never use sportsbook totals/spreads as a proxy for conditions.

---

## 5. Match simulation mathematics

### 5.1 Game conversion

For iid service-point probability `p`, exact standard-game hold probability is:

`H(p) = p^4(1 + 4q + 10q^2) + 20p^3q^3 × p^2/(p^2+q^2)`, where `q=1-p`.

The implementation uses this exact hold probability for regular service games.

### 5.2 Tiebreaks

Tiebreaks are simulated point-by-point with the correct 1-2-2 serving sequence, using each player's own serve-point probability.

The rules registry must specify:
- regular-set tiebreak trigger;
- regular tiebreak target;
- final-set tiebreak trigger;
- final-set tiebreak target;
- best-of-3 or best-of-5.

Never infer rules from market lines.

### 5.3 Parameter uncertainty

Each simulation draws latent serve probabilities on the logit scale:

`logit(pA*) ~ Normal(logit(pA), σA)`

`logit(pB*) ~ Normal(logit(pB), σB)`

This produces fatter and more realistic tails than pretending estimated player strength is known exactly.

### 5.4 Output distribution

For each simulation retain:
- match winner;
- total games;
- A-minus-B game margin;
- set score.

Production default: at least 250,000 simulations per match, raised if probability Monte Carlo error exceeds the validated tolerance.

### 5.5 Derived market probabilities

H2H:
- `P(A wins)` directly from the simulated match winner distribution.

Total line L:
- over = `P(total_games > L)`;
- push = `P(total_games = L)`;
- under = `P(total_games < L)`.

Game handicap h from A perspective:
- win = `P(game_margin_A + h > 0)`;
- push = equality;
- loss = `< 0`.

Push-aware decimal break-even price:

`fair = 1 + P(loss)/P(win)`.

Expected net return per unit stake:

`EV = P(win) × (odds - 1) - P(loss)`.

---

## 6. Match rules and retirement handling

Maintain a versioned tournament rules registry. Grand Slam and tour rules change over time, so historical backtests must use the rules in force on the match date.

V1 prices completed-match tennis, not retirement mechanics. Matches with unresolved material fitness/retirement risk can be excluded. Tracker settlement records `win/loss/push/void`, because bookmaker retirement rules can differ by market and book. Voids must not be counted as wins/losses in model calibration.

---

## 7. The Odds API integration

### 7.1 Discovery

At slate start:
1. call `/v4/sports?all=true` and retain tennis sport keys;
2. select active singles competitions supported by the model/data feed;
3. call `/events` to resolve exact event IDs and commence times;
4. **do not call odds yet**.

After all match P-models are frozen:
5. call `/odds` or event odds with `regions=au`, `markets=h2h,totals,spreads`, decimal format;
6. verify sport key, event ID, competitors and time against the run lock;
7. persist raw market response hash and retrieval timestamp.

### 7.2 Market-depth gate

Default V1 gate:
- H2H: at least 3 distinct AU books;
- totals: at least 2;
- spreads: at least 2.

These thresholds are policy parameters and must be validated. If only H2H clears the gate, only H2H is eligible. No market is mandatory.

### 7.3 Quote normalization

For identical market/selection/line combinations:
- keep all raw quotes for audit;
- use highest current valid decimal price for decisioning;
- reject stale or malformed quotes;
- never synthesize a missing line or price.

### 7.4 Historical validation prices

Historical odds, when used for ROI/CLV testing, must also come only from The Odds API and must be joined **after** each historical P-model snapshot has been generated and frozen.

---

## 8. Immutable freeze contract

A run lock contains:
- run ID;
- tournament/sport key;
- event ID placeholder before market access;
- players and canonical IDs;
- scheduled start;
- tour/surface/rules version;
- data cutoff timestamp;
- quantitative pack hashes;
- research evidence references;
- `pA`, `pB`, uncertainty;
- simulation seed/count/version;
- full winner/total/margin distribution;
- model version and source commit.

Freeze writes canonical JSON plus SHA-256 receipt and sets:

`P_MODEL_STATUS: FROZEN`

The artifact is append-only. If material research changes after freeze, create a new run ID; never mutate the frozen artifact after sportsbook access.

---

## 9. Full-slate runner

For each active eligible ATP/WTA singles competition:
1. build event/tournament context;
2. resolve all scheduled matches;
3. build market-blind match packs;
4. fail closed on unresolved player identity, rules or critical data freshness;
5. estimate serve-point probabilities;
6. simulate each match;
7. freeze all matches independently;
8. after slate freeze, request The Odds API prices;
9. coverage-gate each market;
10. price every valid outcome from the same frozen distribution;
11. rank all positive-EV rows across the slate;
12. apply uncertainty and minimum-edge policy;
13. write selected bets to tracker only when actually placed/confirmed.

No-bet is a valid slate result.

---

## 10. Current research methodology

Research occurs before P-model freeze and remains market blind.

Evidence priority:
1. tournament/official player announcements and schedules;
2. reputable sports/news reporting with direct quotes;
3. verified local weather/venue conditions;
4. player press conferences/social posts where authenticity is clear;
5. secondary commentary only as corroboration.

Research packet fields:
- `injury_status`;
- `retirement_last_30d`;
- `medical_timeout_recent`;
- `return_from_injury_days`;
- `qualifying_matches_7d`;
- `minutes_24h/48h/72h`;
- `travel_transition`;
- `surface_transition`;
- `altitude_m`;
- `indoor_outdoor`;
- `forecast_temp/humidity/wind`;
- `schedule_irregularity`;
- `evidence_confidence`.

Head-to-head is not a primary feature. It is only promoted when there is a measurable mechanism not already captured by serve/return, handedness/style, surface and conditions, and that mechanism survives out-of-sample testing.

---

## 11. Chronological validation

No random train/test split.

Use rolling-origin testing:
- train through date T;
- predict the next chronological block;
- advance T;
- never let future tournament matches update TPI for earlier matches.

Separate reports for:
- ATP / WTA;
- hard / clay / grass / indoor hard where supported;
- best-of-3 / best-of-5;
- model favourite / model underdog;
- H2H;
- totals;
- handicaps;
- tournament stage.

### Probability metrics

H2H:
- log loss;
- Brier score;
- calibration intercept/slope;
- ECE/reliability bins.

Total-games and margin distributions:
- CRPS or ranked probability score;
- PIT / empirical CDF diagnostics;
- interval coverage;
- tail calibration at commonly offered lines.

### Betting metrics

Calculated only after post-prediction Odds API joins:
- closing-line value by market;
- ROI by market;
- turnover;
- average price;
- average model edge;
- max drawdown;
- result by tour/surface/stage;
- void/retirement rate.

CLV and realised ROI are separate scorecards. Never tune P-model features to short-window realised ROI alone.

---

## 12. Tracker schema

Each confirmed bet records:
- run ID + frozen SHA;
- event/tournament/player IDs;
- market/selection/line;
- bookmaker and odds;
- stake;
- frozen win/push/loss probabilities;
- fair price and EV at bet;
- placed timestamp;
- closing price from The Odds API when later available;
- result, void reason and P&L.

The tracker may never alter the frozen P-model.

---

## 13. Acceptance gates

Tennis V1 may not be called production-ready until all gates pass.

### Data/legal
- licensed production data source contracted/approved;
- source lineage present on every normalized row;
- no prohibited public/scraped dataset in production artifacts;
- ATP and WTA identity resolution collision tests pass.

### Simulator
- game hold formula unit tests pass against known values;
- deterministic seed reproducibility passes;
- best-of-3 and best-of-5 score bounds pass;
- tiebreak serve-order tests pass;
- final-set rule variants pass;
- probability mass sums to 1 within tolerance;
- push handling for integer totals/spreads passes.

### Model
- chronological backtest only;
- ATP/WTA separately calibrated;
- surface calibration reported;
- best-of-5 separately validated;
- player uncertainty increases for sparse/return-from-injury states;
- TPI shows out-of-sample incremental value or is disabled.

### Freeze/integrity
- odds endpoint impossible to call before freeze in production orchestration;
- freeze artifact is content-hashed and immutable;
- post-freeze research change creates a new run rather than mutation;
- event/competitor mismatch fails closed.

### Market
- The Odds API is sole price source;
- AU bookmaker region requested;
- market-depth gate enforced;
- no fabricated odds/lines;
- best-price selection auditable from raw response.

### Validation
- minimum sample thresholds set before review;
- calibration slope/intercept within approved bands;
- H2H and distributional scoring beat simple tour/surface baseline out of sample;
- no material degradation in any major ATP/WTA/surface segment without documented exclusion;
- CLV positive over a predeclared evaluation window before stake escalation;
- realised ROI reported but not used as sole promotion criterion.

### Live shadow
- minimum four weeks or agreed event-count shadow operation;
- zero pre-freeze market leakage incidents;
- zero frozen-artifact mutation incidents;
- deterministic replay of every run from stored inputs;
- tracker reconciles odds, result and P&L.

---

## 14. V1 promotion sequence

Milestone 1: architecture, simulator, freeze and market contracts.

Milestone 2: licensed data adapter + normalized historical pack.

Milestone 3: ATP/WTA serve-return model training + TPI research.

Milestone 4: chronological backtest and calibration report.

Milestone 5: The Odds API post-freeze integration + historical CLV/ROI harness.

Milestone 6: full-slate shadow runner + tracker.

Milestone 7: production acceptance only after every gate above passes.
