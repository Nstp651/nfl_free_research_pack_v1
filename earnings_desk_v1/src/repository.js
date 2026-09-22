import { MODEL_CONFIG, MODEL_VERSION, IV_MODEL_VERSION, SELECTION_VERSION, VALUATION_VERSION } from "./config.js";
import { canonicalJson, parseJsonColumn, requireThat, sha256Hex } from "./canonical.js";

export async function seedModelVersions(db, now) {
  const versions = [
    [MODEL_VERSION, "P_MODEL", MODEL_CONFIG],
    [IV_MODEL_VERSION, "POST_EVENT_IV", { version: IV_MODEL_VERSION, hierarchy: ["ticker", "sector_market_cap_moneyness_dte", "broad"], uncertainty_nodes: [-2, -1, 0, 1, 2] }],
    [VALUATION_VERSION, "VALUATION", { version: VALUATION_VERSION, entry: "ASK", exit: "BLACK_SCHOLES_RESIDUAL_IV_WITH_EXECUTION_HAIRCUT", contract_multiplier: 100 }],
    [SELECTION_VERSION, "SELECTION", { version: SELECTION_VERSION, ranking: ["expected_net_dollars", "ev_per_dollar_risk", "p_profit", "confidence", "liquidity"], no_forced_trade: true }]
  ];
  const statements = [];
  for (const [version, kind, config] of versions) {
    const json = canonicalJson(config);
    statements.push(
      db.prepare(`INSERT OR IGNORE INTO earnings_model_versions
        (model_version, model_kind, config_json, config_sha256, created_at, active)
        VALUES (?, ?, ?, ?, ?, 1)`).bind(version, kind, json, await sha256Hex(json), now)
    );
  }
  await db.batch(statements);
}

export async function fetchRun(db, runId) {
  const run = await db.prepare("SELECT * FROM earnings_runs WHERE run_id = ? LIMIT 1").bind(runId).first();
  requireThat(run, "run not found", "NOT_FOUND");
  return run;
}

export async function fetchEvent(db, runId, eventIdOrTicker) {
  const key = String(eventIdOrTicker);
  const event = await db.prepare(`SELECT * FROM earnings_events
    WHERE run_id = ? AND (event_id = ? OR ticker = ?) LIMIT 1`).bind(runId, key, key.toUpperCase()).first();
  requireThat(event, "earnings event not found", "NOT_FOUND");
  return event;
}

export async function fetchResearch(db, runId, eventId) {
  const row = await db.prepare("SELECT * FROM earnings_research_packs WHERE run_id = ? AND event_id = ? LIMIT 1").bind(runId, eventId).first();
  requireThat(row, "research checkpoint not found", "DATA_BLOCKED");
  return { ...row, research: parseJsonColumn(row.research_json) };
}

export async function fetchFreeze(db, runId, eventId) {
  const row = await db.prepare("SELECT * FROM earnings_freezes WHERE run_id = ? AND event_id = ? LIMIT 1").bind(runId, eventId).first();
  requireThat(row, "P_MODEL is not frozen", "DATA_BLOCKED");
  return { ...row, freeze: parseJsonColumn(row.freeze_json) };
}

export async function appendDecision(db, { decisionId, runId, eventId = null, recordType, record, createdAt }) {
  const json = canonicalJson(record);
  const hash = await sha256Hex({ run_id: runId, event_id: eventId, record_type: recordType, record });
  await db.prepare(`INSERT INTO earnings_decision_records
    (decision_id, run_id, event_id, record_type, record_json, record_sha256, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?)`)
    .bind(decisionId, runId, eventId, recordType, json, hash, createdAt)
    .run();
  return hash;
}
