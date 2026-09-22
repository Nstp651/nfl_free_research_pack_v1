import test from "node:test";
import assert from "node:assert/strict";
import { createRun } from "../src/run-service.js";
import { assertLiveReadiness, LIVE_CALIBRATION_ACK, LIVE_CALIBRATION_STATUS, LIVE_RISK_ACK, riskConfigFromEnv } from "../src/risk-config.js";

test("placeholder capital values are SHADOW-only", async () => {
  const config = riskConfigFromEnv({ EARNINGS_DESK_MODE: "SHADOW", MAX_CAPITAL_PER_TRADE_USD: "750", MAX_DAILY_CAPITAL_USD: "1500" });
  assert.equal(config.production_risk_approved, false);
  await assert.rejects(() => createRun({}, { mode: "LIVE" }, config), /does not match configured/i);
});

test("LIVE readiness requires deliberate risk approval, calibration artifact, and observed samples", async () => {
  const env = {
    EARNINGS_DESK_MODE: "LIVE",
    EARNINGS_RISK_PROFILE_ID: "approved-risk-review-2026-09",
    EARNINGS_CAPITAL_LIMITS_STATUS: "APPROVED_FOR_LIVE",
    EARNINGS_PRODUCTION_RISK_ACK: LIVE_RISK_ACK,
    EARNINGS_CALIBRATION_ACK: LIVE_CALIBRATION_ACK,
    EARNINGS_MODEL_CALIBRATION_STATUS: LIVE_CALIBRATION_STATUS,
    EARNINGS_CALIBRATION_REPORT_SHA256: "a".repeat(64),
    LIVE_MIN_SHADOW_RUNS: "5",
    LIVE_MIN_SETTLED_SHADOW_TRADES: "10",
    LIVE_MIN_SHADOW_MODEL_OUTCOMES: "20",
    MAX_CAPITAL_PER_TRADE_USD: "800",
    MAX_DAILY_CAPITAL_USD: "1600"
  };
  const config = riskConfigFromEnv(env);
  const db = { prepare: () => ({ first: async () => ({ shadow_runs: 5, settled_shadow_trades: 10, shadow_model_outcomes: 20 }) }) };
  const result = await assertLiveReadiness(db, config);
  assert.equal(result.observed.shadow_model_outcomes, 20);
  const insufficient = { prepare: () => ({ first: async () => ({ shadow_runs: 4, settled_shadow_trades: 10, shadow_model_outcomes: 20 }) }) };
  await assert.rejects(() => assertLiveReadiness(insufficient, config), /insufficient closed SHADOW runs/i);
});
