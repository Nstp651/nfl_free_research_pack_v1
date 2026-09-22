import test from "node:test";
import assert from "node:assert/strict";
import { ingestHistory } from "../src/run-service.js";
import { RETURN_HORIZON_ID, RETURN_HORIZON_METHODOLOGY_VERSION } from "../src/config.js";

function recordingDb() {
  const state = { statements: [] };
  return {
    state,
    prepare(sql) {
      return {
        bind(...bindings) {
          return { sql, bindings };
        }
      };
    },
    async batch(statements) {
      state.statements = statements;
      return statements.map(() => ({ success: true }));
    }
  };
}

function batchInput(overrides = {}) {
  return {
    source_name: "audited-close-data",
    source_revision: "revision-2026-01",
    source_url: "https://example.test/history/manifest",
    as_of: "2026-02-01T00:00:00Z",
    events: [{
      ticker: "ACME",
      event_date: "2026-01-16",
      event_version: 1,
      event_timing: "BMO",
      sector: "Technology",
      market_cap_cohort: "LARGE",
      pre_event_price: 100,
      pre_event_price_timestamp: "2026-01-15T21:00:00Z",
      pre_event_price_source_url: "https://example.test/prices/pre",
      exit_price: 105,
      exit_price_timestamp: "2026-01-16T21:00:00Z",
      exit_price_source_url: "https://example.test/prices/exit",
      return_horizon_id: RETURN_HORIZON_ID,
      return_horizon_methodology_version: RETURN_HORIZON_METHODOLOGY_VERSION,
      ...overrides
    }]
  };
}

test("history ingestion persists timestamped horizon proof and provenance", async () => {
  const db = recordingDb();
  await ingestHistory(db, batchInput(), new Date("2026-02-01T01:00:00Z"));
  const bindings = db.state.statements[1].bindings;
  assert.equal(bindings[9], "2026-01-15T21:00:00.000Z");
  assert.equal(bindings[10], "https://example.test/prices/pre");
  assert.equal(bindings[12], "2026-01-16T21:00:00.000Z");
  assert.equal(bindings[13], "https://example.test/prices/exit");
  assert.equal(bindings[14], RETURN_HORIZON_ID);
  assert.equal(bindings[15], RETURN_HORIZON_METHODOLOGY_VERSION);
  assert.ok(Math.abs(bindings[16] - 0.05) < 1e-12);
});

test("history ingestion rejects returns not produced by timestamped prices", async () => {
  const db = recordingDb();
  await assert.rejects(() => ingestHistory(db, batchInput({ event_return: 0.04 })), /does not match timestamped prices/i);
});

test("history ingestion rejects a non-approved horizon", async () => {
  const db = recordingDb();
  await assert.rejects(() => ingestHistory(db, batchInput({ return_horizon_id: "UNAPPROVED" })), /return_horizon_id/i);
});
