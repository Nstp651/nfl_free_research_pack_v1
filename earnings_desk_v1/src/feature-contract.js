import { FEATURE_CONTRACT_VERSION, REQUIRED_FEATURES } from "./config.js";
import { clamp, finiteNumber, requireThat, round } from "./canonical.js";
import { mean, sampleStd } from "./math.js";

export const GUIDANCE_ANCHORS = Object.freeze({
  MATERIAL_CUT_OR_WITHDRAWAL: -3,
  CLEAR_CUT: -2,
  MODEST_CUT_OR_CAUTION: -1,
  UNCHANGED_OR_NOT_ISSUED: 0,
  MODEST_RAISE: 1,
  CLEAR_RAISE: 2,
  MATERIAL_RAISE: 3
});

export const COMPANY_SPECIFIC_ANCHORS = Object.freeze({
  MATERIAL_ADVERSE_CONFIRMED: -3,
  ADVERSE_CONFIRMED: -2,
  MODEST_ADVERSE_CONFIRMED: -1,
  NO_NET_MATERIAL_CHANGE: 0,
  MODEST_POSITIVE_CONFIRMED: 1,
  POSITIVE_CONFIRMED: 2,
  MATERIAL_POSITIVE_CONFIRMED: 3
});

export const FEATURE_SCORING_CONTRACT = Object.freeze({
  version: FEATURE_CONTRACT_VERSION,
  score_range: [-3, 3],
  rounding_decimal_places: 6,
  quantitative_rule: "clip(round((observed-reference_mean)/reference_std, 6), -3, 3)",
  features: Object.freeze({
    eps_revision_z: Object.freeze({ type: "QUANTITATIVE", observed: "(current_consensus-prior_consensus)/abs(prior_consensus)", evidence_source_types: ["CONSENSUS_AND_REVISIONS"] }),
    revenue_revision_z: Object.freeze({ type: "QUANTITATIVE", observed: "(current_consensus-prior_consensus)/abs(prior_consensus)", evidence_source_types: ["CONSENSUS_AND_REVISIONS"] }),
    guidance_trajectory: Object.freeze({ type: "QUANTITATIVE_WHEN_COMPARABLE_ELSE_ANCHORED", numeric_thresholds: [-0.10, -0.03, -0.005, 0.005, 0.03, 0.10], anchors: GUIDANCE_ANCHORS, evidence_source_types: ["SEC_OR_OFFICIAL_FILING", "COMPANY_INVESTOR_RELATIONS", "COMPANY_GUIDANCE"] }),
    consensus_dispersion_z: Object.freeze({ type: "QUANTITATIVE", observed: "sample_std(analyst_estimates)/abs(mean(analyst_estimates))", evidence_source_types: ["CONSENSUS_AND_REVISIONS"] }),
    peer_readthrough_z: Object.freeze({ type: "QUANTITATIVE", observed: "weighted_mean(peer_event_returns)", evidence_source_types: ["PEER_READTHROUGH"] }),
    pre_earnings_drift_z: Object.freeze({ type: "QUANTITATIVE", observed: "pre_event_price/start_price-1-benchmark_return", evidence_source_types: ["MARKET_OR_SECTOR_REGIME"] }),
    sector_regime_z: Object.freeze({ type: "QUANTITATIVE", observed: "sector_end_price/sector_start_price-1-index_return", evidence_source_types: ["MARKET_OR_SECTOR_REGIME"] }),
    index_regime_z: Object.freeze({ type: "QUANTITATIVE", observed: "index_end_price/index_start_price-1", evidence_source_types: ["MARKET_OR_SECTOR_REGIME"] }),
    company_specific_z: Object.freeze({ type: "ANCHORED_JUDGMENT", anchors: COMPANY_SPECIFIC_ANCHORS, evidence_source_types: ["SEC_OR_OFFICIAL_FILING", "COMPANY_INVESTOR_RELATIONS", "COMPANY_GUIDANCE", "MATERIAL_COMPANY_NEWS"] }),
    surprise_reaction_beta_z: Object.freeze({ type: "QUANTITATIVE", observed: "OLS_slope(historical_surprises,historical_event_returns)", minimum_observations: 4, evidence_source_types: ["HISTORICAL_EARNINGS"] })
  })
});

function objectInput(value, name) {
  requireThat(value && typeof value === "object" && !Array.isArray(value), `${name} input required`);
  return value;
}

function numericArray(value, name, minimum = 1) {
  requireThat(Array.isArray(value) && value.length >= minimum, `${name} requires at least ${minimum} observations`);
  return value.map((item, index) => finiteNumber(item, `${name}[${index}]`));
}

function zScore(observed, referenceMean, referenceStd, name) {
  const center = finiteNumber(referenceMean, `${name}.reference_mean`);
  const scale = finiteNumber(referenceStd, `${name}.reference_std`);
  requireThat(scale > 0, `${name}.reference_std must be positive`);
  return round(clamp((observed - center) / scale, -3, 3), 6);
}

function revisionScore(value, name) {
  const input = objectInput(value, name);
  const current = finiteNumber(input.current_consensus, `${name}.current_consensus`);
  const prior = finiteNumber(input.prior_consensus, `${name}.prior_consensus`);
  requireThat(Math.abs(prior) > 1e-12, `${name}.prior_consensus cannot be zero`);
  const observed = (current - prior) / Math.abs(prior);
  return zScore(observed, input.historical_revision_mean, input.historical_revision_std, name);
}

function anchoredScore(value, anchors, name) {
  const input = objectInput(value, name);
  const anchor = String(input.anchor ?? "");
  requireThat(Object.hasOwn(anchors, anchor), `${name}.anchor is not defined by ${FEATURE_CONTRACT_VERSION}`);
  requireThat(String(input.rationale ?? "").trim().length >= 12, `${name}.rationale must explain the selected anchor`);
  return anchors[anchor];
}

function guidanceScore(value) {
  const name = "guidance_trajectory";
  const input = objectInput(value, name);
  requireThat(typeof input.comparable_numeric_guidance_available === "boolean", `${name}.comparable_numeric_guidance_available must be boolean`);
  if (!input.comparable_numeric_guidance_available) return anchoredScore(input, GUIDANCE_ANCHORS, name);
  const priorLow = finiteNumber(input.prior_low, `${name}.prior_low`);
  const priorHigh = finiteNumber(input.prior_high, `${name}.prior_high`);
  const currentLow = finiteNumber(input.current_low, `${name}.current_low`);
  const currentHigh = finiteNumber(input.current_high, `${name}.current_high`);
  requireThat(priorHigh >= priorLow && currentHigh >= currentLow, `${name} ranges are inverted`);
  const priorMidpoint = (priorLow + priorHigh) / 2;
  requireThat(Math.abs(priorMidpoint) > 1e-12, `${name} prior midpoint cannot be zero`);
  const change = ((currentLow + currentHigh) / 2 - priorMidpoint) / Math.abs(priorMidpoint);
  if (change <= -0.10) return -3;
  if (change <= -0.03) return -2;
  if (change < -0.005) return -1;
  if (change <= 0.005) return 0;
  if (change < 0.03) return 1;
  if (change < 0.10) return 2;
  return 3;
}

function consensusDispersionScore(value) {
  const name = "consensus_dispersion_z";
  const input = objectInput(value, name);
  const estimates = numericArray(input.analyst_estimates, `${name}.analyst_estimates`, 2);
  const center = mean(estimates);
  requireThat(Math.abs(center) > 1e-12, `${name} estimate mean cannot be zero`);
  const observed = sampleStd(estimates) / Math.abs(center);
  return zScore(observed, input.historical_dispersion_mean, input.historical_dispersion_std, name);
}

function peerScore(value) {
  const name = "peer_readthrough_z";
  const input = objectInput(value, name);
  requireThat(Array.isArray(input.peer_events) && input.peer_events.length > 0, `${name}.peer_events required`);
  let totalWeight = 0;
  let weightedReturn = 0;
  for (const [index, peer] of input.peer_events.entries()) {
    objectInput(peer, `${name}.peer_events[${index}]`);
    const eventReturn = finiteNumber(peer.event_return, `${name}.peer_events[${index}].event_return`);
    const weight = finiteNumber(peer.relevance_weight, `${name}.peer_events[${index}].relevance_weight`);
    requireThat(weight > 0 && weight <= 1, `${name}.peer_events[${index}].relevance_weight must be in (0, 1]`);
    totalWeight += weight;
    weightedReturn += eventReturn * weight;
  }
  return zScore(weightedReturn / totalWeight, input.historical_peer_return_mean, input.historical_peer_return_std, name);
}

function driftScore(value) {
  const name = "pre_earnings_drift_z";
  const input = objectInput(value, name);
  const start = finiteNumber(input.start_price, `${name}.start_price`);
  const end = finiteNumber(input.pre_event_price, `${name}.pre_event_price`);
  requireThat(start > 0 && end > 0, `${name} prices must be positive`);
  const observed = end / start - 1 - finiteNumber(input.benchmark_return, `${name}.benchmark_return`);
  return zScore(observed, input.historical_excess_return_mean, input.historical_excess_return_std, name);
}

function sectorScore(value) {
  const name = "sector_regime_z";
  const input = objectInput(value, name);
  const start = finiteNumber(input.sector_start_price, `${name}.sector_start_price`);
  const end = finiteNumber(input.sector_end_price, `${name}.sector_end_price`);
  requireThat(start > 0 && end > 0, `${name} prices must be positive`);
  const observed = end / start - 1 - finiteNumber(input.index_return, `${name}.index_return`);
  return zScore(observed, input.historical_excess_return_mean, input.historical_excess_return_std, name);
}

function indexScore(value) {
  const name = "index_regime_z";
  const input = objectInput(value, name);
  const start = finiteNumber(input.index_start_price, `${name}.index_start_price`);
  const end = finiteNumber(input.index_end_price, `${name}.index_end_price`);
  requireThat(start > 0 && end > 0, `${name} prices must be positive`);
  return zScore(end / start - 1, input.historical_return_mean, input.historical_return_std, name);
}

function surpriseReactionScore(value) {
  const name = "surprise_reaction_beta_z";
  const input = objectInput(value, name);
  const surprises = numericArray(input.historical_surprises, `${name}.historical_surprises`, 4);
  const reactions = numericArray(input.historical_event_returns, `${name}.historical_event_returns`, 4);
  requireThat(surprises.length === reactions.length, `${name} arrays must have equal length`);
  const xMean = mean(surprises);
  const yMean = mean(reactions);
  const variance = surprises.reduce((sum, x) => sum + (x - xMean) ** 2, 0);
  requireThat(variance > 1e-12, `${name} surprise history has zero variance`);
  const covariance = surprises.reduce((sum, x, index) => sum + (x - xMean) * (reactions[index] - yMean), 0);
  return zScore(covariance / variance, input.historical_beta_mean, input.historical_beta_std, name);
}

export function scoreFeatureInputs(featureInputs) {
  objectInput(featureInputs, "feature_inputs");
  const missing = REQUIRED_FEATURES.filter((name) => !Object.hasOwn(featureInputs, name));
  const extras = Object.keys(featureInputs).filter((name) => !REQUIRED_FEATURES.includes(name));
  requireThat(missing.length === 0, `missing feature input(s): ${missing.join(", ")}`);
  requireThat(extras.length === 0, `unversioned feature input(s): ${extras.join(", ")}`);
  return {
    eps_revision_z: revisionScore(featureInputs.eps_revision_z, "eps_revision_z"),
    revenue_revision_z: revisionScore(featureInputs.revenue_revision_z, "revenue_revision_z"),
    guidance_trajectory: guidanceScore(featureInputs.guidance_trajectory),
    consensus_dispersion_z: consensusDispersionScore(featureInputs.consensus_dispersion_z),
    peer_readthrough_z: peerScore(featureInputs.peer_readthrough_z),
    pre_earnings_drift_z: driftScore(featureInputs.pre_earnings_drift_z),
    sector_regime_z: sectorScore(featureInputs.sector_regime_z),
    index_regime_z: indexScore(featureInputs.index_regime_z),
    company_specific_z: anchoredScore(featureInputs.company_specific_z, COMPANY_SPECIFIC_ANCHORS, "company_specific_z"),
    surprise_reaction_beta_z: surpriseReactionScore(featureInputs.surprise_reaction_beta_z)
  };
}

export function validateFeatureEvidence(featureEvidence, evidenceById) {
  const normalized = {};
  for (const name of REQUIRED_FEATURES) {
    const mappings = featureEvidence?.[name];
    requireThat(Array.isArray(mappings) && mappings.length > 0, `feature ${name} lacks evidence mapping`);
    const ids = [...new Set(mappings.map(String))].sort();
    requireThat(ids.every((id) => evidenceById.has(id)), `feature ${name} cites unknown evidence`);
    const allowed = FEATURE_SCORING_CONTRACT.features[name].evidence_source_types;
    requireThat(ids.some((id) => allowed.includes(evidenceById.get(id).source_type)), `feature ${name} lacks required source type: ${allowed.join(" or ")}`);
    normalized[name] = ids;
  }
  return normalized;
}
