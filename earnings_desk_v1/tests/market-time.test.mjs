import test from "node:test";
import assert from "node:assert/strict";
import { isNewYorkRegularClose, newYorkMarketCloseUtc, validateHistoricalHorizon } from "../src/market-time.js";
import { RETURN_HORIZON_ID, RETURN_HORIZON_METHODOLOGY_VERSION } from "../src/config.js";

test("US market close converts through daylight-saving time", () => {
  assert.equal(newYorkMarketCloseUtc("2026-07-17"), "2026-07-17T20:00:00.000Z");
  assert.ok(isNewYorkRegularClose("2026-07-17T20:00:00Z"));
});

test("US market close converts through standard time", () => {
  assert.equal(newYorkMarketCloseUtc("2026-01-16"), "2026-01-16T21:00:00.000Z");
  assert.ok(isNewYorkRegularClose("2026-01-16T21:00:00Z"));
});

test("historical horizon rejects mismatched methodology and non-close timestamps", () => {
  const valid = {
    pre_event_price_timestamp: "2026-07-16T20:00:00Z",
    exit_price_timestamp: "2026-07-17T20:00:00Z",
    return_horizon_id: RETURN_HORIZON_ID,
    return_horizon_methodology_version: RETURN_HORIZON_METHODOLOGY_VERSION
  };
  assert.equal(validateHistoricalHorizon(valid, "2026-07-17", "BMO").return_horizon_id, RETURN_HORIZON_ID);
  assert.throws(() => validateHistoricalHorizon({ ...valid, return_horizon_id: "OTHER" }, "2026-07-17", "BMO"), /return_horizon_id/);
  assert.throws(() => validateHistoricalHorizon({ ...valid, exit_price_timestamp: "2026-07-17T19:00:00Z" }, "2026-07-17", "BMO"), /16:00 America\/New_York/);
});
