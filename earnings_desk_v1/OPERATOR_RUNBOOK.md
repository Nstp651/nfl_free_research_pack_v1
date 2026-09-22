# Earnings Desk V1 — First Production Run

## Before the first morning

The first run must be `SHADOW`. Confirm all of the following:

- the remote migration is applied;
- `OPERATOR_TOKEN` is configured as a Worker secret;
- `/health` reports the Earnings Desk schema version;
- the historical earnings dataset has at least 20 usable broad events and at least 8 prior events overall before the research cutoff;
- the residual post-event-IV dataset has at least 8 usable observations and relevant moneyness/DTE cohorts;
- event timing comes from a reliable current source;
- no broker credentials are stored anywhere in the Worker or D1.

## Daily sequence: 05:00–07:00 Australia/Sydney

All protected calls use `Authorization: Bearer <operator token>`.

### 1. Settle open positions first

1. Call `GET /v1/earnings/positions/open`.
2. For every open position, capture a fresh IBKR screenshot containing the exact open contracts and executable bid/ask.
3. Submit it to `POST /v1/earnings/positions/{position_id}/settlement-guidance`.
4. Follow the returned SELL limits. The default is to close; do not extend the hold.
5. After the manual fills, submit the screenshot receipt plus exact fills and fees to `POST /v1/earnings/positions/{position_id}/settle`.

### 2. Create the authoritative run lock

Call `POST /v1/earnings/runs` with:

- `mode: SHADOW` for the first production run;
- the current US trading date;
- a research cutoff at the morning run start;
- the next morning exit timestamp;
- every candidate US-listed earnings event between those timestamps;
- AMC/BMO timing, timing source, verification time, sector, market-cap cohort, pre-event price, 20-day realised volatility, and weekly-option/liquidity flags.

Keep the returned `run_id` and `universe_sha256`. Ineligible rows remain logged but cannot be frozen.

### 3. Build and checkpoint market-blind research

For each eligible ticker, use the source hierarchy in order. Do not inspect today's option premiums, implied move, IV, Greeks, or option-derived probabilities.

Map evidence into all ten versioned features and cite at least one evidence ID for every feature. Submit to:

`POST /v1/earnings/runs/{run_id}/research/{ticker}`

If a critical field is missing or a material conflict cannot be resolved, submit `DATA_BLOCKED` or `PASS` with a concrete reason to:

`POST /v1/earnings/runs/{run_id}/disposition/{ticker}`

### 4. Freeze P_MODEL

For each completed research checkpoint call:

`POST /v1/earnings/runs/{run_id}/freeze/{ticker}`

Verify:

- `p_model_status = FROZEN`;
- `market_data = false`;
- the return grid contains 401 draws;
- all quantiles and tail probabilities are present;
- `freeze_receipt_sha256` is present.

Never repeat research to react to option prices. A material new company fact requires an explicitly new run/model rule, not an edited freeze.

### 5. Capture manual IBKR market input

Only after every eligible event is frozen or disposed:

1. Open the IBKR option chain.
2. Capture ticker, underlying, expiry, strikes, call bid/ask, put bid/ask, and visible IV/Greeks.
3. Hash the screenshot bytes with SHA-256.
4. Extract only visibly present fields into the market-input schema. Do not infer, interpolate, or fill blanks from web quotes.
5. Submit one screenshot payload per frozen ticker to `POST /v1/earnings/runs/{run_id}/market-inputs/{ticker}`.

If a required bid/ask is missing, capture a new screenshot or PASS. Do not repair the quote.

### 6. Value the whole run and select globally

Call `POST /v1/earnings/runs/{run_id}/value` once with a `market_input_ids` object mapping every frozen ticker to its accepted market-input ID.

The response ranks the entire slate and returns at most two CORE trade cards. It is valid for the response to contain no CORE positions.

### 7. Manual execution

For each CORE card only:

1. Enter the exact expiry/strike(s) and quantity shown.
2. Do not pay above `MAX ENTRY`.
3. Record exact fills and fees at `POST /v1/earnings/runs/{run_id}/positions`.
4. In SHADOW mode, record the hypothetical executable fill but place no broker order.

### 8. Outcome and calibration

After the exit horizon, record the equivalent-horizon underlying return at `POST /v1/earnings/runs/{run_id}/outcomes/{ticker}`.

After all positions are settled, close the run with operator minutes at `POST /v1/earnings/runs/{run_id}/close`.

Review `GET /v1/earnings/calibration`. Do not change model weights without a new version, backtest, and documented change note.
