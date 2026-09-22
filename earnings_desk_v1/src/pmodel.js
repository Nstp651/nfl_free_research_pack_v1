import { MODEL_CONFIG, REQUIRED_FEATURES } from "./config.js";
import { clamp, requireThat, round } from "./canonical.js";
import { credibleWeight, inverseNormal, mean, sampleStd, summarizeDraws, weightedAverage, winsorize } from "./math.js";
import { validateHistoricalHorizon } from "./market-time.js";

function validHistoryRow(row, cutoffMs) {
  const eventMs = Date.parse(`${String(row.event_date ?? "")}T23:59:59Z`);
  if (!(Number.isFinite(eventMs) &&
    eventMs < cutoffMs &&
    Number.isFinite(Number(row.event_return)) &&
    row.return_horizon_id === MODEL_CONFIG.return_horizon_id &&
    row.return_horizon_methodology_version === MODEL_CONFIG.return_horizon_methodology_version)) return false;
  try {
    validateHistoricalHorizon(row, row.event_date, row.event_timing);
    return true;
  } catch {
    return false;
  }
}

function cohort(history, predicate, limit) {
  return history
    .filter(predicate)
    .sort((a, b) => String(b.event_date).localeCompare(String(a.event_date)))
    .slice(0, limit)
    .map((row) => winsorize(Number(row.event_return), MODEL_CONFIG.winsor_return));
}

function robustScale(values, fallback) {
  const standard = sampleStd(values);
  const absolute = values.length ? mean(values.map(Math.abs)) * 1.253314 : 0;
  const available = [standard, absolute].filter((value) => Number.isFinite(value) && value > 0);
  return available.length ? mean(available) : fallback;
}

function confidenceLabel(effectiveN, missingCount, evidenceQuality) {
  if (effectiveN >= 35 && missingCount === 0 && evidenceQuality === "HIGH") return "HIGH";
  if (effectiveN >= 16 && missingCount <= 2 && evidenceQuality !== "LOW") return "MEDIUM";
  return "LOW";
}

export function buildPModel({ event, research, history, researchCutoff }) {
  const cutoffMs = Date.parse(researchCutoff);
  requireThat(Number.isFinite(cutoffMs), "research cutoff invalid");
  const prior = history.filter((row) => validHistoryRow(row, cutoffMs));
  requireThat(prior.length >= MODEL_CONFIG.minimum_history_events, `historical dataset requires at least ${MODEL_CONFIG.minimum_history_events} prior events`, "DATA_BLOCKED");

  const tickerRows = cohort(prior, (row) => row.ticker === event.ticker, 40);
  const sectorRows = cohort(prior, (row) => row.sector === event.sector && row.market_cap_cohort === event.market_cap_cohort, 160);
  const broadRows = cohort(prior, () => true, 400);
  requireThat(broadRows.length >= MODEL_CONFIG.minimum_broad_events, `broad history requires at least ${MODEL_CONFIG.minimum_broad_events} events`, "DATA_BLOCKED");

  const broadMean = mean(broadRows);
  const sectorCredibility = credibleWeight(sectorRows.length, MODEL_CONFIG.sector_prior_events);
  const sectorMean = sectorRows.length ? mean(sectorRows) : broadMean;
  const pooledSectorMean = sectorCredibility * sectorMean + (1 - sectorCredibility) * broadMean;
  const tickerCredibility = credibleWeight(tickerRows.length, MODEL_CONFIG.ticker_prior_events);
  const tickerMean = tickerRows.length ? mean(tickerRows) : pooledSectorMean;
  const hierarchicalMean = tickerCredibility * tickerMean + (1 - tickerCredibility) * pooledSectorMean;

  const broadScale = robustScale(broadRows, 0.05);
  const sectorScale = robustScale(sectorRows, broadScale);
  const tickerScale = robustScale(tickerRows, sectorScale);
  const hierarchicalScale = weightedAverage([
    { value: tickerScale, weight: tickerCredibility },
    { value: sectorScale, weight: (1 - tickerCredibility) * sectorCredibility },
    { value: broadScale, weight: (1 - tickerCredibility) * (1 - sectorCredibility) }
  ]);

  const missing = REQUIRED_FEATURES.filter((name) => research.features[name] === null || research.features[name] === undefined);
  requireThat(missing.length === 0, `missing structured feature(s): ${missing.join(", ")}`, "DATA_BLOCKED");
  const featureContributions = Object.fromEntries(
    REQUIRED_FEATURES.map((name) => [name, round(Number(research.features[name]) * MODEL_CONFIG.feature_weights[name])])
  );
  const rawFeatureShift = Object.values(featureContributions).reduce((sum, value) => sum + value, 0);
  const evidenceMultiplier = research.evidence_quality === "HIGH" ? 1 : research.evidence_quality === "MEDIUM" ? 0.82 : 0.60;
  const featureShift = clamp(rawFeatureShift * evidenceMultiplier, -MODEL_CONFIG.max_location_shift, MODEL_CONFIG.max_location_shift);

  const realizedVol = Number(event.realized_vol_20d);
  requireThat(Number.isFinite(realizedVol) && realizedVol > 0, "20d realized volatility is required", "DATA_BLOCKED");
  const dailyToEventScale = realizedVol * Math.sqrt(1.5);
  const eventScale = weightedAverage([
    { value: tickerScale, weight: MODEL_CONFIG.scale_weights.historical_event },
    { value: dailyToEventScale, weight: MODEL_CONFIG.scale_weights.realized_vol_20d },
    { value: sectorScale, weight: MODEL_CONFIG.scale_weights.cohort_event }
  ]);
  const dispersionExpansion = 1 + Math.max(0, Number(research.features.consensus_dispersion_z)) * 0.08;
  const sparsePenalty = MODEL_CONFIG.uncertainty.sparse_history_sigma / Math.sqrt(1 + tickerRows.length + 0.25 * sectorRows.length);
  const qualityPenalty = research.evidence_quality === "LOW" ? MODEL_CONFIG.uncertainty.low_evidence_multiplier : 1;
  const parameterUncertainty = (MODEL_CONFIG.uncertainty.base_sigma + sparsePenalty + missing.length * MODEL_CONFIG.uncertainty.per_missing_feature_sigma) * qualityPenalty;
  const finalScale = clamp(Math.sqrt((eventScale * dispersionExpansion) ** 2 + parameterUncertainty ** 2), MODEL_CONFIG.minimum_scale, MODEL_CONFIG.maximum_scale);
  const location = clamp(hierarchicalMean + featureShift, -0.20, 0.20);
  const skewSignal = clamp(
    0.35 * Number(research.features.guidance_trajectory) +
      0.20 * Number(research.features.eps_revision_z) +
      0.20 * Number(research.features.company_specific_z) +
      0.25 * Number(research.features.surprise_reaction_beta_z),
    -1.5,
    1.5
  );

  const draws = [];
  for (let index = 0; index < MODEL_CONFIG.distribution_draws; index += 1) {
    const probability = (index + 0.5) / MODEL_CONFIG.distribution_draws;
    const z = inverseNormal(probability);
    const heavyTail = z * (1 + MODEL_CONFIG.tail_inflation * z * z);
    const skewTerm = 0.08 * skewSignal * finalScale * (z * z - 1);
    draws.push(round(clamp(location + finalScale * heavyTail + skewTerm, -0.95, 3.0), 10));
  }

  const effectiveN = tickerRows.length + 0.35 * sectorRows.length + 0.10 * broadRows.length;
  return {
    model_version: MODEL_CONFIG.model_version,
    coefficient_status: MODEL_CONFIG.coefficient_status,
    feature_contract_version: MODEL_CONFIG.feature_contract_version,
    return_horizon_id: MODEL_CONFIG.return_horizon_id,
    return_horizon_methodology_version: MODEL_CONFIG.return_horizon_methodology_version,
    market_data: false,
    ticker: event.ticker,
    event_id: event.event_id,
    event_time: event.report_at,
    intended_exit_at: event.intended_exit_at,
    distribution_family: "hierarchical_shrunk_heavy_tail_grid_v1",
    distribution_draws: draws,
    ...summarizeDraws(draws),
    parameters: {
      location: round(location),
      scale: round(finalScale),
      skew_signal: round(skewSignal),
      parameter_uncertainty_sigma: round(parameterUncertainty),
      hierarchical_base_mean: round(hierarchicalMean),
      feature_shift: round(featureShift),
      feature_contributions: featureContributions
    },
    pooling: {
      ticker_events: tickerRows.length,
      sector_cohort_events: sectorRows.length,
      broad_events: broadRows.length,
      ticker_credibility: round(tickerCredibility),
      sector_credibility: round(sectorCredibility),
      effective_sample_size: round(effectiveN, 4)
    },
    confidence: confidenceLabel(effectiveN, missing.length, research.evidence_quality),
    uncertainty_notes: [
      tickerRows.length < 8 ? "SPARSE_TICKER_HISTORY" : null,
      research.evidence_quality === "LOW" ? "LOW_RESEARCH_EVIDENCE_QUALITY" : null,
      parameterUncertainty > 0.02 ? "HIGH_PARAMETER_UNCERTAINTY" : null
    ].filter(Boolean)
  };
}
