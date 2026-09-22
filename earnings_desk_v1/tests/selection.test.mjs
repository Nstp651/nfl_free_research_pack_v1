import test from "node:test";
import assert from "node:assert/strict";
import { DEFAULT_RISK_CONFIG } from "../src/config.js";
import { selectCandidates, tradeCard } from "../src/selection.js";

function valuation(id, overrides = {}) {
  return {
    candidate_id: id,
    ticker: "ACME",
    event_time: "2026-09-22T20:00:00Z",
    intended_exit_at: "2026-09-23T11:00:00Z",
    trade_type: "CALL",
    expiry: "2026-09-25",
    strikes: [100],
    entry_ask: 2,
    max_entry: 2.5,
    entry_capital_usd: 200,
    expected_exit_value: 250,
    p_profit: 0.55,
    expected_net_dollars: 45,
    ev_per_dollar_risk: 0.20,
    max_loss: 201.5,
    model_edge: 0.20,
    confidence: "HIGH",
    liquidity: { adequate: true, combined_spread_fraction: 0.08 },
    ...overrides
  };
}

test("selection is EV-first and caps CORE at two", () => {
  const result = selectCandidates([
    valuation("third", { expected_net_dollars: 30 }),
    valuation("first", { expected_net_dollars: 70 }),
    valuation("second", { expected_net_dollars: 50 })
  ], DEFAULT_RISK_CONFIG);
  assert.deepEqual(result.selections.map((row) => row.candidate_id), ["first", "second", "third"]);
  assert.equal(result.core_count, 2);
  assert.deepEqual(result.selections.map((row) => row.selection), ["CORE", "CORE", "WATCH"]);
});

test("no forced trade and simple execution card", () => {
  const pass = selectCandidates([valuation("bad", { expected_net_dollars: -1, ev_per_dollar_risk: -0.01 })], DEFAULT_RISK_CONFIG);
  assert.equal(pass.no_forced_trade, true);
  assert.equal(pass.selections[0].selection, "PASS");
  assert.equal(tradeCard(pass.selections[0]), null);
  const core = selectCandidates([valuation("good")], DEFAULT_RISK_CONFIG).selections[0];
  const card = tradeCard(core);
  assert.equal(card.classification, "CORE — CALL");
  assert.equal(card.exit, "NEXT MORNING RUN");
  assert.equal(card.quantity, 1);
});
