# NCAA Totals V1 — Launch Prompt

```text
NEW NCAA FOOTBALL TOTALS MODEL RUN — V1.0

Season: <YEAR>
Target Week: <WEEK>
Australia/Sydney Run Window: <DATE OR WINDOW>
Timing Mode: <EARLY / MATCHDAY>

Run the complete NCAA Football Totals V1.0 workflow automatically across the eligible FBS-v-FBS slate.

1. Validate the full intended slate and exclude already-started/completed games.
2. Complete the research/market-gateway preflights without accessing sportsbook prices.
3. Retrieve the complete market-blind NCAA research slate at one revision and the aligned QBASE artifact/slate outputs at one QBASE revision.
4. Complete the required current-information scan for every eligible game and targeted deep research for triggered uncertainty.
5. Execute Layer 2 numerically, including all contextual scenario calculations, the full pre-market half-point probability grid, hashes and integrity audits.
6. Freeze the ENTIRE eligible slate only after all numerical/model-integrity checks pass.
7. Only after P_MODEL_STATUS: FROZEN, retrieve the current Australian NCAA full-game totals board at one market revision.
8. Verify every matched fixture and exact frozen line mapping, then run Layers 3/4 and rank the best positive-edge single totals across the slate.

Do not use sportsbook totals, spreads, prices, consensus or betting previews in Layers 0-2. Do not interpolate or create new probabilities after market access. Do not force a bet.

Complete the workflow without pausing for screenshots, CSVs or manual odds when Actions succeed. If a transient Action failure occurs, follow the V1 retry rules exactly; never invent missing data or prices.
```

## Pre-market dry-run variant

Append:

```text
PRE-MARKET DRY RUN ONLY: stop immediately after the successful full-slate P_model freeze. Do not call the NCAA totals market board, do not run Layers 3/4 and do not claim final ranking completion.
```

## Price-refresh variant

```text
NCAA TOTALS MARKET REFRESH

Use the existing frozen P_model and original freeze timestamp from this run. Do not perform new research and do not change any frozen probability, expected total, residual distribution, contextual assumption, Confidence or Fragility.

Call the NCAA totals market board once for the frozen slate window, verify the board/fixtures, then rerun Layers 3/4 only using exact frozen line mappings. If material new football information is discovered, invalidate the affected model instead of refreshing prices against a stale football state.
```