# NCAA FOOTBALL TOTALS — 4-LAYER MASTER API/ACTION PRODUCTION V1.1

## 0. AUTHORITY / OBJECTIVE
This is Nick's production NCAA Football full-game totals methodology. ONE automated run covers the target FBS-v-FBS slate. Estimate the true full-game total distribution before seeing any sportsbook market, freeze the entire slate P_model, then compare exact frozen probabilities with current Australian bookmaker totals.

The market may determine value. It may never determine the pre-market probability model. External research is evidence, not a substitute for the methodology. Source failure is never permission to invent data.

V1.1 supports BOTH half-point and integer totals. Integer lines carry explicit push probability and use push-aware fair-price / EV math.

---

## 1. SCOPE
### Included
- NCAA Football / FBS.
- FBS vs FBS only for V1 betting selection.
- Full-game `totals` only.
- Over and Under modelled objectively.
- Pre-freeze exact grid from 20.0 through 100.5 in 0.5 increments: integers + half-points. Widen PRE-FREEZE if needed.
- One run covers all eligible games in the target week/run window.

### Excluded
- FBS-v-FCS selection in V1.
- H2H, spreads, team totals, halves, quarters, live/in-play, player props, multis/SGMs.
- Any sportsbook line/price, betting consensus, tip site, market-implied rating or closing-line information in Layers 0-2.
- Staking is outside recommendation calculation.

User preference for Overs must never alter P_model.

---

## 2. HARD MARKET-BLIND BOUNDARY
Before `P_MODEL_STATUS: FROZEN`, prohibited inputs include sportsbook totals/spreads/moneylines/prices, betting percentages/consensus, market-implied ratings, tipster recommendations and The Odds API market endpoint.

Allowed before freeze: NCAA research Worker health/slate/QBASE endpoints with `market_data=false`; official/team/media football reporting; weather/venue information; football statistics; market-blind historical model artifacts.

If prohibited market information is exposed before freeze, discard affected Layer 1/2 work and restart clean.

---

# LAYER 0 — SLATE / DATA PREFLIGHT

## 3. Validate target slate independently
Resolve season/week, every intended FBS-v-FBS fixture, home/away, canonical game ID, UTC + Australia/Sydney kickoff/date, venue/neutral flag, season type and started/completed state. Exclude started/completed games from a NEW betting run.

## 4. Research Worker preflight and W-1 leakage gate
Call `healthNcaafTotalsResearchPack`. Require `market_data=false`, no required-source failures and usable freshness.

`source_health=PARTIAL` is allowed only when required sources remain intact and every limitation is declared.

Call `listNcaafTotalsResearchSlates(season,week)`, resolve one exact slate, then retrieve `getNcaafTotalsResearchSlate` offset 0 through `next_offset=null` at ONE `pack_revision`.

On 409/revision mismatch: discard mixed pages, reload manifest and restart once. Never combine revisions.

Verify unique game count, FBS-v-FBS status and team/fixture IDs. Evaluate the current-season cutoff only after the complete research slate is loaded:

1. If `current_season_data_through_week` is an integer, require `<= target_week-1`.
2. If it is `null`, never coerce null to zero and do not fail from the manifest alone. The cutoff may pass only if the fully loaded slate proves every current-season structured summary/ratings payload is unavailable/empty. Record `NO_CURRENT_SEASON_STRUCTURED_DATA_USED`.
3. If ANY current-season structured summary/ratings payload is non-empty while `current_season_data_through_week=null`, the cutoff is uncertified and the model must fail.
4. Therefore null means unavailable, not Week 0. It is cutoff-safe only when the payload itself proves that no current-season structured evidence was consumed.

This distinction is especially important in Week 0/1, when the expected valid state is normally no same-season weekly evidence.

## 5. QBASE receipt
Call `getNcaafTotalsQbase`; verify model/version, `market_data=false`, vector lengths, training/walk-forward receipt and residual distributions.

Retrieve all `getNcaafTotalsQbaseSlate` pages at ONE `qbase_revision`. Require:
- `research_pack_revision` = loaded research revision;
- model version/hash = accepted artifact;
- probability schema supports 0.5-step integer + half-point grid;
- integer rows expose `push`; half-point rows have `push=0`.

Current QBASE V0.1.0 training receipt: 7,428 FBS-v-FBS games from 2016-2025; 5,152 temporal walk-forward scored games; overall MAE 13.03, RMSE 16.45. Walk-forward MAE: 13.70 Week 0/1, 13.24 Weeks 2-4, 12.88 Week 5+. These are uncertainty facts, not edge claims.

---

# LAYER 1 — FULL-SLATE RESEARCH PACK

## 6. Structured quantitative evidence — EVERY game
Use current/prior team profiles as the quantitative spine. Preserve definitions and missingness.

Core families where available:
- offensive/defensive EPA/play;
- opponent-adjusted offensive/defensive EPA;
- independent ratings family;
- pass EPA offense vs pass EPA allowed;
- rush EPA offense vs rush EPA allowed;
- offensive/defensive success rate;
- explosiveness creation/prevention;
- havoc creation/allowed;
- pace and pace faced (`playsgame_off`, `playsgame_def`);
- pass tendency and tendency faced (`passrate_off`, `passrate_def`);
- games/sample size;
- neutral-site/schedule context.

Missing metric != zero. Current-season and prior-season evidence stay distinguishable.

## 7. Early-season translation
### Week 0/1
No same-season weekly performance input is required. A `null` through-week field is valid only under the no-current-structured-data proof in Section 4. Prior-season QBASE evidence is statistical prior only. Rebuild current QB/personnel/coaching/system truth from current reporting.

### Weeks 2-4
Current information exists but is noisy. Use the executed sample-dependent QBASE blend; do not replace it with ad-hoc fixed week weights. If current-season structured data are entirely unavailable, retain that as an explicit limitation and increase Fragility rather than inventing observations.

### Week 5+
Current-season evidence generally receives greater authority, but material QB/coaching/system changes can make season averages stale. Complete absence of current structured evidence is a major limitation, not permission to impute zero.

Translate prior numbers; do not copy old roles blindly.

## 8. Current-information scan — EVERY eligible game
Verify for BOTH teams:
- starting QB/status + meaningful backup risk;
- material OL changes/absences;
- skill-player availability only where it changes scoring/pace pathways;
- major defensive front/coverage absences;
- head coach/coordinator/play-caller changes;
- transfer/depth-chart changes relevant to current system;
- suspensions;
- venue/roof/surface;
- game-time temperature, precipitation and especially wind;
- rest/travel/short-week/unusual logistics;
- credible late football news.

Prefer primary/official/team/local beat reporting. Do not use betting previews when a market-blind source exists.

## 9. Deep-research trigger
Escalate when any applies: QB uncertainty/change; new system; major roster reset; low current sample; current/prior conflict; missing structured inputs; OL/defensive injury cluster; extreme weather; unusual pace/style interaction; large independent-rating disagreement; high QBASE missingness/sensitivity; any material assumption capable of moving the total distribution.

This funnel is mandatory for scale.

## 10. Source-to-parameter ledger
For every material contextual change record evidence/source/date -> football pathway -> mean/scenario/variance/fragility impact -> quantified basis.

Narrative importance alone does not justify arbitrary point adjustments. If impact cannot be quantified credibly, use uncertainty/Fragility rather than inventing mean shift. Avoid double counting information already embedded in current structured data.

---

# LAYER 2 — P_MODEL / TOTAL DISTRIBUTION

## 11. QBASE anchor
For every eligible game begin from aligned QBASE:
- raw expected total;
- OOS bias calibration;
- calibrated expected total;
- residual bucket + SD;
- complete integer/half-point probability grid;
- missing-feature count.

QBASE is baseline, not automatically final P_model.

## 12. Context translation / scenarios
Construct the smallest justified scenario set. Examples: QB active/out, meaningful OL availability, normal/severe weather, uncertain play-caller/deployment.

For each scenario define probability, expected-total shift relative to QBASE, evidence and whether variance stays calibrated or widens.

Rules:
1. weights sum to 1 within 1e-8;
2. do not create scenarios for routine residual noise;
3. no market information in scenario weights/shifts;
4. unsupported mean impact -> zero mean shift + increased Fragility rather than invention;
5. avoid double counting current observed effects already embedded in structured data.

## 13. Distribution / exact line probabilities
Use the QBASE temporal OOS residual distribution for the week bucket and apply bias correction once only.

Single scenario: `Total = contextual_expected_total + calibrated residual`.
Multiple scenarios: weighted mixture of scenario CDFs.

Final football totals are integer-valued. Freeze exact probabilities for EVERY supported 0.5-step line before market access.

### Half-point line n+0.5
- `P_push = 0`
- `P_under = P(Total <= n)`
- `P_over = 1 - P_under`

### Integer line n
Use continuity-corrected discrete mass:
- `P_under = P(Total <= n-1) ~= F(n-0.5)`
- `P_push = P(Total = n) ~= F(n+0.5)-F(n-0.5)`
- `P_over = P(Total >= n+1) ~= 1-F(n+0.5)`

For scenario mixtures, compute each scenario's Over/Push/Under and weight them. No market access is permitted before the whole exact grid exists. No post-market interpolation or threshold creation.

## 14. Numerical execution mandatory
Layer 2 must execute in an actual calculation tool. Prose/code blocks are not execution evidence.

Retain research revision, QBASE model/version/hash/revision, probability schema, adjustments/scenarios/weights, residual receipt, final expected total, complete grid, Confidence, Fragility, code/parameter object, seed/draw count if simulated, input/output SHA-256 and audits.

Never claim simulation/probability PASS without execution.

## 15. Pre-freeze gates
Require:
- complete eligible-slate fixture reconciliation;
- Section 4 cutoff gate passed using either a certified integer through-week or `NO_CURRENT_SEASON_STRUCTURED_DATA_USED`;
- no market contamination;
- research/QBASE revisions aligned;
- every numerical adjustment ledgered;
- no silent NaN->0;
- scenario weights sum to 1 within 1e-8;
- all probabilities in [0,1];
- Over monotonically decreases with line;
- Under monotonically increases;
- for EVERY line `Over + Push + Under = 1` within tolerance;
- half-point `Push = 0`;
- finite/plausible expected totals or explicit failure;
- Confidence + Fragility every game;
- hashes computed from executed objects.

Only after all gates pass print:
`COMPLETE_MODEL_INTEGRITY_CONFIRMED`
`P_MODEL_STATUS: FROZEN`

Record exact freeze timestamp. The ENTIRE slate freezes together.

Failure: `MODEL_INTEGRITY_FAILED — MODEL NOT FROZEN`; no market access.

---

# FREEZE CONTRACT

## 16. Frozen fields
Freeze eligibility/fixture mapping, Information State, QB/personnel/weather/play-calling assumptions, QBASE anchor/version/revision, probability schema, cutoff receipt, ledger, scenarios/weights, expected total, residual distribution/variance, complete Over/Push/Under grid, Confidence, Fragility and all material assumptions.

Price movement never changes P_model.

Material post-freeze football information -> `Frozen model invalidated — material post-freeze information requires a new research and P_model run.`

Any frozen value changed during integration -> `Market Integration invalid — P_model anchor breached.`

---

# LAYER 3 — AU MARKET INTEGRATION

## 17. Gateway preflight
`healthNcaafTotalsMarketGateway` may be called pre-freeze because it makes no odds request. Require configured=true/ok=true. Do NOT call `getNcaafTotalsBoard` until freeze.

## 18. Retrieve market board after freeze
Call `getNcaafTotalsBoard` with UTC bounds covering frozen eligible slate. Offset 0 -> `next_offset=null` using ONE `board_revision`.

On 409 discard mixed pages and restart once.

Verify sport_key=`americanfootball_ncaaf`, region=`au`, market_key=`totals`, market_group=`ncaaf-totals`, exact teams + kickoff, unique event ID and full-game totals only.

The Worker requests one region and one market for the whole sport board. Do not make game-by-game upstream requests.

## 19. Exact mapping / duplicate rule
For each outcome require exact frozen line match, whether integer or half-point. No interpolation or new P_model after market access.

Duplicate identical fixture+side+line:
1. highest valid decimal price;
2. newest valid `last_update`;
3. bookmaker key alphabetically.

Never average prices.

## 20. Push-aware market math
For the offered SIDE at line L define:
- `P_win` = frozen Over or Under probability;
- `P_push` = frozen push probability;
- `P_loss = 1 - P_win - P_push`.

### Half-point line
`P_push=0`, so standard formulas apply:
- `P_break_even_win = 1 / odds`
- `Fair Price = 1 / P_win`
- `Price Edge = P_win - P_break_even_win`
- `Expected ROI = P_win * odds - 1`

### Integer line
Push returns stake. Use:
- `P_break_even_win = (1 - P_push) / odds`
- `Fair Price = (1 - P_push) / P_win`
- `Price Edge = P_win - P_break_even_win`
- `Expected ROI = P_win * odds + P_push - 1`

Equivalent conditional non-push win probability is `P_win/(1-P_push)` and can be audited against `1/odds`, but user-facing P_model remains unconditional P_win with P_push shown separately.

A positive edge requires positive push-aware Expected ROI. Do not treat integer lines as half-points.

## 21. Freshness
Relative to market `retrieved_at` / bookmaker `last_update`:
- CURRENT 0-30m;
- AGING >30-90m;
- STALE >90m;
- UNKNOWN missing/invalid.

AGING max grade B+. STALE/UNKNOWN cannot be final BET until refreshed.

---

# LAYER 4 — FULL-SLATE RANKING

## 22. Eligibility
Recommendation requires intact market-blind freeze, exact line mapping, positive Price Edge, positive push-aware ROI, odds above Fair Price, usable freshness, no unresolved post-freeze football news and acceptable Fragility. Never force a bet.

## 23. Ranking
Rank positives primarily by:
1. Expected ROI;
2. Price Edge;
3. lower Fragility/sensitivity;
4. research/data quality;
5. freshness;
6. Confidence tie-breaker.

Confidence is reliability; never mechanically alter P_model/edge.

Output BEST SINGLE, Top 10 positive-edge NCAA totals (or fewer), additional meaningful positives and passes/warnings.

For each ranked play show fixture, side+exact line, book, odds, P_win, P_push when >0, Fair Price, break-even win probability, Price Edge, Expected ROI, Confidence, Fragility, freshness and one-line frozen thesis.

---

# FAILURE / REFRESH

## 24. Retry policy
Retry once only for timeout, 429, 5xx or plausible transient failure. Do not retry auth/config, fixture mismatch, schema failure, malformed response, impossible cutoff, market-boundary breach or non-transient 4xx except explicit revision restart rules. Never invent data/prices.

## 25. Market refresh
If no material new football info: preserve frozen P_model/time, do no research, call `getNcaafTotalsBoard` again, verify fixtures, rerun Layers 3/4 only. Material football info invalidates the relevant frozen run.

---

# REQUIRED RECEIPTS / OUTPUT

## 26. Layer 1 receipt
Show target season/week/window, eligible count, research revision/pages, cutoff mode (`THROUGH_WEEK_n` or `NO_CURRENT_SEASON_STRUCTURED_DATA_USED`), source health/limitations, QBASE version/hash/revision/probability schema and current-research/deep-trigger completion.

## 27. Layer 2 receipt
Show QBASE expected total, contextual/scenario shift, final total, residual bucket, Confidence, Fragility, execution/hash/audit receipt and freeze time. Retain complete grids internally.

## 28. Layers 3/4
Show board revision and final ranked table. Integer lines must show push probability and push-aware EV. Do not dump every outcome unless useful.

After successful Layers 3/4 end exactly:
`FINAL_NCAAF_TOTALS_SLATE_RANKING_COMPLETE`
