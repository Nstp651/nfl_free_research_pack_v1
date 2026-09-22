import test from "node:test";
import assert from "node:assert/strict";
import { buildPModel } from "../src/pmodel.js";
import { findMarketContamination, validateResearchPack } from "../src/research.js";

function history() {
  return Array.from({ length: 120 }, (_, index) => ({
    ticker: index % 12 === 0 ? "ACME" : `T${index}`,
    event_date: `${2020 + Math.floor(index / 24)}-${String((index % 12) + 1).padStart(2, "0")}-15`,
    sector: index % 3 === 0 ? "Technology" : "Industrials",
    market_cap_cohort: index % 2 === 0 ? "LARGE" : "MID",
    event_return: ((index % 17) - 8) / 100
  }));
}

function research() {
  const features = {
    eps_revision_z: 0.8,
    revenue_revision_z: 0.4,
    guidance_trajectory: 1,
    consensus_dispersion_z: 0.2,
    peer_readthrough_z: 0.3,
    pre_earnings_drift_z: -0.1,
    sector_regime_z: 0.2,
    index_regime_z: 0.1,
    company_specific_z: 0.6,
    surprise_reaction_beta_z: 0.25
  };
  return {
    market_data: false,
    ticker: "ACME",
    event_id: "evt_acme",
    evidence_quality: "HIGH",
    evidence: [{ evidence_id: "sec-1", source_type: "SEC_OR_OFFICIAL_FILING", url: "https://www.sec.gov/example", title: "Quarterly filing", fact: "Revenue trajectory improved.", published_at: "2026-09-20T00:00:00Z", retrieved_at: "2026-09-21T20:00:00Z" }],
    features,
    feature_evidence: Object.fromEntries(Object.keys(features).map((key) => [key, ["sec-1"]])),
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
