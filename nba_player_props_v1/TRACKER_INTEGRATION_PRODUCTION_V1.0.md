# NBA V1 — BET TRACKER INTEGRATION CONTRACT

NBA V1 reuses Nick's existing production Bet Tracker. No new tracker database or Worker is introduced.

Custom GPT Action schema: `tracker_openapi_v1.yaml`. It points to the existing `nick-betting-api` service and deliberately narrows the shared backend to NBA identity, Assists/Rebounds, Over selections and single-wager logging only.

## Preflight
Require tracker health before starting an operational run:
- `status=ok`;
- established production schema (currently `2.1.0` in the shared model workflow).

Tracker health is bookkeeping preflight and contains no sportsbook price input to P_model.

## Model identity
- `sport=nba`
- `league=nba`
- `model_name=Nick NBA Assists + Rebounds`
- `model_version=1.0`

The NBA Action schema rejects non-NBA identity. It does not broaden or alter the shared tracker backend.

## When to create a model run
After the **first completed Layer 4 ranking**:
- if one or more actionable positive-edge selections exist, call `createModelRun` exactly once with those actionable selections only;
- if Layer 4 returns `NO BET`, do **not** fabricate a tracker selection and do **not** create a tracker model run. Preserve/report the NO BET decision in the NBA run output instead.

Do not create a tracker model run:
- during Layer 1 research;
- during Layer 2 freeze;
- before market ranking;
- again for a later Odds API refresh;
- again for a Bet365/manual screenshot refresh;
- merely because odds changed.

A tracker write failure never changes P_model, frozen receipts or ranking.

## Stable identity / idempotency
`request_id` is mandatory for every tracker write.

For `createModelRun`, use a stable request ID derived from immutable NBA run identity, e.g. `run_id + freeze_receipt_sha256`. Reuse it only for an identical retry after uncertain/failed transport.

Preserve in the tracker run / notes / key assumptions:
- NBA `run_id`;
- ET league date;
- eligible fixture identity;
- original `frozen_at`;
- `freeze_receipt_sha256`;
- Assists QBASE model version / promotion receipt;
- Rebounds QBASE model version / promotion receipt;
- market snapshot receipt used for the initial Layer 4 ranking.

## Selection identity
For stored Assists selections:
- `market_family=assists`
- `market_key=player_assists`

For stored Rebounds selections:
- `market_family=rebounds`
- `market_key=player_rebounds`

The NBA Action schema permits `side=over` only. Alternate ladders use the same normalized tracker market key with the exact alternate threshold retained explicitly.

Every stored selection must include enough exact identity to be safely referenced later:
- selection/player identity;
- market family/key;
- Over side;
- exact integer/half threshold;
- `p_model=P_win`;
- push-aware fair odds;
- bookmaker and observed decimal price at initial integration;
- final positive-edge rank and final-play flag.

Also preserve, where supported by the shared tracker, exact game/event identity, edge/EV context, `P_push` for integer lines, categorical Confidence/Fragility, immutable freeze receipt and player/head hashes. Do not invent numeric confidence.

Retain every returned `model_selection_id` for later wager logging.

## Probability / fair-price mapping
### Half-point
`P_push=0`

- `p_model = P_win`
- `fair_odds = 1 / P_win`
- `p_market = 1 / observed_decimal_odds`
- `edge = P_win - p_market`

### Integer push line
`EV = P_win * (odds - 1) - P_loss`

Push-aware fair odds:

`fair_odds = (1 - P_push) / P_win`

Where the tracker requires a comparable market probability, use the established push-aware representation supported by the current tracker workflow and preserve raw `P_win/P_push/P_loss` in notes. Never treat a push as a loss or convert an integer line to a half-point line.

## Refreshes
Odds API and screenshot refreshes keep the same tracker model run and model selection identities. Do not recreate canonical model data because a bookmaker changed price.

If a refreshed best price belongs to the same frozen player/head/threshold, Layer 4 output may change while the tracker model run remains the original frozen model identity.

If the **initial** Layer 4 result was NO BET and a later post-freeze price refresh creates the first actionable positive edge, create the one tracker model run at that point using the same immutable freeze identity and that first actionable ranked market snapshot. Never backfill a fake initial selection.

## Wager logging
Call `recordBet` only after Nick explicitly confirms:
- exact stored selection;
- bookmaker;
- accepted decimal odds;
- stake.

The Action marks `recordBet` consequential. A new `request_id` is mandatory for each genuinely distinct accepted wager; reuse only for an identical uncertain/failed write retry.

Use the existing `model_selection_id`.
- `bet_type=single`
- exactly one leg.

The NBA Action rejects multi-leg/multi bet types even if the shared tracker backend supports them for other models.

Never log a recommendation as a wager. Never fabricate a selection ID. If no stored selection matches the confirmed wager, stop and surface the mismatch rather than creating an unrelated canonical model run.
