# NBA ASSISTS + REBOUNDS — 4-LAYER MASTER — PRODUCTION V1.0

**Model:** Nick NBA Assists + Rebounds  
**League:** NBA  
**Scope:** player Assists and Rebounds Overs, standard and alternate ladders  
**Run unit:** one complete NBA `America/New_York` league-date slate  
**Default mode:** `BOTH`  
**Status:** production methodology; live production acceptance remains mandatory before release sign-off.

---

## 1. NON-NEGOTIABLE MODEL PRINCIPLES

1. **Market blind through Layer 2.** No sportsbook price, bookmaker line, market consensus, betting tip, projection site or odds-derived input may enter fixture selection, research, current-role translation or P_model.
2. **One persistent slate run.** A run covers every still-eligible NBA game on one ET league date. The server exposes only the next 1–2 pending games for research and requires checkpoint persistence before later games become available.
3. **Historical data is prior evidence, never current truth.** Last-season minutes, shares, rolling rates and QBASE means are anchors only. Trades, free agency, injuries, starting roles, coaching, preseason/camp and current lineup dependencies must rebuild the current state.
4. **GPT supplies basketball state, not a final mean.** The research layer supplies evidence-bound projected minutes, starter probability, expected assist/rebound opportunity and team environment. It cannot submit a player assists/rebounds mean or arbitrary probability override.
5. **Server-authoritative quantitative transforms only.** Runtime scoring is restricted to typed transformations of promoted QBASE artifacts: `QBASE_RUNTIME_SCORE`, `MINUTES_RECOMPUTE`, `ROLE_OPPORTUNITY_RECOMPUTE`, `LINEUP_DEPENDENCY_RECOMPUTE`.
6. **No universal prior-competition multiplier.** NCAA, G League, EuroLeague, NBL or other prior competition translation must have a separately promoted empirical route. Without one, the player is excluded from P_model rather than fabricated.
7. **Whole-slate atomic freeze.** Market access is impossible until all eligible games are `RESEARCH_COMPLETE` and the requested heads freeze together under one immutable slate receipt.
8. **Exact thresholds only.** Integer and half-point probabilities are generated before prices. No interpolation after a market line is seen.
9. **No forced bet.** Layer 4 ranks positive EV only. If none qualify, output `NO BET`.
10. **No P_model mutation after freeze.** Price refreshes are Layer 3/4 only. Material basketball news invalidates affected frozen scope; a changed P_model requires a new run.

---

# 2. PLATFORM ARCHITECTURE

## Research / Freeze Worker
`nba-player-props-research-v1`

Responsibilities:
- ET league-date fixture discovery;
- sanitized current ESPN schedule and roster identity;
- exact Git/runtime-asset pinning;
- persistent `NbaSlateRun` Durable Object;
- 1–2 game research queue;
- research checkpoint validation and market-leakage rejection;
- server historical prior assembly;
- deterministic QBASE current-state transforms;
- exact probability grids;
- atomic slate freeze;
- immutable freeze retrieval;
- late-news invalidation registry;
- post-freeze market-access grant.

## Market Worker
`nba-player-props-market-v1`

Responsibilities:
- obtain a fresh market-access grant from Research Worker before any sportsbook request;
- free The Odds API NBA event discovery;
- one-to-one event matching by exact teams plus kickoff tolerance;
- event-level requests for only:
  - `player_assists`
  - `player_assists_alternate`
  - `player_rebounds`
  - `player_rebounds_alternate`;
- strict player identity resolution inside the frozen game;
- Overs-only price ingestion;
- manual Bet365 / sportsbook screenshot ingestion after freeze;
- current-snapshot replacement rather than stale-price accumulation;
- best exact current price by player/head/side/threshold;
- push-aware EV;
- global Layer 4 rankings.

The Market Worker does not own, rebuild or mutate P_model.

---

# 3. HISTORICAL / QBASE FOUNDATION

## Accepted history
The base V1 source gate uses five pinned NBA seasons and an independent source-reconciliation chain. Source inconsistencies adjudicated against final boxes are handled by removing the **entire affected game**, never by patching one statistic or one team.

Current accepted build after source adjudication:
- original validated player-games: 139,809;
- complete games quarantined: 14;
- player-game rows removed: 280;
- accepted player-games: 139,529;
- accepted-history SHA-256: `2e6926aa87ccebafbf938322f8facefeb54de63eb22f924dc2793afc61750b25`.

The deterministic history feature pipeline is strictly pregame/lagged. No current-game outcome feature may enter its own prediction.

## Independent heads
Assists and Rebounds are separate count-model challenges and separate promotion artifacts.

Locked selection process:
- 2024 and 2025 expanding-window validation folds;
- candidates: shrunk Poisson, shrunk NB, regularized GLM Poisson, regularized GLM NB;
- selection by validation Brier subject to no early-season cohort regression versus locked shrunk-Poisson baseline;
- 2026 untouched holdout used only for predeclared pass/fail promotion review;
- holdout cannot reselect model family.

Both heads have passed `PROMOTED_CORE_V1` under the corrected-history gate. Runtime numeric parameters are exported at deterministic production precision and CI reruns the challenge twice to require byte-identical evidence.

## Base feature families
Shared history includes:
- games before;
- team games before;
- rest;
- player days since last game;
- team change;
- prior starter state and rolling start rate;
- rolling minutes;
- team pace proxy.

Assists adds:
- rolling assists;
- assists per minute;
- assist share;
- turnovers / FGA context;
- rolling team assists;
- opponent assists allowed.

Rebounds adds:
- rolling rebounds;
- offensive / defensive rebound components;
- rebounds per minute;
- rebound share;
- rolling team rebounds;
- opponent rebounds allowed.

## Specialist metrics
Potential assists, touches, passes, rebound chances and related tracking metrics remain feature-gated. A metric is never treated as zero when unavailable. It enters QBASE only after historical + runtime coverage, schema, identity, temporal integrity and clean OOS challenge all pass.

Base V1 is deliberately permitted without specialist metrics.

---

# 4. LAYER 0 — PREFLIGHT, SLATE LOCK, ELIGIBILITY

1. Research Worker health must be healthy, market blind and Durable-Object enabled.
2. Market Worker health may be checked, but **no market refresh** may be called yet.
3. Bet Tracker preflight must pass current schema requirements before the run is treated as operational.
4. Resolve the target `America/New_York` league date through the Research Worker.
5. Only not-yet-started games returned by the Worker are eligible for a new run.
6. Start exactly one slate run with `run_mode=BOTH` unless Nick explicitly requests a single head.
7. Preserve:
   - `run_id`;
   - `slate_date_et`;
   - exact eligible game IDs and fixture locks;
   - source Git commit;
   - promoted QBASE model versions / receipts.
8. If interrupted, recover the same `run_id`. Never silently replace an existing valid run.

---

# 5. LAYER 1 — DEEP CURRENT BASKETBALL RESEARCH

## 5.1 Batch discipline
Call the next-research endpoint. Research **only** the returned 1–2 games. Checkpoint those games immediately when complete. Verify they move into `completed_game_ids`. Only then request the next batch.

Never preload later pending games before the current server batch is checkpointed.

## 5.2 Source hierarchy
Use source quality appropriate to the claim.

**Tier 0 — canonical / direct**
- NBA / team transactions and roster status;
- official injury/status information where available;
- official team/league communications;
- direct coach/player statements.

**Tier 1 — strong current reporting**
- credible team beat reporters;
- reputable national basketball reporting;
- confirmed training-camp / preseason rotation reporting.

**Tier 2 — descriptive/statistical support**
- reliable NBA statistical/reference sources;
- historical lineup/role splits where temporally valid;
- current roster/depth information from reputable databases.

**Tier 3 — secondary context**
Use only when clearly labelled and never as the sole support for a material availability/role claim.

Do not use betting-tip sites or market-derived projections in Layers 0–2.

Every evidence item requires a stable `evidence_id`, HTTPS URL, title, check time, tier and evidence type.

## 5.3 Research population
Research the complete expected meaningful rotation, not only players assumed to have a sportsbook prop. Market availability is unknown pre-freeze.

Default inclusion target:
- expected rotation players generally projected for meaningful minutes;
- all likely starters;
- primary/secondary creators;
- primary frontcourt rebounders;
- questionable/doubtful rotation players whose status materially affects teammates;
- rookies/new-to-NBA players even when their own QBASE may be excluded, because their role can change teammate opportunity.

End-of-bench players with no plausible rotation role need not be modeled, but material rotation uncertainty must be documented.

## 5.4 Fixture research
For both teams establish:
- game identity and start time;
- availability and injury picture;
- expected starting five;
- expected rotation and bench hierarchy;
- coach/system changes;
- rest/travel/back-to-back context;
- pace expectations;
- creator hierarchy;
- frontcourt hierarchy;
- lineup dependencies;
- current preseason/training-camp evidence where relevant.

## 5.5 Player current-state research
For each researched player establish:
- exact ESPN player/team identity;
- availability: `ACTIVE / PROBABLE / QUESTIONABLE / DOUBTFUL / OUT / UNKNOWN`;
- role state: `RETURNING_SAME / RETURNING_CHANGED / NEW_TO_TEAM / ROOKIE / NEW_TO_NBA / UNKNOWN`;
- projected minutes low / mean / high;
- expected starter probability;
- direct evidence bindings;
- confidence inputs and fragility inputs;
- head-specific causal pathway.

### Early-season priority
Early season is not a reason to lean harder on last year. It is the opposite: explicitly audit:
- trades and free-agent movement;
- departures and vacated minutes;
- vacated assists / creator possessions;
- vacated rebounds / frontcourt possessions;
- new starters;
- new sixth-man / stagger roles;
- new head coach or offensive scheme;
- preseason starting groups and rotation patterns;
- rookie/import integration;
- injuries changing the expected hierarchy.

## 5.6 Server research-seed anchors
The seed exposes two kinds of market-blind prior evidence.

### Player prior
For players with accepted NBA history:
- recent minutes;
- start rates;
- assist/rebound rates and shares;
- prior team;
- historical QBASE prior mean for both heads.

### Team environment prior
For each team:
- recent estimated possessions;
- team assists;
- team rebounds;
- assists allowed;
- rebounds allowed.

These values are **anchors only**. They must not be copied blindly when personnel/system changed.

## 5.7 Research-state numerical protocol
The GPT must provide current-state numerical inputs, but these are **not P_model means**.

### Projected minutes
Choose low / mean / high from:
- expected rotation slot;
- starter likelihood;
- coach usage;
- injury restriction risk;
- competition for minutes;
- preseason/current deployment;
- game-context fragility.

The band must reflect real uncertainty. Do not create a narrow band simply to increase model confidence.

### Expected starter probability
Use a probability in `[0,1]` representing current evidence about the starting role. `1.0` is appropriate only when the role is genuinely settled.

### Expected possessions
Start from the server team pace prior. Move it only for current evidence such as meaningful coaching/system change, personnel-driven pace change, or credible current/preseason pace evidence. Avoid large speculative moves.

### Expected team assists
Start from server team-assist prior and evaluate:
- new primary creator / point guard;
- creator departures;
- ball movement/system change;
- expected finishing quality and lineup;
- opponent historical assists-allowed environment;
- current lineup availability.

This is a team environment estimate, not the target player's assists prediction.

### Expected assist share
Start from player historical assist-share prior when available and explicitly redistribute creation based on:
- lead/secondary creator hierarchy;
- on-ball initiation;
- stagger pattern;
- teammate creator absences/additions;
- starting vs bench unit;
- role change supported by current evidence.

### Expected team rebounds
Start from team rebound prior and evaluate:
- frontcourt personnel;
- expected minutes by centers/forwards;
- opponent rebound environment;
- lineup size;
- meaningful coaching/system changes.

### Expected rebound share
Start from player rebound-share prior when available and redistribute based on:
- frontcourt hierarchy;
- teammate rebound competition;
- expected position/lineup size;
- small-ball/big-lineup deployment;
- center/forward absences;
- current minutes role.

Do not derive any of these values from a sportsbook line.

## 5.8 New-to-NBA players
Research their prior competition and current NBA role because they affect teammates. But base V1 does **not** generate their own P_model unless the relevant prior-competition translation route has separately passed promotion. No fallback multiplier is allowed.

## 5.9 Specialist metric registry
For the game, record each relevant specialist metric status as `AVAILABLE`, `PARTIAL`, `UNAVAILABLE`, `BLOCKED` or `NOT_RELIABLE`. Unavailable/blocked metrics are omitted, not zeroed.

## 5.10 Checkpoint
Checkpoint each current server batch only when research is complete. The Worker rejects:
- market material;
- fixture drift;
- player/team identity errors;
- missing requested-head context;
- unsupported opportunity fields;
- missing evidence bindings;
- out-of-order game batches.

Continue until the run returns `RESEARCH_COMPLETE`.

---

# 6. LAYER 2 — SERVER P_MODEL AND ATOMIC FREEZE

Layer 2 requires **no client-entered final player means**.

After all game research is checkpointed, call the freeze endpoint with an empty body.

For each returning player/head the Worker:
1. assembles the server historical feature prior from accepted history;
2. validates temporal identity and current fixture;
3. applies projected-minutes/starter recomputation;
4. applies whitelisted current role/opportunity features;
5. applies head-specific lineup/team environment features;
6. scores the promoted QBASE artifact;
7. uses its promoted dispersion;
8. builds an exact count probability grid.

Unsupported feature or free-form mean fields have no API path.

## Probability distribution
Promoted QBASE heads are count models. Runtime output uses Poisson only when dispersion is effectively zero; otherwise Negative Binomial NB2.

For each frozen player/head store:
- final server mean;
- dispersion alpha;
- exact count PMF;
- tail probability;
- at-least ladder;
- half-point Over/Under grid;
- integer Over/Push/Under grid;
- model/promotion/prior/quantitative receipts;
- transform-chain receipt.

## Whole-slate freeze
Freeze succeeds only after every eligible game research checkpoint exists. It produces:
- original `frozen_at`;
- one immutable `freeze_receipt_sha256`;
- exact frozen fixture metadata per game;
- all modeled players / heads;
- explicit exclusions.

Required status: `FROZEN`.

A rookie/new-to-NBA player without promoted translation is an explicit exclusion, not a model failure and not a fabricated estimate.

No sportsbook request is permitted before this point.

---

# 7. LAYER 3 — POST-FREEZE MARKET INTEGRATION

## 7.1 Server gate
The Market Worker must obtain a fresh `nba_market_access_grant_v1` from the Research Worker. The grant binds:
- `run_id`;
- slate date;
- run mode;
- original `frozen_at`;
- freeze receipt;
- currently allowed game IDs;
- invalidated game IDs.

Without the grant, Layer 3 stops.

## 7.2 The Odds API
The Worker first uses NBA event discovery, then maps each allowed frozen game one-to-one by:
- exact normalized home team;
- exact normalized away team;
- kickoff within strict tolerance.

Ambiguous/missing event mappings fail closed.

Only the four approved player prop keys are requested. Player identities are then resolved one-to-one inside the already-frozen game. Unknown sportsbook players are recorded and skipped; names are never guessed across players.

V1 ranks **Overs only**.

## 7.3 Current snapshot rule
Each new Odds API refresh replaces the prior API snapshot for current ranking. Historical receipts are retained, but stale previous API prices are not allowed to compete with current prices.

## 7.4 Manual screenshots / Bet365
After freeze, screenshots may supplement API prices.

Extract every clearly visible valid quote with:
- game ID;
- player ID when known, otherwise exact player name;
- assists/rebounds;
- Over;
- exact threshold;
- decimal price;
- bookmaker;
- capture time;
- screenshot evidence ID.

The submitted `freeze_receipt_sha256` must equal the original frozen run. Screenshot capture/ingestion must be post-freeze.

A new manual screenshot submission replaces the current manual snapshot; its predecessor is retained only as history.

## 7.5 Best exact price
Current API and current manual snapshots are combined. For duplicate game/player/head/side/threshold combinations retain the highest current valid price.

No line interpolation or threshold synthesis.

---

# 8. LAYER 4 — EDGE, RANKING, BEST SINGLE

## Half-point line
For line `k + 0.5`:
- `P_win = P(X >= k+1)`;
- `P_push = 0`;
- `P_loss = 1 - P_win`.

## Integer line
For line `k`:
- `P_win = P(X > k)`;
- `P_push = P(X = k)`;
- `P_loss = P(X < k)`.

## Push-aware EV
For decimal odds `d`:

`EV/unit = P_win * (d - 1) - P_loss`

For integer markets the fair decimal price conditional on action is:

`fair_price = (P_win + P_loss) / P_win = (1 - P_push) / P_win`

The Worker also reports the conditional non-push win probability and a comparable break-even probability.

## Ranking outputs
Return:
1. `BEST SINGLE` across both heads if any positive EV exists;
2. Top 10 combined positive edges;
3. all positive Assists edges;
4. all positive Rebounds edges;
5. `NO BET` if none are positive.

For each recommendation surface:
- player / team;
- stat / exact threshold / Over;
- bookmaker / decimal odds;
- P_win and P_push;
- fair price / break-even;
- EV per unit / probability edge;
- model mean;
- Confidence;
- Fragility;
- concise basketball thesis from Layer 1.

Do not force one selection from each head.

---

# 9. CONFIDENCE AND FRAGILITY

Base V1 assigns deterministic server categories from current research state rather than letting prose inflate certainty.

Broadly:
- settled active returning roles with tight minutes bands can be `A / LOW`;
- changed-team/changed-role or moderate minutes uncertainty generally moves to `B / MEDIUM`;
- questionable/doubtful/unknown availability, rookie/new-to-NBA state or severe role uncertainty produces `C / HIGH`.

These categories describe model-state reliability. They are not a substitute for EV and are not converted to a fake numeric probability.

---

# 10. LATE NEWS / INVALIDATION

After freeze, material news never edits frozen probabilities.

If news materially changes one or more games:
1. record affected game IDs and reason through the invalidation endpoint;
2. original freeze object / timestamp / receipt remain unchanged;
3. market grant excludes invalidated games;
4. run status becomes `FROZEN_BUT_INVALIDATED`;
5. if a new P_model is desired, start a **new market-blind run**.

Examples of material news:
- ruled-out primary creator;
- unexpected starting-center scratch;
- announced severe minutes restriction;
- major starting lineup reversal with material role redistribution.

A sportsbook price move alone is not basketball news and never invalidates P_model.

---

# 11. BET TRACKER CONTRACT

Tracker is bookkeeping only and never feeds P_model.

After completed Layer 4 create exactly one model run with:
- `sport=nba`;
- `league=nba`;
- `model_name=Nick NBA Assists + Rebounds`;
- `model_version=1.0`;
- exact league-date/event identity;
- original `frozen_at` and freeze receipt in notes/key assumptions;
- stable request ID derived from the frozen run.

Store evaluated/recommended selections using:
- `market_family=assists` or `rebounds`;
- `market_key=player_assists` or `player_rebounds`;
- `p_model=P_win`;
- push-aware fair-price math for integer lines;
- P_push, Confidence, Fragility and frozen receipts in notes/assumptions.

Do not create another tracker model run for API refresh or screenshot refresh.

`recordBet` occurs only after Nick explicitly confirms a real wager with exact selection, bookmaker, accepted odds and stake. Recommendation does not equal wager.

---

# 12. PRODUCTION ACCEPTANCE GATES

Do not label V1 production-ready until all gates actually pass:

1. corrected historical source acceptance;
2. deterministic rebuild;
3. independent Assists QBASE promotion;
4. independent Rebounds QBASE promotion;
5. repeated byte-identical challenge/artifact rebuild;
6. runtime assets committed and follow-up rebuild byte-identical;
7. all Python/JS CI green;
8. NBL isolation green;
9. Research Worker deployed with Durable Object and exact source commit;
10. Market Worker deployed with Durable Object + Research service binding;
11. required secrets/bindings configured without exposing values;
12. live future-slate Layer 0 fixture resolution;
13. complete server-enforced 1–2 game Layer 1 loop;
14. whole-slate Layer 2 freeze;
15. live real Odds API retrieval only after freeze;
16. exact event/player mapping and Layer 4 global ranking;
17. Tracker model-run creation after Layer 4;
18. post-freeze Bet365 screenshot refresh using same `run_id`, `frozen_at` and `freeze_receipt_sha256`;
19. proof that screenshot refresh performs no Layer 1 rerun and no P_model mutation;
20. no unresolved integrity/control failure.

Until those gates pass, the build remains a production candidate, not production-approved.
