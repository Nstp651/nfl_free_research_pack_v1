# Nick NCAA Football Totals Model — V1.1 Architecture

Status: PRODUCTION CANDIDATE. Authoritative betting methodology lives in `NCAA_TOTALS_4_LAYER_MASTER_API_ACTION_PRODUCTION_V1.1.md`; this document describes system architecture.

## Objective
Build a fully automated FBS-v-FBS full-game totals model that scales across an NCAA slate while preserving the same market-blind freeze discipline and auditability as the NFL production system.

`football evidence -> probability model -> ENTIRE SLATE FREEZE -> AU market -> exact mapping -> push-aware EV -> ranking`

## Scope
- FBS vs FBS only for V1 betting selection.
- Full-game totals only.
- Over and Under modelled objectively.
- Both integer and half-point totals supported.
- No H2H/spreads/team totals/periods/live/player props/multis.
- AU sportsbook data enters only after entire slate freeze.

## Layer 0 — slate validation
Validate season/week, canonical game ID, teams/home-away, UTC + Australia/Sydney kickoff, venue/neutral flag, season type and FBS-v-FBS eligibility. NEW runs exclude games already started/completed.

## Layer 1 — scalable research funnel
### 1A Structured data — every game
Research pack retains current and prior evidence separately, including where available:
- play volume / pace;
- EPA offense/defense and pass/rush splits;
- success rate;
- explosiveness;
- havoc;
- pass tendency;
- opponent-adjusted metrics;
- independent ratings;
- games/sample size;
- preseason talent / returning production when published.

### 1B Current-information scan — every game
Market-blind live research verifies QB, meaningful backup risk, material OL/skill/defensive absences, coaching/play-caller/system changes, transfers/depth-chart shifts, suspensions, venue/surface, weather/wind and unusual rest/travel.

### 1C Deep-research trigger — only where needed
Escalate QB uncertainty/change, new system, roster reset, low sample, current/prior conflict, important missing data, injury clusters, extreme weather, unusual pace/style, rating disagreement or high sensitivity.

This is the scale solution: structured work for 50+ games, lightweight current scan for all, expensive deep research only where it can materially change P_model.

## Anti-leakage contract
For target week W:

`current_season_data_through_week <= W-1`

Week 1 current performance is unavailable, not zero. Prior-season evidence is a statistical prior only; current personnel/system truth must be rebuilt.

No sportsbook line/price/consensus or betting-derived feature is allowed in Layers 0-2.

## QBASE
The selected market-blind baseline is Ridge QBASE V0.1.0.

Training receipt:
- 7,428 FBS-v-FBS games, 2016-2025;
- 5,152 temporal walk-forward scored games;
- OOS MAE 13.03, RMSE 16.45;
- Week 0/1 MAE 13.70;
- Weeks 2-4 MAE 13.24;
- Week 5+ MAE 12.88.

Nonlinear challengers did not improve OOS error and were not promoted.

QBASE supplies an expected-total anchor and temporal OOS residual distribution. It is not automatically final P_model; current football context can alter scenario mean/variance before freeze only when supported and ledgered.

## Layer 2 — final total distribution
For each fixture:
1. start from aligned QBASE;
2. translate current football context via the smallest justified scenario set;
3. use calibrated temporal OOS residual distribution;
4. compute final expected total / uncertainty;
5. freeze exact probabilities across a broad grid from 20.0 through 100.5 in 0.5 increments.

### Half-point line n+0.5
- Push = 0.
- Over/Under partition the outcome.

### Integer line n
Football final totals are integers, so whole-number markets need push probability:
- Under n ~= F(n-0.5)
- Push n ~= F(n+0.5)-F(n-0.5)
- Over n ~= 1-F(n+0.5)

Audits require probabilities in [0,1], Over monotonic down, Under monotonic up and Over+Push+Under=1 at every line. Half-point push must equal zero.

Actual numerical execution, hashes and audit receipts are mandatory. Only then:

`COMPLETE_MODEL_INTEGRITY_CONFIRMED`
`P_MODEL_STATUS: FROZEN`

The entire slate freezes together.

## Freeze contract
Frozen fields include fixture mapping, Information State, QB/personnel/weather/play-calling assumptions, QBASE version/revision, adjustment ledger, scenarios/weights, final mean/distribution, complete Over/Push/Under grid, Confidence and Fragility.

Price movement never changes P_model. Material post-freeze football information invalidates the run.

## Layer 3 — post-freeze market integration
The market Worker makes one NCAA sport-board request using:
- sport `americanfootball_ncaaf`
- region `au`
- market `totals`

GPT retrieves all pages at one immutable `board_revision` after freeze only. Fixture matching requires both teams + kickoff. Line mapping is exact; no post-market interpolation.

Duplicate identical side+line: highest decimal price, then newest `last_update`, then bookmaker key alphabetical.

### Push-aware market math
For offered side:
- P_win = frozen Over or Under probability
- P_push = frozen push
- P_loss = 1-P_win-P_push

Half-point:
- break-even = 1/odds
- Fair Price = 1/P_win
- ROI = P_win*odds-1

Integer:
- break-even win probability = (1-P_push)/odds
- Fair Price = (1-P_push)/P_win
- ROI = P_win*odds + P_push - 1

`model/market_math.py` executes these formulas. `model/integrate_market.py` provides deterministic exact mapping, best-price selection, freshness and ranking for a complete frozen artifact + complete post-freeze board snapshot.

## Layer 4 — ranking
Only exact-mapped positive push-aware ROI selections with acceptable freshness and intact freeze path are eligible. Rank primarily by ROI, Price Edge, Fragility, data/research quality, freshness and Confidence as tie-breaker. Never force a bet.

## Infrastructure
### GitHub
- source-controlled ETL/model/tests/schemas;
- scheduled research refresh;
- generated immutable research/QBASE artifacts;
- verification CI.

### Cloudflare native Git deployment
Research Worker:
- root `ncaaf_totals_v1`
- serves research + QBASE only.

Market Worker:
- root `ncaaf_totals_v1/market_worker`
- serves POST-FREEZE AU totals only;
- Odds API key remains an encrypted Cloudflare secret.

GitHub Actions do not deploy Workers; Cloudflare Git integration is the sole production deploy owner.

## Live acceptance state
Research and market-health Workers are live. Controlled AU board acceptance confirmed live NCAA totals from Sportsbet, TAB, TABtouch and PlayUp, with both integer and half-point lines present. Real-board acceptance is manual-only because it consumes Odds API quota.

## Governance
Predictive changes require temporal OOS evidence, not narrative preference. Continue tracking MAE/RMSE, threshold calibration/Brier/log loss, early-vs-late season performance and ablations. Betting ROI/CLV is assessed separately after frozen historical P_models are joined to as-of market snapshots.