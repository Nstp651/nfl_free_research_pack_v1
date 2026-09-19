# NBL ASSISTS + REBOUNDS V1.1 — PLAYER-FIRST SELECTION ADDENDUM

Policy ID: `NBL_PLAYER_PROPS_PLAYER_FIRST_1.1`

Use this file with `NBL_ASSISTS_REBOUNDS_4_LAYER_MASTER_PRODUCTION_V1.0.md`.

This is a **selection-layer revision only**. It does not change Layer 1 research, QBASE, opening stabilization, prior-competition translation, server sanity, NB2 distributions, probability grids, atomic BOTH-head freeze, freeze receipts, or tracker identities.

Where this addendum conflicts with Layer 3/4 ranking language in the V1.0 master, **V1.1 wins**.

## 1. Market source

NBL player-prop market integration is **screenshot-only** for production V1.1.

After `P_MODEL_STATUS: FROZEN`, return `MARKET INPUT REQUIRED` until Nick supplies sportsbook screenshots.

Do not call Odds API for NBL assists/rebounds or alternate ladders. It is not part of the production V1.1 market workflow.

For post-freeze screenshots:
- extract every visible player, stat, side, exact threshold, bookmaker and decimal price;
- evaluate only exact frozen thresholds;
- no interpolation or nearest-line substitution;
- merge duplicate player/stat/threshold rows by best valid supplied price;
- use the message/upload observation time when an embedded capture time is unavailable, unless Nick or the screenshot indicates the price is old;
- do not reject an otherwise usable post-freeze screenshot solely because it lacks an embedded timestamp.

Production recommendation scope is **ASSISTS Overs + REBOUNDS Overs only**, including alternate ladders. Do not recommend unders.

## 2. Why V1.1 changes selection

The existing server market evaluator is mathematically useful but its `best_single` is selected from a raw EV-first list after hard reliability gates. That can let a long alternate threshold headline the run before a sensible core line is established.

V1.1 keeps server market evaluation as the source of exact frozen probability/EV math, but treats:
- server `best_single`,
- raw `positive_edges`,
- deterministic server grade

as **audit fields**, not the final recommendation selector.

The final selector is player/stat-first.

## 3. Candidate unit

Treat each `player + stat_type` as one candidate head.

Examples:
- Zylan Cheatham — ASSISTS
- Zylan Cheatham — REBOUNDS
- Nick Rakocevic — REBOUNDS

For each candidate head, choose at most one qualifying CORE anchor before comparing candidates.

## 4. Actionable edge bands

Use server `probability_edge`:

- PREMIUM: >= 7.0 percentage points
- STRONG: >= 4.0 and < 7.0 pp
- PLAYABLE: >= 2.0 and < 4.0 pp
- THIN POSITIVE: > 0 and < 2.0 pp
- NON-POSITIVE: <= 0

Positive EV remains mandatory.

For actionability probability use `conditional_win_probability`; for half-points this equals P_win. Tracker P_model remains the server P_win.

## 5. CORE anchor paths

### STANDARD CORE

All required:
- side OVER;
- current valid screenshot row;
- actionability probability >= 40%;
- probability edge >= 2.0 pp;
- EV per unit >= 5%;
- Confidence A or B;
- Fragility LOW or MEDIUM;
- threshold validation is DIRECT_VALIDATED, or TAIL_SUPPORTED with exact threshold marked supported for BEST SINGLE.

### SUPPORTED LOWER-HIT CORE

All required:
- side OVER;
- 30% <= actionability probability < 40%;
- probability edge >= 4.0 pp;
- EV per unit >= 10%;
- Confidence A;
- Fragility LOW;
- threshold validation DIRECT_VALIDATED.

### CANNOT LEAD

Any row with actionability probability < 30% can never be CORE and can never choose the player/stat, regardless of price or raw EV.

Confidence C, Fragility HIGH and EXTREME_TAIL rows cannot be CORE. They remain visible as WATCH/PASS when useful.

## 6. Deterministic candidate ranking

For each player/stat candidate choose its best qualifying CORE anchor.

Compare anchors by:

1. edge band: PREMIUM, STRONG, PLAYABLE;
2. STANDARD CORE before SUPPORTED LOWER-HIT CORE within the same band;
3. probability edge descending;
4. actionability probability descending;
5. DIRECT_VALIDATED before TAIL_SUPPORTED;
6. LOW before MEDIUM Fragility;
7. A before B Confidence;
8. EV per unit descending;
9. lower threshold;
10. stat type;
11. canonical player ID/name;
12. bookmaker.

The winning anchor is:
- `BEST NBL PROP`
- `CORE BET`

Raw EV rank, sportsbook payout size, number of positive alternates and player fame do not select the winner.

## 7. Same-player/stat ladder

Only after the CORE player/stat is selected, evaluate higher thresholds for that same player and same stat.

### OPTIONAL LADDER
- threshold > CORE threshold;
- actionability probability >= 20%;
- edge >= 2.0 pp;
- EV >= 5%;
- Confidence A/B;
- Fragility LOW/MEDIUM;
- DIRECT_VALIDATED or BEST-SINGLE-supported TAIL_SUPPORTED.

Choose at most one.

### OPTIONAL STRETCH
- threshold > CORE threshold;
- 12% <= actionability probability < 20%;
- edge >= 3.0 pp;
- EV >= 10%;
- Confidence A;
- Fragility LOW;
- DIRECT_VALIDATED or BEST-SINGLE-supported TAIL_SUPPORTED.

Choose at most one independently. A missing OPTIONAL LADDER does not block a qualifying STRETCH.

Actionability probability < 12% is TAIL-PASS for recommendation purposes.

Same-player thresholds are dependent singles. Do not multiply probabilities or present them as diversified exposure.

## 8. Output states

With a valid frozen run but no screenshot rows:
`MARKET INPUT REQUIRED — upload sportsbook screenshots.`

With malformed/unmappable screenshot rows:
`MARKET INPUT INCOMPLETE`

With a valid evaluated screenshot board but no qualifying CORE:
`NO BET — no qualifying actionable NBL core prop.`

Do not use NO BET for missing market input.

## 9. Output

Lead with one of:
- `BEST NBL PROP — [player] [stat]`
- `NO BET — no qualifying actionable NBL core prop`
- `MARKET INPUT REQUIRED`
- `MARKET INPUT INCOMPLETE`

For a bet show:
- CORE bet, bookmaker and odds;
- P_win, actionability probability, fair price, edge, EV, edge band and CORE path;
- concise frozen basketball thesis and main risk;
- selected player/stat ladder in threshold order;
- labels CORE, OPTIONAL LADDER, OPTIONAL STRETCH, ALTERNATIVE, WATCH/PASS;
- up to three serious alternative player/stat candidates and why they lost.

## 10. Freeze / tracker

Screenshot refresh reruns Layer 3–4 only. Never change frozen minutes, means, distributions, Confidence, Fragility, role assumptions or freeze receipt.

Tracker ranking must reflect the V1.1 recommendation order, not raw server EV rank. Never record an actual wager until Nick explicitly confirms exact bookmaker, odds and stake.
