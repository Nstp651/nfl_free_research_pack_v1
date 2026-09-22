import test from "node:test";
import assert from "node:assert/strict";
import { DEFAULT_RISK_CONFIG } from "../src/config.js";
import { buildCandidates, validateMarketInput } from "../src/market-input.js";
import { blackScholes, valueCandidate } from "../src/option-pricing.js";

const event = { event_id: "evt_acme", ticker: "ACME", sector: "Technology", market_cap_cohort: "LARGE", report_at: "2026-09-22T20:00:00Z", intended_exit_at: "2026-09-23T11:00:00Z" };
const freeze = { run_id: "r".repeat(64), freeze_receipt_sha256: "f".repeat(64), frozen_at: "2026-09-22T00:00:00Z" };

function marketInput() {
  return {
    source_type: "IBKR_SCREENSHOT",
    run_id: freeze.run_id,
    ticker: "ACME",
    freeze_receipt_sha256: freeze.freeze_receipt_sha256,
    screenshot_sha256: "a".repeat(64),
    captured_at: "2026-09-22T01:00:00Z",
    underlying_price: 100,
    quotes: [
      { expiry: "2026-09-25", strike: 95, right: "PUT", bid: 1.8, ask: 2.0, iv: 0.75 },
      { expiry: "2026-09-25", strike: 100, right: "PUT", bid: 3.8, ask: 4.0, iv: 0.72 },
      { expiry: "2026-09-25", strike: 100, right: "CALL", bid: 3.7, ask: 4.0, iv: 0.73 },
      { expiry: "2026-09-25", strike: 105, right: "CALL", bid: 1.7, ask: 2.0, iv: 0.76 }
    ]
  };
}

test("manual IBKR input requires exact executable bid and ask", async () => {
  const missingAsk = marketInput();
  delete missingAsk.quotes[0].ask;
  await assert.rejects(() => validateMarketInput(missingAsk, event, freeze, DEFAULT_RISK_CONFIG, new Date("2026-09-22T01:05:00Z")), /ask must be finite/);
});

test("candidate builder creates calls, puts, straddles and strangles without interpolation", async () => {
  const normalized = await validateMarketInput(marketInput(), event, freeze, DEFAULT_RISK_CONFIG, new Date("2026-09-22T01:05:00Z"));
  const candidates = buildCandidates(normalized);
  assert.ok(candidates.some((candidate) => candidate.trade_type === "CALL"));
  assert.ok(candidates.some((candidate) => candidate.trade_type === "PUT"));
  assert.ok(candidates.some((candidate) => candidate.trade_type === "STRADDLE"));
  assert.ok(candidates.some((candidate) => candidate.trade_type === "STRANGLE"));
  assert.ok(candidates.every((candidate) => candidate.legs.every((leg) => normalized.quotes.includes(leg))));
});

test("Black-Scholes respects intrinsic value at expiry", () => {
  assert.equal(blackScholes({ right: "CALL", spot: 110, strike: 100, timeYears: 0, volatility: 0.5, riskFreeRate: 0.04 }), 10);
  assert.equal(blackScholes({ right: "PUT", spot: 90, strike: 100, timeYears: 0, volatility: 0.5, riskFreeRate: 0.04 }), 10);
});

test("actual candidate valuation uses ask and post-event IV uncertainty", async () => {
  const normalized = await validateMarketInput(marketInput(), event, freeze, DEFAULT_RISK_CONFIG, new Date("2026-09-22T01:05:00Z"));
  const candidate = buildCandidates(normalized).find((row) => row.trade_type === "STRADDLE");
  const pModel = { confidence: "HIGH", distribution_draws: Array.from({ length: 101 }, (_, index) => (index - 50) / 500) };
  const ivObservations = Array.from({ length: 30 }, (_, index) => ({ ticker: index < 12 ? "ACME" : `T${index}`, sector: "Technology", market_cap_cohort: "LARGE", moneyness_bucket: "ATM_2PCT", dte_bucket: "0_2", residual_iv: 0.35 + (index % 5) * 0.02, exit_spread_fraction: 0.08 + (index % 3) * 0.01 }));
  const value = valueCandidate({ candidate, marketInput: normalized, pModel, event, ivObservations, riskConfig: DEFAULT_RISK_CONFIG });
  assert.equal(value.entry_ask, 8);
  assert.equal(value.legs.length, 2);
  assert.ok(value.scenario_count > pModel.distribution_draws.length);
  assert.ok(value.expected_exit_value >= 0);
  assert.ok(value.p_profit >= 0 && value.p_profit <= 1);
  assert.equal(value.legs[0].post_event_iv_model.version, "post-event-iv-v1.0.0");
});
