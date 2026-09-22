import test from "node:test";
import assert from "node:assert/strict";
import { buildPModel } from "../src/pmodel.js";
import { findMarketContamination, validateResearchPack } from "../src/research.js";
import { FEATURE_CONTRACT_VERSION, RETURN_HORIZON_ID, RETURN_HORIZON_METHODOLOGY_VERSION } from "../src/config.js";
import { newYorkMarketCloseUtc } from "../src/market-time.js";

function history() {
  return Array.from({ length: 120 }, (_, index) => {
    const eventDate = `${2020 + Math.floor(index / 24)}-${String((index % 12) + 1).padStart(2, "0")}-15`;
    const exitDate = new Date(`${eventDate}T12:00:00Z`);
    exitDate.setUTCDate(exitDate.getUTCDate() + 1);
    const exitDateText = exitDate.toISOString().slice(0, 10);
    return {
      ticker: index % 12 === 0 ? "ACME" : `T${index}`,
      event_date: eventDate,
      event_timing: "AMC",
      sector: index % 3 === 0 ? "Technology" : "Industrials",
      market_cap_cohort: index % 2 === 0 ? "LARGE" : "MID",
      pre_event_price_timestamp: newYorkMarketCloseUtc(eventDate),
      exit_price_timestamp: newYorkMarketCloseUtc(exitDateText),
      return_horizon_id: RETURN_HORIZON_ID,
      return_horizon_methodology_version: RETURN_HORIZON_METHODOLOGY_VERSION,
      event_return: ((index % 17) - 8) / 100
    };
  });
}

function research() {
  const featureInputs = {
    eps_revision_z: { current_consensus: 1.08, prior_consensus: 1, historical_revision_mean: 0, historical_revision_std: 0.1 },
    revenue_revision_z: { current_consensus: 104, prior_consensus: 100, historical_revision_mean: 0, historical_revision_std: 0.1 },
    guidance_trajectory: { comparable_numeric_guidance_available: false, anchor: "MODEST_RAISE", rationale: "Company raised the low end of official guidance." },
    consensus_dispersion_z: { analyst_estimates: [98, 102], historical_dispersion_mean: 0.0182842712474619, historical_dispersion_std: 0.05 },
    peer_readthrough_z: { peer_events: [{ event_return: 0.03, relevance_weight: 1 }], historical_peer_return_mean: 0, historical_peer_return_std: 0.1 },
    pre_earnings_drift_z: { start_price: 100, pre_event_price: 102, benchmark_return: 0.03, historical_excess_return_mean: 0, historical_excess_return_std: 0.1 },
    sector_regime_z: { sector_start_price: 100, sector_end_price: 103, index_return: 0.01, historical_excess_return_mean: 0, historical_excess_return_std: 0.1 },
    index_regime_z: { index_start_price: 100, index_end_price: 101, historical_return_mean: 0, historical_return_std: 0.1 },
    company_specific_z: { anchor: "MODEST_POSITIVE_CONFIRMED", rationale: "Official filing confirms a modest operating improvement." },
    surprise_reaction_beta_z: { historical_surprises: [-0.2, -0.1, 0.1, 0.2], historical_event_returns: [-0.01, -0.005, 0.005, 0.01], historical_beta_mean: 0.025, historical_beta_std: 0.1 }
  };
  const evidence = [
    { evidence_id: "consensus-1", source_type: "CONSENSUS_AND_REVISIONS", url: "https://example.test/consensus", title: "Consensus history", fact: "Timestamped estimates and revisions.", retrieved_at: "2026-09-21T20:00:00Z" },
    { evidence_id: "guidance-1", source_type: "COMPANY_GUIDANCE", url: "https://example.test/guidance", title: "Company guidance", fact: "Company raised the low end of guidance.", retrieved_at: "2026-09-21T20:00:00Z" },
    { evidence_id: "peer-1", source_type: "PEER_READTHROUGH", url: "https://example.test/peer", title: "Peer result", fact: "Relevant peer event return.", retrieved_at: "2026-09-21T20:00:00Z" },
    { evidence_id: "market-1", source_type: "MARKET_OR_SECTOR_REGIME", url: "https://example.test/market", title: "Cash equity history", fact: "Underlying, sector, and index closes.", retrieved_at: "2026-09-21T20:00:00Z" },
    { evidence_id: "sec-1", source_type: "SEC_OR_OFFICIAL_FILING", url: "https://www.sec.gov/example", title: "Quarterly filing", fact: "Revenue trajectory improved.", published_at: "2026-09-20T00:00:00Z", retrieved_at: "2026-09-21T20:00:00Z" },
    { evidence_id: "history-1", source_type: "HISTORICAL_EARNINGS", url: "https://example.test/history", title: "Historical reactions", fact: "Audited surprise and reaction pairs.", retrieved_at: "2026-09-21T20:00:00Z" }
  ];
  return {
    market_data: false,
    ticker: "ACME",
    event_id: "evt_acme",
    evidence_quality: "HIGH",
    evidence,
    feature_contract_version: FEATURE_CONTRACT_VERSION,
    feature_inputs: featureInputs,
    feature_evidence: {
      eps_revision_z: ["consensus-1"], revenue_revision_z: ["consensus-1"], guidance_trajectory: ["guidance-1"], consensus_dispersion_z: ["consensus-1"],
      peer_readthrough_z: ["peer-1"], pre_earnings_drift_z: ["market-1"], sector_regime_z: ["market-1"], index_regime_z: ["market-1"],
      company_specific_z: ["sec-1"], surprise_reaction_beta_z: ["history-1"]
    },
    conflicts: []
  };
}

const event = {
  event_id: "evt_acme",
  ticker: "ACME",
  sector: "Technology",
  market_cap_cohort: "LARGE",
  realized_vol_20d: 0.025,
  report_at: "2026-09-22T20:05:00Z",
  intended_exit_at: "2026-09-23T20:30:00Z"
};

test("research contract blocks live option-derived inputs", () => {
  assert.deepEqual(findMarketContamination({ implied_move: 0.05 }), ["$.implied_move"]);
  assert.throws(() => validateResearchPack({ ...research(), analyst_note: "The option premium looks cheap." }, event, "2026-09-22T00:00:00Z"), /market-blind boundary/i);
});

test("feature contract derives deterministic scores and rejects caller-supplied scores", () => {
  const first = validateResearchPack(research(), event, "2026-09-22T00:00:00Z");
  const second = validateResearchPack(research(), event, "2026-09-22T00:00:00Z");
  assert.deepEqual(first.features, second.features);
  assert.deepEqual(first.features, {
    eps_revision_z: 0.8, revenue_revision_z: 0.4, guidance_trajectory: 1, consensus_dispersion_z: 0.2,
    peer_readthrough_z: 0.3, pre_earnings_drift_z: -0.1, sector_regime_z: 0.2, index_regime_z: 0.1,
    company_specific_z: 1, surprise_reaction_beta_z: 0.25
  });
  assert.throws(() => validateResearchPack({ ...research(), features: first.features }, event, "2026-09-22T00:00:00Z"), /server-derived/i);
});

test("feature contract calculates comparable numeric guidance and closes anchor choices", () => {
  const numeric = research();
  numeric.feature_inputs.guidance_trajectory = { comparable_numeric_guidance_available: true, prior_low: 95, prior_high: 105, current_low: 100, current_high: 106 };
  assert.equal(validateResearchPack(numeric, event, "2026-09-22T00:00:00Z").features.guidance_trajectory, 2);
  const invalid = research();
  invalid.feature_inputs.company_specific_z = { anchor: "SLIGHTLY_GOOD", rationale: "A deliberately invalid unversioned anchor." };
  assert.throws(() => validateResearchPack(invalid, event, "2026-09-22T00:00:00Z"), /anchor is not defined/i);
});

test("market-blind guard rejects alternative option-market wording", () => {
  const contaminated = [
    "The straddle costs five dollars.", "A cheap strangle is available.", "Options pricing implies a move.",
    "IV crush should be severe.", "The volatility skew is steep.", "The IV term structure is inverted.",
    "Open interest is concentrated.", "Gamma and vega are elevated.", "Option-derived probabilities favour upside."
  ];
  for (const analyst_note of contaminated) {
    assert.throws(() => validateResearchPack({ ...research(), analyst_note }, event, "2026-09-22T00:00:00Z"), /market-blind boundary/i, analyst_note);
  }
});

test("P_MODEL is deterministic, complete, and hierarchically pooled", () => {
  const validated = validateResearchPack(research(), event, "2026-09-22T00:00:00Z");
  const first = buildPModel({ event, research: validated, history: history(), researchCutoff: "2026-09-22T00:00:00Z" });
  const second = buildPModel({ event, research: validated, history: history(), researchCutoff: "2026-09-22T00:00:00Z" });
  assert.deepEqual(first, second);
  assert.equal(first.distribution_draws.length, 401);
  assert.ok(first.p_up > 0 && first.p_up < 1);
  assert.ok(first.p_down > 0 && first.p_down < 1);
  assert.ok(first.quantiles.p05 < first.quantiles.p50);
  assert.ok(first.quantiles.p50 < first.quantiles.p95);
  assert.ok(first.expected_abs_move > 0);
  assert.ok(first.tail_probabilities.P_ABS_GT_2_PCT >= first.tail_probabilities.P_ABS_GT_10_PCT);
  assert.ok(first.pooling.ticker_credibility < 1);
});

test("P_MODEL refuses an inadequate historical base", () => {
  assert.throws(() => buildPModel({ event, research: research(), history: history().slice(0, 5), researchCutoff: "2026-09-22T00:00:00Z" }), /historical dataset requires/i);
});

test("P_MODEL excludes history without exact approved horizon proof", () => {
  const validated = validateResearchPack(research(), event, "2026-09-22T00:00:00Z");
  const contaminatedHistory = history().map((row) => ({ ...row, exit_price_timestamp: row.exit_price_timestamp.replace("T20:00:00.000Z", "T19:00:00.000Z").replace("T21:00:00.000Z", "T20:00:00.000Z") }));
  assert.throws(() => buildPModel({ event, research: validated, history: contaminatedHistory, researchCutoff: "2026-09-22T00:00:00Z" }), /historical dataset requires/i);
});
