# NFL RECEPTIONS V5.1.1 — ACTIONABLE PLAYER-FIRST SELECTION POLICY

Policy ID: `NFL_RECEPTIONS_PLAYER_FIRST_1.1`

This is a narrow selection-policy revision to V5.1.0. It does **not** change the V5 probability engine, research methodology, checkpoint, immutable freeze, market gateway, tracker identities, settlement, or supported market scope.

Use this file with `NFL_RECEPTIONS_V5.1.0_MASTER.md`. Where this policy conflicts with Part II selection cutoffs or ladder dependency in that master, **this V5.1.1 policy wins**. All other V5.1.0 requirements remain active.

## Why V5.1.1 exists

V5.0 could headline a very-low-probability tail because raw Expected ROI controlled the final answer. V5.1.0 correctly separated raw market ranking from the recommendation, but its universal 50% CORE hit-rate floor was too blunt and could convert a board containing credible actionable value into repeated NO BET results.

V5.1.1 keeps the player-first architecture and tail protection while moving closer to the AFL-style actionable-edge approach:

- true probability remains frozen before prices;
- raw `positive_edge_ranked` remains audit-only;
- role/evidence/reliability determine whether a player is trustworthy enough to lead;
- price edge determines whether the trustworthy player is actually playable;
- no composite score or market-driven probability adjustment is permitted;
- a smaller raw edge may outrank a larger one for explicit actionability reasons;
- speculative tails cannot select the player.

The thresholds below are transparent operating defaults, **not backtested optimums**. Freeze them for the run and monitor prospectively.

## 1. Player eligibility — unchanged

A player can lead only when every V5.1 player gate passes:

- position WR, TE or RB;
- `INCLUDE`;
- one of the first four approved receiver classes;
- role `STABLE` or `VERIFIED_EXPANSION`;
- usable receiving pathway;
- evidence score at least 11/16;
- Availability / Route Security = 2;
- Current Role = 2;
- Confidence HIGH or MEDIUM;
- player Fragility LOW or MODERATE;
- Research Quality Permission YES;
- no unresolved identity, availability or pathway contradiction.

Missing facts mean ineligible/UNKNOWN, never favorable inference.

## 2. Actionable edge bands

Use raw probability edge `P_model - 1/odds`:

- THIN POSITIVE: >0 to <2.0 percentage points
- PLAYABLE: 2.0 to <4.0 pp
- STRONG: 4.0 to <7.0 pp
- PREMIUM: 7.0 pp or higher

Positive edge alone does not make a row bet-worthy.

## 3. CORE anchor paths

Every player is reduced to at most one qualifying CORE anchor before players are compared.

### STANDARD CORE

All required:

- current valid quote;
- `P_model >= 30%`;
- probability edge >=2.0 pp;
- Expected ROI >=5%;
- threshold Fragility LOW/MODERATE, with player Fragility fallback allowed only when threshold Fragility is unavailable.

### SUPPORTED LOWER-HIT CORE

This allows a genuinely strong, well-supported price in the 20–30% hit-rate band without reopening the longshot problem.

All required:

- `20% <= P_model < 30%`;
- probability edge >=3.0 pp;
- Expected ROI >=10%;
- player Confidence HIGH;
- player Fragility LOW;
- explicit threshold Fragility LOW; no fallback;
- all normal player gates pass.

### TAIL — CANNOT LEAD

`P_model < 20%` can never be CORE and can never select the player, regardless of calculated ROI or offered odds.

## 4. Deterministic player-first ranking

For each eligible player, choose their best qualifying CORE anchor. Compare those player anchors by:

1. edge band: PREMIUM, STRONG, PLAYABLE;
2. within the same edge band, STANDARD CORE before SUPPORTED LOWER-HIT CORE;
3. raw probability edge descending;
4. P_model descending;
5. LOW before MODERATE threshold Fragility;
6. HIGH before MEDIUM player Confidence;
7. Expected ROI descending;
8. newest current quote;
9. lower reception threshold;
10. bookmaker key;
11. canonical player ID.

The winning anchor identifies `BEST RECEPTIONS PLAYER` and `CORE BET`.

Upper ladder rows, number of positive rows, raw ROI rank, player fame and position do not contribute to player selection.

## 5. Same-player ladder — independent rung evaluation

After the CORE player is selected, evaluate only that player's higher thresholds. **Do not require an intermediate rung to exist before a higher supported rung can qualify.**

### OPTIONAL LADDER

- k > CORE k;
- `P_model >= 20%`;
- edge >=2.0 pp;
- ROI >=5%;
- explicit threshold Fragility LOW/MODERATE.

Choose at most one OPTIONAL LADDER row by edge band, edge, P_model, reliability, ROI, freshness and deterministic tie-breaks.

### OPTIONAL STRETCH

- k > CORE k;
- `12% <= P_model < 20%`;
- edge >=3.0 pp;
- ROI >=10%;
- player Confidence HIGH;
- player Fragility LOW;
- explicit threshold Fragility LOW.

Choose at most one OPTIONAL STRETCH independently. A missing OPTIONAL LADDER does **not** block a qualifying STRETCH.

`P_model < 12%` is TAIL-PASS for recommendation purposes.

Maximum recommended singles from one run: CORE + one OPTIONAL LADDER + one OPTIONAL STRETCH. They remain nested, dependent singles; do not multiply probabilities or claim diversification/basket ROI.

Lower thresholds than CORE may be shown as ALTERNATIVES when independently valid, but are not extra recommendations by default.

## 6. Market integrity remains mandatory

Only CURRENT valid quotes (0–30 minutes) can create a new recommendation. Deduplicate exact player + threshold by highest current decimal price, then newest timestamp, standard before alternate, bookmaker key.

Missing complete-board coverage, missing required eligibility evidence, unavailable code execution, unresolved frozen-probability conflicts or incomplete retrieval are **SELECTION INPUT INCOMPLETE / MARKET COVERAGE INCOMPLETE**, not NO BET.

Only when all required inputs are complete and no CORE anchor qualifies may the model return:

`NO BET — no qualifying actionable core reception bet.`

## 7. Minimum acceptable price

For fixed P_model `p`, required probability edge `e` and ROI `r`:

`o_min = max(1/(p-e), (1+r)/p)` when `p > e`.

Use the requirements of the row's actual policy path. Round **up** to the next 0.01 and recheck at full precision.

Examples of path requirements:

- STANDARD CORE: e=0.02, r=0.05
- SUPPORTED LOWER-HIT CORE: e=0.03, r=0.10
- OPTIONAL LADDER: e=0.02, r=0.05
- OPTIONAL STRETCH: e=0.03, r=0.10

Minimum price never overrides role, reliability, freshness or identity gates.

## 8. Output

Lead with one of:

- `BEST RECEPTIONS PLAYER — [player]`
- `NO BET — no qualifying actionable core reception bet`
- the exact blocked/incomplete status.

For a BET show:

- CORE bet, book and odds;
- P_model, fair odds, edge, ROI, edge band and CORE path;
- concise football reason and main risk;
- selected player's useful ladder in threshold order;
- labels: CORE, OPTIONAL LADDER, OPTIONAL STRETCH, ALTERNATIVE, WATCH/PASS;
- minimum acceptable price for recommended/watch rows where useful;
- up to three serious alternative players and the exact reason they lost.

Do not dump raw positive-edge rows by default. Preserve the raw board and policy artifact for audit.

## 9. Tracker / freeze

No tracker schema change is authorized by this policy. Preserve the existing V5 run/freeze identities and V5.1 tracker compatibility rules. Recommended rows and raw positive-edge registry rows remain distinct states. Never record a wager without explicit user confirmation.

Market refreshes rerun selection only. They never modify frozen P_model, role, Confidence, Fragility, means, distributions or assumptions.
