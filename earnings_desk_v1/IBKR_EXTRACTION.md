# IBKR Screenshot Extraction Contract

Treat the screenshot as the only market authority. Return JSON only.

Required top-level fields:

- `source_type`: exactly `IBKR_SCREENSHOT`
- `run_id`
- `ticker`
- `freeze_receipt_sha256`
- `screenshot_sha256`
- `captured_at`
- `underlying_price`
- `quotes`

For each visibly complete contract row, extract:

- `expiry` (`YYYY-MM-DD`)
- `strike`
- `right` (`CALL` or `PUT`)
- `bid`
- `ask`
- `iv`, `delta`, `open_interest`, and `volume` only when visible; otherwise `null`

Never infer a missing bid or ask, use a midpoint as a bid/ask, copy a neighbouring strike, substitute a web quote, change the timestamp, or include an ambiguous contract. If no row is complete, return `DATA BLOCKED / PASS` instead of market JSON.
