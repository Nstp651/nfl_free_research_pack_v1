import assert from "node:assert/strict";
import { FEATURE_CONTRACT_VERSION, RETURN_HORIZON_ID, RETURN_HORIZON_METHODOLOGY_VERSION } from "../src/config.js";
import { newYorkMarketCloseUtc } from "../src/market-time.js";

const base = process.env.EARNINGS_ACCEPTANCE_BASE ?? "http://127.0.0.1:8791";
const token = process.env.EARNINGS_ACCEPTANCE_TOKEN ?? "local-acceptance-token-1234567890";
const headers = { authorization: `Bearer ${token}`, "content-type": "application/json" };

async function api(path, options = {}) {
  const response = await fetch(`${base}${path}`, { ...options, headers: { ...headers, ...(options.headers ?? {}) } });
  const data = await response.json();
  assert.ok(response.ok, `${path} failed ${response.status}: ${JSON.stringify(data)}`);
  return data;
}

const started = new Date();
const suffix = String(started.getTime());
const cutoff = new Date(started.getTime() - 60_000).toISOString();
const reportAt = new Date(started.getTime() + 4 * 3_600_000).toISOString();
const exitAt = new Date(started.getTime() + 18 * 3_600_000).toISOString();
const expiry = new Date(started.getTime() + 4 * 86_400_000).toISOString().slice(0, 10);

const health = await api("/health", { headers: {} });
assert.equal(health.service, "kj-event-desk");
assert.equal(health.earningsDesk.version, "1.1.0");

function shiftDate(dateText, days) {
  const date = new Date(`${dateText}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

const historical = Array.from({ length: 120 }, (_, index) => {
  const eventDate = new Date(Date.UTC(2014, 0, 1) + index * 28 * 86_400_000).toISOString().slice(0, 10);
  const eventReturn = ((index % 19) - 9) / 100;
  const eventTiming = index % 2 ? "AMC" : "BMO";
  const preDate = eventTiming === "AMC" ? eventDate : shiftDate(eventDate, -1);
  const exitDate = eventTiming === "AMC" ? shiftDate(eventDate, 1) : eventDate;
  return {
    ticker: index % 12 === 0 ? "ACME" : `Z${String(index).padStart(3, "0")}`,
    event_date: eventDate,
    event_version: 1,
    event_timing: eventTiming,
    sector: index % 3 ? "Industrials" : "Technology",
    market_cap_cohort: index % 2 ? "MID" : "LARGE",
    pre_event_price: 100,
    pre_event_price_timestamp: newYorkMarketCloseUtc(preDate),
    pre_event_price_source_url: "https://example.test/history/pre-close",
    exit_price: 100 * (1 + eventReturn),
    exit_price_timestamp: newYorkMarketCloseUtc(exitDate),
    exit_price_source_url: "https://example.test/history/post-close",
    return_horizon_id: RETURN_HORIZON_ID,
    return_horizon_methodology_version: RETURN_HORIZON_METHODOLOGY_VERSION,
    realized_vol_20d: 0.025,
    pre_event_drift: 0.01,
    estimate_revision_z: 0.1,
    consensus_dispersion_z: 0.2
  };
});
await api("/v1/earnings/history/batches", { method: "POST", body: JSON.stringify({ source_name: "local-acceptance", source_revision: suffix, source_url: "https://example.test/history", as_of: cutoff, events: historical }) });

const observations = Array.from({ length: 40 }, (_, index) => ({
  ticker: index < 12 ? "ACME" : `Z${index}`,
  event_date: new Date(Date.UTC(2018, 0, 1) + index * 35 * 86_400_000).toISOString().slice(0, 10),
  sector: "Technology",
  market_cap_cohort: "LARGE",
  moneyness_bucket: index % 2 ? "ATM_2PCT" : "OTM_2_7",
  dte_bucket: "3_7",
  residual_iv: 0.35 + (index % 6) * 0.02,
  exit_spread_fraction: 0.08 + (index % 3) * 0.01
}));
await api("/v1/earnings/iv-observations", { method: "POST", body: JSON.stringify({ source: "local-acceptance", source_revision: suffix, observations }) });

const eventId = `evt_accept_${suffix}`;
const run = await api("/v1/earnings/runs", { method: "POST", body: JSON.stringify({
  mode: "SHADOW",
  us_trading_date: started.toISOString().slice(0, 10),
  research_cutoff: cutoff,
  intended_exit_at: exitAt,
  events: [{
    event_id: eventId,
    ticker: "ACME",
    company_name: "Acceptance Corp",
    sector: "Technology",
    market_cap_cohort: "LARGE",
    report_at: reportAt,
    event_timing: "AMC",
    timing_source_url: "https://example.test/timing",
    timing_verified_at: cutoff,
    timing_reliability: "HIGH",
    realized_vol_20d: 0.025,
    pre_event_price: 100,
    liquid_us_listing: true,
    weekly_options_available: true
  }]
}) });
assert.equal(run.eligible_count, 1);

const featureInputs = {
  eps_revision_z: { current_consensus: 1.07, prior_consensus: 1, historical_revision_mean: 0, historical_revision_std: 0.1 },
  revenue_revision_z: { current_consensus: 105, prior_consensus: 100, historical_revision_mean: 0, historical_revision_std: 0.1 },
  guidance_trajectory: { comparable_numeric_guidance_available: false, anchor: "MODEST_RAISE", rationale: "Official guidance raised the low end modestly." },
  consensus_dispersion_z: { analyst_estimates: [98, 102], historical_dispersion_mean: 0.0182842712474619, historical_dispersion_std: 0.05 },
  peer_readthrough_z: { peer_events: [{ event_return: 0.04, relevance_weight: 1 }], historical_peer_return_mean: 0, historical_peer_return_std: 0.1 },
  pre_earnings_drift_z: { start_price: 100, pre_event_price: 102, benchmark_return: 0.01, historical_excess_return_mean: 0, historical_excess_return_std: 0.1 },
  sector_regime_z: { sector_start_price: 100, sector_end_price: 103, index_return: 0.01, historical_excess_return_mean: 0, historical_excess_return_std: 0.1 },
  index_regime_z: { index_start_price: 100, index_end_price: 101, historical_return_mean: 0, historical_return_std: 0.1 },
  company_specific_z: { anchor: "MODEST_POSITIVE_CONFIRMED", rationale: "Official filing confirms modest operating improvement." },
  surprise_reaction_beta_z: { historical_surprises: [-0.2, -0.1, 0.1, 0.2], historical_event_returns: [-0.012, -0.006, 0.006, 0.012], historical_beta_mean: 0.03, historical_beta_std: 0.1 }
};
const researchEvidence = [
  { evidence_id: "consensus-1", source_type: "CONSENSUS_AND_REVISIONS", url: "https://example.test/consensus", title: "Consensus", fact: "Timestamped consensus history.", retrieved_at: cutoff },
  { evidence_id: "guidance-1", source_type: "COMPANY_GUIDANCE", url: "https://example.test/guidance", title: "Guidance", fact: "Official guidance trajectory.", retrieved_at: cutoff },
  { evidence_id: "peer-1", source_type: "PEER_READTHROUGH", url: "https://example.test/peer", title: "Peer", fact: "Relevant peer event reaction.", retrieved_at: cutoff },
  { evidence_id: "market-1", source_type: "MARKET_OR_SECTOR_REGIME", url: "https://example.test/market", title: "Cash market", fact: "Underlying, sector, and index close history.", retrieved_at: cutoff },
  { evidence_id: "official-1", source_type: "SEC_OR_OFFICIAL_FILING", url: "https://www.sec.gov/example", title: "Official filing", fact: "Acceptance-only verified operating evidence.", published_at: cutoff, retrieved_at: cutoff },
  { evidence_id: "history-1", source_type: "HISTORICAL_EARNINGS", url: "https://example.test/reactions", title: "Historical reactions", fact: "Audited surprise and return pairs.", retrieved_at: cutoff }
];
await api(`/v1/earnings/runs/${run.run_id}/research/ACME`, { method: "POST", body: JSON.stringify({
  market_data: false,
  ticker: "ACME",
  event_id: eventId,
  evidence_quality: "HIGH",
  evidence: researchEvidence,
  feature_contract_version: FEATURE_CONTRACT_VERSION,
  feature_inputs: featureInputs,
  feature_evidence: {
    eps_revision_z: ["consensus-1"], revenue_revision_z: ["consensus-1"], guidance_trajectory: ["guidance-1"], consensus_dispersion_z: ["consensus-1"],
    peer_readthrough_z: ["peer-1"], pre_earnings_drift_z: ["market-1"], sector_regime_z: ["market-1"], index_regime_z: ["market-1"],
    company_specific_z: ["official-1"], surprise_reaction_beta_z: ["history-1"]
  },
  conflicts: []
}) });

const freeze = await api(`/v1/earnings/runs/${run.run_id}/freeze/ACME`, { method: "POST", body: "{}" });
assert.equal(freeze.p_model_status, "FROZEN");
assert.equal(freeze.return_distribution.distribution_draws.length, 401);

const market = await api(`/v1/earnings/runs/${run.run_id}/market-inputs/ACME`, { method: "POST", body: JSON.stringify({
  source_type: "IBKR_SCREENSHOT",
  run_id: run.run_id,
  ticker: "ACME",
  freeze_receipt_sha256: freeze.freeze_receipt_sha256,
  screenshot_sha256: "a".repeat(64),
  captured_at: new Date().toISOString(),
  underlying_price: 100,
  quotes: [
    { expiry, strike: 95, right: "PUT", bid: 0.04, ask: 0.05, iv: 0.8 },
    { expiry, strike: 100, right: "PUT", bid: 0.04, ask: 0.05, iv: 0.8 },
    { expiry, strike: 100, right: "CALL", bid: 0.04, ask: 0.05, iv: 0.8 },
    { expiry, strike: 105, right: "CALL", bid: 0.04, ask: 0.05, iv: 0.8 }
  ]
}) });

const valued = await api(`/v1/earnings/runs/${run.run_id}/value`, { method: "POST", body: JSON.stringify({ market_input_ids: { ACME: market.market_input_id } }) });
assert.ok(valued.core_count <= 2);
assert.ok(valued.trade_cards.length >= 1);
const core = valued.selections.find((row) => row.selection === "CORE");
assert.ok(core);

const position = await api(`/v1/earnings/runs/${run.run_id}/positions`, { method: "POST", body: JSON.stringify({
  valuation_id: core.valuation_id,
  quantity: 1,
  opened_at: new Date().toISOString(),
  leg_fills: core.legs.map((leg) => ({ contract_key: leg.contract_key, fill_price: leg.ask })),
  entry_fees: core.legs.length * 0.65,
  execution_notes: "Local SHADOW acceptance"
}) });

const settlementInput = {
  source_type: "IBKR_SCREENSHOT",
  screenshot_sha256: "b".repeat(64),
  captured_at: new Date().toISOString(),
  quotes: core.legs.map((leg) => ({ contract_key: leg.contract_key, bid: 0.8, ask: 0.82 })),
  actual_fills: core.legs.map((leg) => ({ contract_key: leg.contract_key, fill_price: 0.78 })),
  exit_fees: core.legs.length * 0.65,
  settled_at: new Date().toISOString()
};
const settlement = await api(`/v1/earnings/positions/${position.position_id}/settle`, { method: "POST", body: JSON.stringify(settlementInput) });
assert.ok(Number.isFinite(settlement.realized_pnl));

await api(`/v1/earnings/runs/${run.run_id}/outcomes/ACME`, { method: "POST", body: JSON.stringify({ actual_underlying_return: 0.045, actual_gap_open_return: 0.04, observed_post_event_iv: 0.41 }) });
await api(`/v1/earnings/runs/${run.run_id}/close`, { method: "POST", body: JSON.stringify({ operator_minutes: 45 }) });
const calibration = await api("/v1/earnings/calibration");
assert.ok(calibration.sample_sizes.distribution_events >= 1);
assert.ok(calibration.sample_sizes.completed_trades >= 1);

console.log(JSON.stringify({ acceptance: "PASS", run_id: run.run_id, freeze_receipt_sha256: freeze.freeze_receipt_sha256, core_count: valued.core_count, position_id: position.position_id, realized_pnl: settlement.realized_pnl }, null, 2));
