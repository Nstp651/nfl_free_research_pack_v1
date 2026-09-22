# K&J Earnings Desk V1

Production-oriented earnings-event research, probability, option valuation, execution-recording, settlement, and calibration engine for the existing `kj-event-desk` Worker.

## Status

Code and the additive D1 migration are complete and locally verified. The live Cloudflare account already contains the `kj-event-desk` Worker, `kj-event-desk` D1 database, and `DB` binding.

Deployment remains gated by an operator secret and historical data readiness. Do not weaken those gates to make a first run pass.

## Implemented scope

- EARN-DIRECTION: long call and long put.
- EARN-MOVE: long ATM straddle and long strangle.
- Deterministic hierarchical P_MODEL and uncertainty grid.
- Immutable P_MODEL freeze with cryptographic receipt.
- Manual IBKR screenshot extraction contract and exact-quote validation.
- Post-event IV hierarchy and next-morning option simulation.
- Run-level CORE/WATCH/PASS ranking with a two-CORE cap.
- One-contract manual execution records.
- Exact bid-based settlement guidance and realised P&L.
- JSON calibration dashboard.
- Existing M&A event endpoints retained.

## Verification

From the repository root:

```bash
npm install
npm --prefix earnings_desk_v1 test
npx wrangler deploy --dry-run --config earnings_desk_v1/wrangler.jsonc
npx wrangler d1 migrations apply DB --local --config earnings_desk_v1/wrangler.jsonc
```

## Production installation

1. Review and merge the Earnings Desk change.
2. Create a strong operator token interactively; never put it in source or shell history:

   ```bash
   npx wrangler secret put OPERATOR_TOKEN --config earnings_desk_v1/wrangler.jsonc
   ```

3. Export or bookmark the current D1 database for recovery.
4. Apply the additive migration:

   ```bash
   npx wrangler d1 migrations apply DB --remote --config earnings_desk_v1/wrangler.jsonc
   ```

5. Dry-run, then deploy:

   ```bash
   npx wrangler deploy --dry-run --config earnings_desk_v1/wrangler.jsonc
   npx wrangler deploy --config earnings_desk_v1/wrangler.jsonc
   ```

6. Confirm `/health` retains the M&A fields and shows `earningsDesk.schema = earnings_desk_schema_v1.0.0`.
7. Confirm `/v1/events?status=active` still returns the existing M&A response.
8. Load approved historical earnings events and post-event IV observations. The model intentionally returns `DATA BLOCKED / PASS` below its minimum sample sizes.
9. Complete at least one end-to-end SHADOW run before changing `EARNINGS_DESK_MODE` to `LIVE`.

See [OPERATOR_RUNBOOK.md](OPERATOR_RUNBOOK.md) for the daily sequence and [ARCHITECTURE.md](ARCHITECTURE.md) for model details.
