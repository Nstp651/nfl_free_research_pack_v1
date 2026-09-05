# NCAA FOOTBALL TOTALS — 4-LAYER MASTER API/ACTION PRODUCTION V1.0

## 0. AUTHORITY / OBJECTIVE

This is Nick's production NCAA Football full-game totals methodology. It is built for ONE automated run covering the target FBS-v-FBS slate. The objective is to estimate the true full-game total distribution before seeing any sportsbook market, freeze the entire slate P_model, then compare exact frozen probabilities with current Australian bookmaker totals.

The market may determine value. It may never determine the pre-market probability model.

External research is evidence, not a substitute for the methodology. Research/Action source failure is never permission to invent data.

---

## 1. SCOPE

### Included
- NCAA Football / FBS.
- FBS vs FBS only for V1 betting selection.
- Full-game `totals` only.
- Over and Under are both modelled mathematically.
- Standard half-point total grid supported pre-freeze from 30.5 through 85.5; widen PRE-FREEZE if the slate requires broader support.
- One run covers all eligible games in the target week/run window.

### Excluded
- FBS-v-FCS selection in V1.
- H2H, spreads, team totals, halves, quarters, live/in-play, player props, multis/SGMs.
- Any sportsbook line/price, betting consensus, tip site, market-implied rating or closing-line information in Layers 0-2.
- Staking is outside the model recommendation calculation.

User preference for Overs must never alter P_model. If the model prefers an Under, calculate it honestly.

---

## 2. HARD MARKET-BLIND BOUNDARY

Before `P_MODEL_STATUS: FROZEN`, prohibited inputs include:
- sportsbook totals/spreads/moneylines/prices;
- betting percentages/consensus;
- market-implied team ratings;
- tipster or betting-preview recommendations;
- The Odds API market endpoint.

Allowed before freeze:
- NCAA research Worker health/slate/QBASE endpoints because they validate `market_data:false`;
- official/team/media football reporting;
- weather and venue information;
- football statistics and market-blind historical model artifacts.

If any prohibited market information is accidentally exposed before freeze, the run is contaminated: discard the affected Layer 1/2 work and restart from a clean information state.

---

# LAYER 0 — SLATE / DATA PREFLIGHT

## 3. Validate target slate independently

Resolve:
- season and NCAA week;
- every intended FBS-v-FBS fixture;
- home/away;
- canonical game ID;
- UTC kickoff and Australia/Sydney kickoff/date;
- venue and neutral-site flag;
- season type;
- whether game has already started.

A weekly research pack may retain already-completed fixtures for auditability. Exclude started/completed games from a NEW betting run.

## 4. Research Worker preflight

Call `healthNcaafTotalsResearchPack`.

Require:
- `market_data=false`;
- required source failures = none;
- freshness usable under the current Information State.

`source_health=PARTIAL` is not automatic failure when only declared optional sources are unavailable. Preserve the limitations and reflect them in reliability/fragility.

Call `listNcaafTotalsResearchSlates(season, week)` and resolve one exact slate. Then call `getNcaafTotalsResearchSlate` from offset 0 and follow `pagination.next_offset` to null at ONE `pack_revision`.

On 409/revision mismatch: discard all mixed pages, reload manifest and restart once. Never combine revisions.

Verify:
- unique game count = manifest game_count;
- all selected games FBS-v-FBS;
- team IDs/fixture IDs reconcile;
- `current_season_data_through_week <= target_week - 1`;
- null `current_season_data_through_week` means unavailable/unknown, never zero.

Print a structured research receipt: slate_id, pack_revision, pages, game count, generated/checked time, source health, current cutoff, prior-season cutoff, limitations.

## 5. QBASE receipt

Before live market access call `getNcaafTotalsQbase` and retrieve the calibrated market-blind QBASE artifact. Verify:
- model name/version;
- `market_data=false`;
- feature vector lengths reconcile;
- training/walk-forward receipt exists;
- residual distribution exists.

Retrieve the precomputed QBASE slate pages when available and require its `research_pack_revision` to equal the loaded Layer-1 pack revision and its model version/hash to equal the accepted artifact. A mismatch is not a cosmetic warning: recompute/retrieve the aligned baseline before proceeding.

Current QBASE V0.1.0 receipt at build time: 7,428 FBS-v-FBS training games from 2016-2025; 5,152 temporal walk-forward scored games; overall MAE 13.03, RMSE 16.45. Walk-forward MAE was 13.70 in Week 0/1, 13.24 in Weeks 2-4 and 12.88 from Week 5 onward. These are uncertainty facts, not edge claims.

---

# LAYER 1 — FULL-SLATE RESEARCH PACK

## 6. Structured quantitative evidence — EVERY game

Use the loaded current/prior team profiles as the quantitative spine. Preserve source definitions and missingness.

Core families where available:
- offensive/defensive EPA per play;
- opponent-adjusted offensive/defensive EPA;
- second independent ratings family;
- pass EPA offense vs pass EPA allowed;
- rush EPA offense vs rush EPA allowed;
- offensive/defensive success rate;
- explosiveness creation/prevention;
- havoc creation/allowed;
- offensive pace and pace faced (`playsgame_off`, `playsgame_def`);
- pass tendency and pass tendency faced (`passrate_off`, `passrate_def`);
- games/sample size;
- neutral site / schedule context.

The QBASE interaction logic is market-blind and uses offense against opponent defense, not a simple team-strength ranking. Keep current-season and prior-season evidence distinguishable.

Missing metric != zero.

## 7. Early-season translation

### Week 0/1
There is intentionally no same-season weekly performance input. Use prior-season QBASE evidence as a statistical prior only, then rebuild 2026 structural truth from current personnel/deployment reporting.

### Weeks 2-4
Current information exists but is noisy. The QBASE uses a sample-dependent prior/current blend. Do not override the executed model with an ad-hoc fixed week weight.

### Week 5+
Current-season evidence generally receives greater authority as sample size firms, but a material QB/coaching/system change can still make stale season-to-date averages misleading.

A team's prior numbers may describe a different roster/system. Translate, do not copy.

## 8. Current-information scan — EVERY eligible game

Complete a concise live football scan for both teams:
- starting QB identity/status and meaningful backup risk;
- offensive-line absences/changes;
- high-impact skill-position availability only where it changes scoring/pace pathways;
- major defensive front/coverage personnel losses;
- head coach, coordinator and play-caller changes;
- transfer/depth-chart changes relevant to current role/system;
- suspensions;
- venue/roof/surface;
- game-time temperature, precipitation and especially wind;
- rest/travel/short-week or unusual logistical context;
- credible late breaking football news.

Use primary/official/team/local beat reporting where possible. Do not use betting previews as football evidence when a non-market source exists.

## 9. Deep-research trigger

Escalate a game to deeper research when any applies:
- QB uncertainty/change;
- new coach/coordinator/system;
- major roster/transfer reset;
- low current-season sample;
- current vs prior profile conflict;
- missing structured inputs;
- major OL/defensive injury cluster;
- extreme weather;
- unusual pace/style interaction;
- large disagreement between independent structured rating families;
- QBASE prediction highly sensitive to missing/imputed inputs;
- any material assumption that could move the total distribution.

This funnel is mandatory for scale. Do not spend identical browsing depth on 50+ games when structured data and current status are stable.

## 10. Source-to-parameter ledger

For every material contextual change record:
- evidence/source/date;
- affected football pathway;
- whether it changes expected scoring mean, scenario weight, variance/fragility only, or no numerical input;
- quantified basis if a numerical change is made.

Narrative importance alone is not permission to add/subtract arbitrary points.

If an impact cannot be quantified credibly, reflect it in scenario uncertainty/Fragility rather than fabricating a mean adjustment.

---

# LAYER 2 — P_MODEL / TOTAL DISTRIBUTION

## 11. QBASE anchor

For every eligible game begin from the executed QBASE output aligned to the loaded research revision:
- raw expected total;
- out-of-sample bias calibration;
- calibrated QBASE expected total;
- residual bucket and residual SD;
- pre-market half-point probability grid;
- missing-feature count.

QBASE is a baseline, not final P_model. Live football context can alter it only through the documented ledger/scenario process below.

## 12. Context translation and scenarios

Construct the smallest set of scenarios needed to represent material uncertainty.

Examples:
- QB A active / QB A out;
- OL starter active / out where genuinely material;
- normal weather / severe weather band;
- uncertain play-caller/deployment split.

For each scenario define:
- scenario probability;
- expected-total shift relative to QBASE;
- evidence for the shift;
- whether residual variance should remain at QBASE calibration or be widened.

Rules:
1. Scenario weights must sum to 100% within numerical tolerance.
2. Do not create scenarios for routine noise already represented in QBASE residuals.
3. Do not use sportsbook information to choose scenario weights or shifts.
4. Prefer quantified football evidence. If unsupported, use zero mean shift and increased Fragility rather than an invented adjustment.
5. Avoid double counting: an observed 2026 role/performance change already embedded in current structured data cannot be added again narratively.

## 13. Distribution / probabilities

Use the QBASE temporal out-of-sample residual distribution appropriate to the week bucket as the base error distribution. Apply its documented bias correction once only.

For a single scenario:
`Total = contextual_expected_total + calibrated residual`

For multiple scenarios, compute a weighted mixture of scenario CDFs.

Before ANY market access compute exact frozen probabilities for every supported half-point threshold:
- `P(Over 30.5)` through `P(Over 85.5)`;
- matching Under complements for half-point lines;
- widen grid pre-freeze if needed.

No post-market interpolation or new threshold modelling is allowed.

## 14. Numerical execution is mandatory

Layer 2 must be executed with Code Interpreter/Data Analysis or another actual calculation tool. Prose/code blocks are not execution evidence.

Retain:
- research pack revision;
- QBASE model version/hash and QBASE slate revision;
- all contextual adjustments/scenarios/weights;
- residual bucket/distribution receipt;
- final expected total per game;
- full frozen probability grid;
- Confidence and Fragility;
- code/parameter object;
- seed/draw count if simulation is used;
- input/result SHA-256 hashes;
- numerical audits.

Never claim simulation, probability audit or PASS without execution.

## 15. Pre-freeze integrity gates

Require all:
- complete eligible-slate fixture reconciliation;
- W-1 cutoff passed;
- no market data in Layer 0/1/2 inputs;
- QBASE/research revisions aligned;
- every numerical adjustment has a ledger entry;
- missing values are not silently coerced to zero;
- all scenario weights sum to 1 within 1e-8;
- probabilities within [0,1];
- Over probability monotonically decreases as line rises;
- Under probability monotonically increases;
- Over + Under = 1 for every half-point threshold within numerical tolerance;
- expected totals are finite/plausible or explicitly failed;
- every eligible game has Confidence and Fragility;
- input/output hashes computed from executed objects.

Only after every gate passes print:

`COMPLETE_MODEL_INTEGRITY_CONFIRMED`

`P_MODEL_STATUS: FROZEN`

Record exact freeze timestamp. The ENTIRE slate freezes together.

If execution/audits fail:
`MODEL_INTEGRITY_FAILED — MODEL NOT FROZEN`
Do not access market data.

---

# FREEZE CONTRACT

## 16. Frozen fields

After freeze preserve for every game:
- eligibility/fixture mapping;
- Information State;
- QB/personnel/weather assumptions;
- QBASE anchor/version/revision;
- contextual adjustment ledger;
- scenarios and weights;
- expected total;
- residual distribution/variance;
- complete probability grid;
- Confidence;
- Fragility;
- all material assumptions.

Price movement does not invalidate P_model.

Material post-freeze football information affecting QB, personnel, weather, play-calling, availability or another frozen pathway DOES invalidate the affected slate model:

`Frozen model invalidated — material post-freeze information requires a new research and P_model run.`

If any frozen value changes during market integration:
`Market Integration invalid — P_model anchor breached.`

---

# LAYER 3 — AU MARKET INTEGRATION

## 17. Gateway preflight

`healthNcaafTotalsMarketGateway` may be called before Layer 1 because it explicitly makes no odds request. Require configured=true/ok=true. It contains no price data.

Do NOT call `getNcaafTotalsBoard` until after freeze.

## 18. Retrieve market board after freeze

Call `getNcaafTotalsBoard` with UTC commence bounds covering the frozen eligible slate. Start offset 0 and follow pagination to null using ONE `board_revision`.

On 409: discard mixed pages and restart once at offset 0. Never combine market revisions.

Verify:
- sport_key=`americanfootball_ncaaf`;
- region=`au`;
- market_key=`totals`;
- market_group=`ncaaf-totals`;
- exact fixture by both teams and kickoff time/date;
- event ID unique;
- only full-game Over/Under totals.

The full-sport Odds API endpoint requests one region (`au`) and one market (`totals`); under The Odds API's documented cost formula this is one usage credit for a non-empty request. Do not multiply calls game-by-game unnecessarily.

## 19. Exact mapping / duplicate rule

For each sportsbook outcome require an exact frozen half-point line. No interpolation or creation of P_model after market access.

For duplicate identical fixture + side + line:
1. highest valid decimal price;
2. newest valid `last_update`;
3. bookmaker key alphabetically.

Never average bookmaker prices.

## 20. Market math

For every exact mapped outcome:
- `P_break_even = 1 / decimal_odds`
- `Fair Price = 1 / P_model`
- `Price Edge = P_model - P_break_even`
- `Expected ROI = P_model * decimal_odds - 1`

No invented vig-adjusted probability unless a later validated method explicitly requires it.

## 21. Price freshness

Relative to market `retrieved_at` / bookmaker `last_update`:
- CURRENT: 0-30 minutes;
- AGING: >30-90 minutes;
- STALE: >90 minutes;
- UNKNOWN: missing/invalid.

AGING caps recommendation grade at B+. STALE/UNKNOWN cannot be a final BET recommendation until refreshed.

---

# LAYER 4 — FULL-SLATE RANKING

## 22. Eligibility

A recommended play requires:
- intact market-blind freeze pathway;
- exact frozen line mapping;
- positive Price Edge;
- positive Expected ROI;
- offered odds above Fair Price;
- usable price freshness;
- no unresolved material post-freeze news;
- acceptable Fragility for the claimed grade.

Never force a bet.

## 23. Ranking

Rank the positive-edge slate primarily by:
1. Expected ROI;
2. Price Edge;
3. lower frozen Fragility / sensitivity;
4. research/data quality;
5. price freshness;
6. Confidence as a reliability tie-breaker.

Confidence is reliability. It must not mechanically change P_model or edge.

Output:
- BEST SINGLE;
- Top 10 positive-edge NCAA totals (or fewer if fewer qualify);
- additional meaningful positives;
- passes/tight games;
- coverage/data/freshness warnings.

For each ranked play show: fixture, Over/Under + exact line, book, odds, P_model, fair price, break-even, Price Edge, Expected ROI, Confidence, Fragility, freshness and one-line frozen thesis.

---

# FAILURE / REFRESH RULES

## 24. Retry policy

Retry once only for timeout, 429, 5xx or plausible transient upstream failure.

Do not retry auth/configuration, invalid fixture, schema mismatch, malformed response, impossible cutoff, market-boundary breach or non-transient 4xx. Research revision and market-board 409 use their explicit one-restart procedure.

Never invent unavailable source values or prices.

## 25. Market refresh

For a price refresh with no material new football information:
- preserve exact frozen P_model and freeze timestamp;
- do no new research;
- call `getNcaafTotalsBoard` again;
- reverify fixtures;
- rerun Layers 3/4 only.

If material football information arrived, invalidate and rerun Layers 1/2 before any new ranking.

---

# REQUIRED RUN RECEIPTS / OUTPUT

## 26. Layer 1 receipt
Show:
- target season/week/run window;
- eligible fixture count;
- research pack revision/pages;
- current data through week;
- required/optional source health;
- QBASE artifact version/hash + walk-forward reference;
- live-current research completion and deep-research triggers.

## 27. Layer 2 receipt
Show:
- QBASE expected total per eligible game;
- material contextual shift/scenario summary;
- final expected total;
- residual bucket;
- Confidence/Fragility;
- numerical execution/hash/audit receipt;
- freeze timestamp.

For large slates, keep the user-facing table compact; retain the full probability grid internally for exact post-freeze mapping.

## 28. Layer 3/4 output
Show market snapshot/revision and final ranked table. Do not dump every bookmaker outcome unless useful.

After successfully completed Layers 3/4 end exactly:

`FINAL_NCAAF_TOTALS_SLATE_RANKING_COMPLETE`
