# Tennis V1 — Serve/Return Match Simulator

Production-oriented, market-blind tennis pricing engine for K&J Betting Operations.

## Core principle

One pre-market joint match distribution prices all supported markets:

1. match winner (`h2h`)
2. total match games (`totals`)
3. game handicap (`spreads`)

No sportsbook data is permitted before `P_MODEL_STATUS: FROZEN`.

## V1 scope

- Singles only.
- ATP and WTA calibrated separately.
- Best-of-3 and best-of-5 explicit.
- Tournament-specific tiebreak rules explicit.
- The Odds API is the only sportsbook/price source.
- AU region is the default market region.
- H2H, totals and spreads are ranked together, but only after market-depth gates pass.

## Module layout

- `TENNIS_V1_SPEC.md` — full architecture, math, research, validation, market and acceptance contract.
- `SOURCE_AUDIT.md` — source licensing/production-use audit.
- `src/tennis_v1/model.py` — serve/return matchup point-probability contract.
- `src/tennis_v1/simulator.py` — full match simulation and market probability extraction.
- `src/tennis_v1/freeze.py` — immutable pre-market freeze receipts.
- `src/tennis_v1/market.py` — post-freeze quote pricing.
- `src/tennis_v1/slate.py` — coverage gating and slate ranking.
- `src/tennis_v1/tracker.py` — immutable bet-log record schema.
- `tests/` — deterministic integrity tests.

## Production status

**NOT PRODUCTION READY YET.** The code establishes the V1 probability, freeze and market contracts. Production promotion requires a licensed structured tennis data feed, chronological backtesting, calibration gates and live shadow runs described in `TENNIS_V1_SPEC.md`.

The project deliberately does **not** vendor or scrape Jeff Sackmann/Tennis Abstract, ATP/WTA website data, or Tennis-Data historical files because their published usage terms do not support this production betting workflow.
