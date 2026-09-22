# K&J Earnings Desk V1 — Architecture and Reuse Plan

## Outcome

Earnings Desk is a new namespaced engine inside the existing `kj-event-desk` Cloudflare Worker and D1 database. It preserves the live M&A API (`/health`, `/v1/events`, `/v1/events/{id}`), its scheduled no-op, and all existing D1 tables. New storage is additive and every table begins with `earnings_`.

## Reused platform contracts

The implementation carries forward the shared Betting Platform V1 controls:

- a content-addressed authoritative run lock;
- market-blind research and P_MODEL construction;
- evidence-bound structured features calculated under `earn-feature-contract-v1.1.0`;
- deterministic numerical execution with versioned coefficients;
- immutable server-side freeze and SHA-256 receipt;
- a hard server market gate after freeze;
- exact contract mapping with no interpolation;
- append-only decision records;
- SHADOW and LIVE modes through one pipeline;
- no forced trade.

The existing M&A read API and D1 database are reused. The sports systems' Durable Object implementation is not copied because Earnings Desk already has a D1 control plane and requires cross-event historical/calibration queries. D1 atomic batches, immutability triggers, and append-only receipts provide the equivalent lifecycle controls.

## Pipeline

`SETTLE -> RUN LOCK -> UNIVERSE -> RESEARCH CHECKPOINT -> P_MODEL -> FREEZE -> IBKR SCREENSHOT -> OPTION VALUE -> GLOBAL SELECTION -> MANUAL EXECUTION -> SETTLEMENT -> CALIBRATION`

Every eligible event must reach one of three terminal pre-market states before valuation: `FROZEN`, `DATA_BLOCKED`, or `PASS`. The run cannot value options until every event is resolved, preventing a partially researched slate from silently producing trades.

## P_MODEL V1

The model produces a complete next-exit-horizon stock-return distribution as 401 deterministic draws. Live option fields are rejected before research checkpointing and never enter P_MODEL. Research callers provide raw inputs, not feature scores; the Worker calculates eight quantitative features and maps the two judgment features through closed, evidence-gated anchors documented in [FEATURE_SCORING_CONTRACT.md](FEATURE_SCORING_CONTRACT.md).

The distribution combines:

1. broad earnings-event base rates;
2. sector and market-cap cohort base rates;
3. ticker history, shrunk toward the cohort with explicit credibility weights;
4. 20-day realised volatility and historical event volatility;
5. versioned mappings for revisions, guidance, consensus dispersion, peer read-through, drift, sector/index regime, company-specific evidence, and surprise/reaction sensitivity;
6. sparse-history, evidence-quality, and parameter uncertainty;
7. deterministic heavy-tail and skew transforms.

The existing feature weights and transforms are explicitly labelled `V1_PRIORS_NOT_EMPIRICALLY_TRAINED`. They are not claimed to be fitted coefficients. Replacing them requires a new model version and reproducible historical calibration/backtest.

## Historical horizon integrity

P_MODEL V1.1 accepts only `PRE_EVENT_CLOSE_TO_POST_EVENT_CLOSE_ET_V1` observations under methodology `earn-return-horizon-v1.0.0`. Each versioned row must store the pre-event and exit prices, their source URLs, and exact timestamps. Both timestamps must resolve to 16:00 `America/New_York`; the Worker handles EDT/EST conversion. AMC rows use the event-date close as the pre-event observation, while BMO rows use the event-date close as the exit observation. The event return is recalculated from those prices and any conflicting submitted value is rejected.

The freeze exposes P_UP, P_DOWN, expected and median returns, expected absolute move, P05/P10/P25/P50/P75/P90/P95, and absolute-move exceedance probabilities at 2%, 3%, 5%, 7.5%, and 10%.

## Option valuation

Only exact IBKR screenshot quotes are accepted. Every leg requires a bid and ask; missing prices are blocked. Entry uses the ask.

For each call, put, ATM straddle, and bounded-width strangle actually present in the screenshot:

- the frozen stock-return grid determines next-morning spot scenarios;
- Black-Scholes is used only to translate each scenario into remaining option value;
- residual post-event IV is hierarchically pooled by ticker, then sector/market-cap/moneyness/DTE, then broad history;
- five fixed residual-IV uncertainty nodes are integrated;
- remaining DTE, moneyness, commissions, regulatory fees, and pessimistic exit-spread slippage are included;
- option expiry is calculated as 16:00 `America/New_York`, with EDT/EST conversion rather than a fixed UTC hour;
- no current option price changes the frozen underlying distribution.

## Global selection

All frozen events are valued in one run-level call. Ranking is deterministic:

1. expected net dollars;
2. EV per dollar at risk;
3. P(profit);
4. model confidence;
5. spread quality.

Hard gates enforce freshness, verified timing, frozen P_MODEL, nonzero executable bids, spread limits, positive net EV, capital limits, and resolved research conflicts. At most two CORE positions can survive across the entire daily run.

## Storage and audit

`migrations/0001_earnings_desk_v1.sql` adds 20 namespaced tables plus the current-history view and 18 immutability triggers. It stores run locks, evidence, approved return-horizon definitions, versioned history, freezes, screenshot receipts, exact quotes, residual-IV observations, valuations, selections, positions, settlements, outcomes, decisions, and model versions.

The calibration endpoint reports direction Brier score, PIT distribution calibration, absolute-move error, P(profit) calibration, expected versus realised option P&L, cohort breakdowns, and profit per operator hour.

## Deliberate V1 boundaries

- no IBKR API or stored brokerage credentials;
- no automated orders;
- no continuous monitoring;
- no naked or short-premium structures;
- no market quote substitution;
- no generated historical observations;
- `$750` per trade and `$1,500` daily are explicitly SHADOW-only, non-production placeholders;
- no LIVE mode until deliberate risk values are approved, a backtest/calibration report hash is configured, and operator-chosen minimum SHADOW run/trade/outcome counts are actually satisfied.
