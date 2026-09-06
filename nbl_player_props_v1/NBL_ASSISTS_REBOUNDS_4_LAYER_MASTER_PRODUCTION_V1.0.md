# NBL ASSISTS + REBOUNDS — 4-LAYER MASTER — PRODUCTION V1.0

## 1. PURPOSE
This is Nick's production methodology for one NBL matchup engine with two independent player-prop heads:
- ASSISTS
- REBOUNDS

The default run mode is `BOTH`: research the fixture once, then build and atomically freeze separate assists and rebounds P_models. `ASSISTS_ONLY` and `REBOUNDS_ONLY` are permitted when explicitly requested.

The objective is not to predict sportsbook lines. It is to estimate true player outcome distributions from market-blind basketball information, freeze them, and only then compare exact frozen probabilities with post-freeze prices.

No bet is mandatory. A correct final result may be NO BET.

---

# LAYER 0 — FIXTURE + DATA LOCK

## 0.1 Exact fixture resolution
Resolve the requested NBL fixture through the Research/Freeze Gateway. Use exact `fixture_id`, teams, season start year and start time. Never model a fixture that has already started.

Start one persistent match run. Preserve:
- `run_id`
- `fixture_id`
- `run_mode`
- `source_commit`
- `asset_revision` / `pack_revision`
- `snapshot_revision`
- assists QBASE revision
- rebounds QBASE revision
- `eligibility_at`

The Worker pins one immutable GitHub main commit and verifies canonical hashes for the QBASE artifacts and historical prior snapshot.

## 0.2 Market boundary
Layers 0–2 are strictly market blind.

Forbidden before freeze:
- sportsbook pages or screenshots
- The Odds API prices/lines
- bookmaker odds or alternate ladders
- consensus betting markets
- tip sites or betting projections derived from market prices
- any attempt to infer the target line and tune P_model toward it

A market-like field entering the research/QBASE/freeze payload is an integrity failure.

## 0.3 Structured priors
The free structured spine supplies:
- official NBL/Genius fixture and roster identity
- historical NBL player/team game data
- immutable temporal QBASE artifacts
- next-game historical player/team prior snapshot

These are priors, not current-role truth.

---

# LAYER 1 — CURRENT RESEARCH PACK

Layer 1 is the most important edge-generation layer, especially early in the NBL season. Research must rebuild the current basketball state rather than mechanically carry last season forward.

## 1.1 Source hierarchy
Prefer, in order:
1. official NBL / club announcements, injury reports, rosters, previews and game reports;
2. credible current beat reporting, coach/player interviews and established basketball media;
3. official preseason/Blitz box scores, rotations and reports;
4. credible prior-competition statistics and official league/player records for imports/new arrivals;
5. other reputable basketball reporting only when primary evidence is unavailable.

Do not use betting-tip sites as basketball evidence.

Every material finding must have a source receipt with HTTPS URL, title and `checked_at`, then be referenced by source ID in the player/fixture research record.

## 1.2 Mandatory fixture research
Determine and record:
- fixture status and venue;
- home/away identity;
- rest days and travel burden;
- schedule compression / back-to-back effects;
- current team availability picture;
- expected starting groups and rotation shape;
- coaching or system changes;
- pace/environment expectation based on basketball evidence only;
- preseason/Blitz deployment when current-season sample is thin;
- credible late news.

## 1.3 Mandatory player research
For every player considered modelable, determine:
- exact identity/team;
- ACTIVE / PROBABLE / QUESTIONABLE / DOUBTFUL / OUT / UNKNOWN;
- projected minutes low / mean / high;
- starter likelihood where material;
- current rotation position;
- role state: RETURNING_SAME, RETURNING_CHANGED, NEW_TO_TEAM, NEW_TO_NBL, ROOKIE or UNKNOWN;
- creation role: PRIMARY, SECONDARY, CONNECTOR, OFF_BALL, LOW or UNKNOWN;
- frontcourt role: PRIMARY_BIG, SECOND_BIG, SMALL_BALL_BIG, WING, GUARD or UNKNOWN;
- teammates who compete for the same minutes or statistical opportunities;
- lineup dependencies and role fragility.

OUT players must not be frozen as modeled selections.

## 1.4 Early-season role translation
Opening weeks are a deliberate edge regime. Heavily research:
- import turnover;
- transfers and new signings;
- departed high-usage players;
- vacated minutes and creation/rebound share;
- new coaches and offensive systems;
- preseason starting groups;
- actual Blitz minutes and role;
- young-player role expansion;
- injuries that create temporary opportunity;
- returning players whose current role materially differs from last year.

Prior-season NBL production is a statistical prior only. Current expected role and minutes must be rebuilt.

## 1.5 New-to-NBL / imports
For a player without sufficient NBL history, research the most relevant competitive evidence from roughly the previous 12–18 months where possible:
- NBA / G League
- NCAA
- EuroLeague / EuroCup
- domestic European leagues
- B.LEAGUE / Asian leagues
- FIBA competition
- Summer League
- NZ NBL / NBL1
- other credible professional leagues

Capture:
- minutes and starting role;
- assists/rebounds per minute and role-adjusted production;
- usage / creation responsibility;
- AST%, turnover profile or passing role when available;
- ORB/DRB/TRB profile when available;
- team quality and competition context;
- likely NBL minutes and role.

There is NO universal fixed league-to-NBL multiplier. Translation must be evidence-based. New-to-NBL uncertainty must be represented through lower confidence/higher fragility and wider dispersion, not hidden by false precision.

## 1.6 ASSISTS-specific research
Focus on pathways that can change assist opportunity:
- primary vs secondary initiator status;
- on-ball possessions / touches / potential assists where credible data exists;
- pick-and-roll and half-court initiation responsibility;
- teammate shot conversion and spacing;
- competing ball-handlers;
- lineup-specific creation share;
- pace and possession expectation;
- opponent pressure, turnover forcing and validated assist environment;
- injury/absence effects on initiation responsibility.

Do not double count correlated evidence. Example: a lead guard injury may create both more minutes and more initiation; record the separate mechanisms but avoid applying the same role change twice.

## 1.7 REBOUNDS-specific research
Focus on pathways that can change rebound opportunity:
- frontcourt minutes and position;
- small-ball vs two-big structures;
- ORB%, DRB%, TRB% and rebound share/chances where available;
- teammate rebound competition;
- expected opponent shot/miss environment;
- opponent offensive/defensive rebounding tendencies where validated;
- pace / possession count;
- foul risk / matchup size;
- lineup absences that change frontcourt responsibility.

## 1.8 Welo
Current-season Welo may be used as supporting team-strength evidence after Week 1 when supplied/available. Never use prior-season Welo as a substitute for current NBL team strength because roster turnover is high. Welo is supporting context, not a direct player-prop probability override.

## 1.9 Research checkpoint
Checkpoint the completed market-blind research context before Layer 2. The checkpoint must bind to the exact fixture, pack revision and run mode. Preserve the `research_context_sha256`.

---

# LAYER 2 — P_MODEL + ATOMIC FREEZE

## 2.1 Separate stat heads
ASSISTS and REBOUNDS remain mathematically independent. Sharing research/minutes does not mean sharing a probability distribution.

## 2.2 Returning-player QBASE authority
The Worker owns the returning-player historical QBASE calculation.

For returning players:
- `QBASE_RUNTIME_SCORE` means are computed by the Worker;
- `QBASE_MINUTES_RECOMPUTE` means are recomputed by the Worker from the requested minutes scenario;
- client-supplied means for these methods may only match the Worker result; the Worker supplies the quantitative receipt;
- the historical baseline is not allowed to drift because of narrative preference.

This preserves the statistical anchor while allowing Layer 1 to translate current role/minutes through explicit scenarios.

## 2.3 Context scenarios
Scenarios describe materially different current states, not arbitrary optimism/pessimism.

Permitted methods:
- `QBASE_RUNTIME_SCORE`
- `QBASE_MINUTES_RECOMPUTE`
- `EMPIRICAL_ROLE_SPLIT`
- `PRIOR_COMP_TRANSLATION`

Every scenario requires:
- unique scenario ID;
- positive weight;
- evidence source IDs;
- explicit assumptions;
- quantitative receipt when required by the runtime.

Scenario weights must sum to exactly 1.0.

Use the smallest scenario set that represents the real uncertainty. Do not create scenarios merely to spread the distribution.

## 2.4 Empirical role split
`EMPIRICAL_ROLE_SPLIT` is allowed only when current evidence supports a genuine role state not adequately represented by minutes alone—for example, a returning guard shifting from secondary to primary creator.

Its mean must be derived from defensible basketball evidence/calculation and carry a quantitative receipt. Do not use this method as a free-form manual adjustment.

## 2.5 Prior-comp translation
If the Worker reports `PRIOR_COMP_TRANSLATION_REQUIRED`, all scenarios for that head must use `PRIOR_COMP_TRANSLATION`.

The translated means must be supported by the Layer 1 prior-competition research. The head must use an explicit `MAX_QBASE_PRIOR_COMP` dispersion override that can widen but never narrow the QBASE temporal-OOS dispersion.

## 2.6 Confidence and fragility
Confidence grades:
- A: strong role/minutes evidence, stable identity and robust historical support;
- B: good evidence with meaningful but manageable uncertainty;
- C: thin/translated/uncertain evidence.

Fragility:
- LOW: distribution should be relatively stable to plausible late information;
- MEDIUM: one or more material role/minutes dependencies;
- HIGH: imports, uncertain rotation, injury-dependent role, thin sample, or major scenario uncertainty.

Confidence/Fragility describe model reliability; they do not change because a sportsbook price is attractive.

## 2.7 Distribution
Each head freezes:
- final weighted mean;
- QBASE temporal-OOS dispersion, or permitted widened prior-comp dispersion;
- full count distribution;
- at-least ladder probabilities;
- half-point over/under grid;
- integer over/push/under grid.

Integer lines require exact push probability. Never treat an integer prop like a half-point prop.

## 2.8 Atomic freeze
In BOTH mode every modeled player must contain both requested heads. If either requested head fails integrity, the matchup does not partially freeze.

A successful freeze must return:
- `status: FROZEN`
- `market_data: false`
- exact fixture/run identity
- original `frozen_at`
- `research_context_sha256`
- QBASE hashes
- immutable `freeze_receipt_sha256`
- per-player `player_model_sha256`
- PASS audits for market boundary, research binding, server QBASE authority, scenario weighting, probability grid and atomic requested heads.

Repeated compute calls after freeze must return the original immutable freeze.

---

# LAYER 3 — POST-FREEZE MARKET INTEGRATION

No market source may be accessed until Layer 2 reports FROZEN.

## 3.1 Accepted market sources
Post-freeze observations may come from:
- The Odds API if actual NBL assists/rebounds markets are returned;
- user sportsbook screenshots, including Bet365;
- clean public-web sportsbook prices that are directly accessible without bypassing authentication or anti-bot controls.

The market source is optional. The P_model does not depend on it.

## 3.2 Canonical market record
Normalize each observed market to:
- fixture ID
- player ID when known
- player name
- stat type
- over/under side
- exact threshold
- decimal price
- bookmaker
- capture timestamp
- source type

Screenshot capture/ingestion time must be at or after `frozen_at`. Pre-freeze market observations are invalid even if submitted later.

## 3.3 Freeze binding
The Market Gateway must verify:
- run status is FROZEN;
- exact caller `freeze_receipt_sha256` matches;
- fixture matches;
- fetched full player model has the same frozen timestamp and receipt;
- full player payload hash equals the compact frozen `player_model_sha256`.

## 3.4 Best price merge
After resolving all records to the exact frozen player identity, retain the highest valid price for each exact:
`player + stat + side + threshold`.

This allows a name-only Bet365 screenshot to compete correctly with an ID-bearing Odds API record.

## 3.5 Exact threshold mapping
Only evaluate thresholds that exist exactly in the frozen probability grid. No interpolation, extrapolation or nearest-line substitution.

For half points:
`EV = P(win) * (decimal_price - 1) - P(loss)`

For integer lines the same formula is used with explicit push probability; push returns stake. Conditional non-push win probability and fair price may be reported, but EV must remain push-aware.

---

# LAYER 4 — RANKING + DECISION

## 4.1 Positive-edge ranking
Rank by expected value, with Confidence and Fragility as reliability/tie-break context rather than a reason to manufacture an edge.

For BOTH mode report:
1. BEST SINGLE across assists + rebounds;
2. ranked assists positive edges;
3. ranked rebounds positive edges;
4. combined positive-edge ranking.

If no market is positive EV, output NO BET.

## 4.2 No mutation after market
Once market access occurs, no frozen mean, scenario, minutes assumption, probability, confidence or fragility may be changed.

If material basketball information appears after freeze—injury, scratch, starter/rotation change, minutes restriction, major role news—invalidate the run and start a new market-blind run. Do not reprice the existing frozen model in response to the sportsbook.

## 4.3 Bet tracking
Model ranking is not placement. Record a bet in Nick's tracker only after Nick explicitly confirms the bet/book/price/stake was placed.

---

# PRODUCTION PRINCIPLES
- Research creates the edge; the market only prices the frozen view.
- Current role beats stale prior role, especially early season.
- Historical data anchors rather than dictates.
- Server QBASE prevents narrative drift for returning players.
- Imports/new players carry explicit translation uncertainty.
- Assists and rebounds remain separate statistical heads.
- Exact identity, hashes and timestamps are integrity requirements.
- Do not force action.
