import { canonicalJson, finiteNumber, isoTimestamp, parseJsonColumn, randomId, requireThat, round, sha256Hex } from "./canonical.js";
import { appendDecision, fetchEvent, fetchFreeze, fetchRun } from "./repository.js";

export async function recordExecution(db, runId, input, riskConfig, now = new Date()) {
  const valuationId = String(input.valuation_id ?? "");
  const row = await db.prepare(`SELECT v.*, b.event_id, b.run_id
    FROM earnings_valuations v
    JOIN earnings_valuation_batches b ON b.valuation_batch_id = v.valuation_batch_id
    WHERE v.valuation_id = ? AND b.run_id = ? LIMIT 1`).bind(valuationId, runId).first();
  requireThat(row, "valuation not found", "NOT_FOUND");
  requireThat(row.selection === "CORE", "only CORE selections can be recorded as positions");
  const run = await fetchRun(db, runId);
  const valuation = parseJsonColumn(row.valuation_json);
  requireThat(Array.isArray(input.leg_fills) && input.leg_fills.length === valuation.legs.length, "one entry fill per option leg is required");
  const fills = input.leg_fills.map((fill, index) => {
    const expected = valuation.legs[index];
    requireThat(String(fill.contract_key) === expected.contract_key, `entry leg ${index} contract mismatch`);
    const price = finiteNumber(fill.fill_price, `entry leg ${index} fill_price`);
    requireThat(price > 0 && price <= valuation.max_entry, `entry leg ${index} fill exceeds allowed maximum`);
    return { ...expected, fill_price: price };
  });
  const entryFillTotal = fills.reduce((sum, fill) => sum + fill.fill_price, 0);
  requireThat(entryFillTotal <= valuation.max_entry + 1e-9, "combined entry fill exceeds MAX ENTRY");
  const quantity = Math.trunc(Number(input.quantity ?? 1));
  requireThat(quantity === 1, "v1 execution supports one contract per leg");
  const entryFees = input.entry_fees === undefined
    ? fills.length * riskConfig.commission_per_contract_usd
    : finiteNumber(input.entry_fees, "entry_fees");
  requireThat(entryFees >= 0, "entry_fees invalid");
  const maxCapital = entryFillTotal * riskConfig.contract_multiplier * quantity + entryFees;
  requireThat(maxCapital <= riskConfig.max_capital_per_trade_usd, "executed position exceeds per-trade capital limit");
  const positionId = randomId("position");
  const openedAt = isoTimestamp(input.opened_at ?? now.toISOString(), "opened_at");
  const statements = [db.prepare(`INSERT INTO earnings_positions
    (position_id, run_id, event_id, valuation_id, mode, status, quantity, opened_at, entry_fill_total,
     entry_fees, max_capital_at_risk, execution_notes)
    VALUES (?, ?, ?, ?, ?, 'OPEN', ?, ?, ?, ?, ?, ?)`)
    .bind(positionId, runId, row.event_id, valuationId, run.mode, quantity, openedAt, entryFillTotal, entryFees, maxCapital, String(input.execution_notes ?? "").trim() || null)];
  for (const fill of fills) {
    statements.push(db.prepare(`INSERT INTO earnings_position_legs
      (position_leg_id, position_id, contract_key, expiry, strike, right_type, entry_fill, quantity)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?)`)
      .bind(randomId("leg"), positionId, fill.contract_key, fill.expiry, fill.strike, fill.right, fill.fill_price, quantity));
  }
  const record = { position_id: positionId, valuation_id: valuationId, mode: run.mode, quantity, opened_at: openedAt, entry_fill_total: round(entryFillTotal, 4), entry_fees: round(entryFees, 2), max_capital_at_risk: round(maxCapital, 2) };
  const recordJson = canonicalJson(record);
  statements.push(db.prepare(`INSERT INTO earnings_decision_records
    (decision_id, run_id, event_id, record_type, record_json, record_sha256, created_at)
    VALUES (?, ?, ?, 'MANUAL_EXECUTION', ?, ?, ?)`)
    .bind(randomId("decision"), runId, row.event_id, recordJson, await sha256Hex(record), now.toISOString()));
  await db.batch(statements);
  return record;
}

async function positionWithLegs(db, positionId) {
  const position = await db.prepare(`SELECT p.*, e.ticker, e.report_at, e.intended_exit_at
    FROM earnings_positions p JOIN earnings_events e ON e.event_id = p.event_id
    WHERE p.position_id = ? LIMIT 1`).bind(positionId).first();
  requireThat(position, "position not found", "NOT_FOUND");
  const legs = await db.prepare("SELECT * FROM earnings_position_legs WHERE position_id = ? ORDER BY contract_key").bind(positionId).all();
  return { position, legs: legs.results ?? [] };
}

export async function settlementGuidance(db, positionId, input, riskConfig, now = new Date()) {
  const { position, legs } = await positionWithLegs(db, positionId);
  requireThat(position.status === "OPEN", "position is not open");
  requireThat(input.source_type === "IBKR_SCREENSHOT", "settlement source must be IBKR_SCREENSHOT");
  requireThat(/^[a-f0-9]{64}$/.test(String(input.screenshot_sha256 ?? "")), "settlement screenshot_sha256 required");
  const capturedAt = isoTimestamp(input.captured_at, "settlement captured_at");
  const ageMinutes = (now.getTime() - Date.parse(capturedAt)) / 60_000;
  requireThat(ageMinutes >= -2 && ageMinutes <= riskConfig.market_input_max_age_minutes, "settlement quote is stale", "DATA_BLOCKED");
  requireThat(Array.isArray(input.quotes) && input.quotes.length === legs.length, "all position legs require fresh settlement quotes");
  const byKey = new Map(input.quotes.map((quote) => [String(quote.contract_key), quote]));
  const sellLegs = legs.map((leg) => {
    const quote = byKey.get(leg.contract_key);
    requireThat(quote, `missing settlement quote for ${leg.contract_key}`, "DATA_BLOCKED");
    const bid = finiteNumber(quote.bid, `${leg.contract_key} bid`);
    const ask = finiteNumber(quote.ask, `${leg.contract_key} ask`);
    requireThat(bid >= 0 && ask >= bid, `invalid settlement quote for ${leg.contract_key}`);
    return { contract_key: leg.contract_key, action: "SELL", quantity: leg.quantity, limit: round(bid, 2), bid: round(bid, 4), ask: round(ask, 4) };
  });
  const executableBidTotal = sellLegs.reduce((sum, leg) => sum + leg.bid, 0);
  const guidance = {
    position_id: positionId,
    ticker: position.ticker,
    captured_at: capturedAt,
    screenshot_sha256: String(input.screenshot_sha256),
    sell_legs: sellLegs,
    combo_sell_limit: round(executableBidTotal, 2),
    instruction: "SELL TO CLOSE AT CURRENT EXECUTABLE BID; DO NOT EXTEND HOLD"
  };
  await appendDecision(db, { decisionId: randomId("decision"), runId: position.run_id, eventId: position.event_id, recordType: "SETTLEMENT_GUIDANCE", record: guidance, createdAt: now.toISOString() });
  return guidance;
}

export async function settlePosition(db, positionId, input, riskConfig, now = new Date()) {
  const { position, legs } = await positionWithLegs(db, positionId);
  requireThat(position.status === "OPEN", "position is not open");
  const guidance = await settlementGuidance(db, positionId, input, riskConfig, now);
  requireThat(Array.isArray(input.actual_fills) && input.actual_fills.length === legs.length, "actual exit fill required for every leg");
  const fillMap = new Map(input.actual_fills.map((fill) => [String(fill.contract_key), fill]));
  const actualExitFillTotal = legs.reduce((sum, leg) => {
    const fill = fillMap.get(leg.contract_key);
    requireThat(fill, `missing actual exit fill for ${leg.contract_key}`);
    const price = finiteNumber(fill.fill_price, `${leg.contract_key} exit fill`);
    requireThat(price >= 0, `${leg.contract_key} exit fill invalid`);
    return sum + price;
  }, 0);
  const exitFees = input.exit_fees === undefined
    ? legs.length * riskConfig.commission_per_contract_usd
    : finiteNumber(input.exit_fees, "exit_fees");
  requireThat(exitFees >= 0, "exit_fees invalid");
  const multiplier = riskConfig.contract_multiplier * position.quantity;
  const slippage = (guidance.combo_sell_limit - actualExitFillTotal) * multiplier;
  const realizedPnl = (actualExitFillTotal - position.entry_fill_total) * multiplier - position.entry_fees - exitFees;
  const settlementId = randomId("settlement");
  const settledAt = isoTimestamp(input.settled_at ?? now.toISOString(), "settled_at");
  const settlement = {
    settlement_id: settlementId,
    position_id: positionId,
    sell_limit_guidance: guidance,
    actual_exit_fill_total: round(actualExitFillTotal, 4),
    exit_fees: round(exitFees, 2),
    slippage_dollars: round(slippage, 2),
    realized_pnl: round(realizedPnl, 2),
    settled_at: settledAt
  };
  await db.batch([
    db.prepare(`INSERT INTO earnings_settlements
      (settlement_id, position_id, screenshot_sha256, captured_at, guidance_json, executable_bid_total,
       actual_exit_fill_total, exit_fees, slippage_dollars, realized_pnl, settled_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
      .bind(settlementId, positionId, input.screenshot_sha256, guidance.captured_at, canonicalJson(guidance), guidance.combo_sell_limit, actualExitFillTotal, exitFees, slippage, realizedPnl, settledAt),
    db.prepare("UPDATE earnings_positions SET status = 'CLOSED', closed_at = ? WHERE position_id = ? AND status = 'OPEN'").bind(settledAt, positionId),
    db.prepare(`INSERT INTO earnings_decision_records
      (decision_id, run_id, event_id, record_type, record_json, record_sha256, created_at)
      VALUES (?, ?, ?, 'SETTLEMENT', ?, ?, ?)`)
      .bind(randomId("decision"), position.run_id, position.event_id, canonicalJson(settlement), await sha256Hex(settlement), settledAt)
  ]);
  return settlement;
}

export async function listOpenPositions(db) {
  const result = await db.prepare(`SELECT p.position_id, p.run_id, p.event_id, p.mode, p.quantity, p.opened_at,
    p.entry_fill_total, p.entry_fees, p.max_capital_at_risk, e.ticker, e.report_at, e.intended_exit_at,
    v.trade_type, v.p_profit, v.expected_net_dollars, v.confidence
    FROM earnings_positions p
    JOIN earnings_events e ON e.event_id = p.event_id
    JOIN earnings_valuations v ON v.valuation_id = p.valuation_id
    WHERE p.status = 'OPEN' ORDER BY e.intended_exit_at, e.ticker`).all();
  return result.results ?? [];
}

export async function recordOutcome(db, runId, eventKey, input, now = new Date()) {
  const event = await fetchEvent(db, runId, eventKey);
  const freezeRow = await fetchFreeze(db, runId, event.event_id);
  const actualReturn = finiteNumber(input.actual_underlying_return, "actual_underlying_return");
  const draws = freezeRow.freeze.return_distribution.distribution_draws;
  const percentile = draws.filter((draw) => draw <= actualReturn).length / draws.length;
  const outcomeId = randomId("outcome");
  const recordedAt = now.toISOString();
  await db.prepare(`INSERT INTO earnings_model_outcomes
    (outcome_id, run_id, event_id, freeze_id, actual_underlying_return, actual_absolute_move,
     actual_gap_open_return, forecast_percentile, observed_post_event_iv, recorded_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
    .bind(outcomeId, runId, event.event_id, freezeRow.freeze_id, actualReturn, Math.abs(actualReturn), input.actual_gap_open_return ?? null, percentile, input.observed_post_event_iv ?? null, recordedAt)
    .run();
  const record = { outcome_id: outcomeId, ticker: event.ticker, actual_underlying_return: round(actualReturn), actual_absolute_move: round(Math.abs(actualReturn)), forecast_percentile: round(percentile), observed_post_event_iv: input.observed_post_event_iv ?? null };
  await appendDecision(db, { decisionId: randomId("decision"), runId, eventId: event.event_id, recordType: "MODEL_OUTCOME", record, createdAt: recordedAt });
  return record;
}

export async function closeRun(db, runId, operatorMinutes, now = new Date()) {
  const run = await fetchRun(db, runId);
  requireThat(run.status === "VALUED", "only a VALUED run can be closed");
  const open = await db.prepare("SELECT COUNT(*) AS count FROM earnings_positions WHERE run_id = ? AND status = 'OPEN'").bind(runId).first();
  requireThat(Number(open.count) === 0, "run has open positions");
  const minutes = finiteNumber(operatorMinutes, "operator_minutes");
  requireThat(minutes > 0 && minutes <= 600, "operator_minutes invalid");
  const closedAt = now.toISOString();
  await db.prepare("UPDATE earnings_runs SET status = 'CLOSED', operator_minutes = ?, updated_at = ? WHERE run_id = ?").bind(minutes, closedAt, runId).run();
  return { run_id: runId, status: "CLOSED", operator_minutes: minutes, closed_at: closedAt };
}
