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
- H2H, totals and spreads are ranked together only after market-depth gates pass.

## Module layout

- `TENNIS_V1_SPEC.md` — M1 architecture, math, research, validation and market contract.
- `M2_SOURCE_AUDIT.md` — current zero-cost source/licensing audit and selected source stack.
- `M2_STATUS.md` — Milestone 2 implementation and acceptance status.
- `src/tennis_v1/data_sources.py` — unattended source adapters and market-column quarantine.
- `src/tennis_v1/data_pipeline.py` — normalized parquet pack, coverage and acceptance gates.
- `src/tennis_v1/ratings.py` — chronological internal overall/surface Elo and workload state.
- `scripts/build_data_pack.py` — historical rebuild/current refresh/zero-upload CLI.
- `src/tennis_v1/model.py` — serve/return matchup point-probability contract.
- `src/tennis_v1/simulator.py` — full match simulation and market probability extraction.
- `src/tennis_v1/freeze.py` — immutable pre-market freeze receipts.
- `src/tennis_v1/market.py` — post-freeze quote pricing.
- `src/tennis_v1/slate.py` — coverage gating and slate ranking.
- `src/tennis_v1/tracker.py` — immutable bet-log record schema.
- `tests/` — deterministic integrity tests.

## Milestone status

**M1: ACCEPTED FOUNDATION.**

**M2: BLOCKED — `ZERO_UPLOAD_TEST = FAIL_SERVE_STATS_GAP`.**

The zero-cost automated results layer is viable using Valuebetennis CC BY 4.0 open data, with all upstream market fields destroyed before persistence. Internal chronological Elo, surface Elo, workload and transition states are implemented.

The blocker is narrower and explicit: the audited free sources do not provide sufficiently deep and current ATP+WTA **match-level serve/return statistics** under rights that support an unattended private betting research pipeline. The only accepted free serve-stat source found is the CC BY 4.0 UCI 2013 majors dataset, which is far too stale and narrow for production state training or Tournament Pace Index.

The project will not use results-only scores as a substitute for separately identifiable serve and return strength, and will not reintroduce rejected non-commercial/scraped sources simply to make M2 green.

See `M2_SOURCE_AUDIT.md` and `M2_STATUS.md` for the exact gap and implemented pipeline.
