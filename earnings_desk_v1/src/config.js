export const FEATURE_CONTRACT_VERSION = "earn-feature-contract-v1.1.0";
export const RETURN_HORIZON_ID = "PRE_EVENT_CLOSE_TO_POST_EVENT_CLOSE_ET_V1";
export const RETURN_HORIZON_METHODOLOGY_VERSION = "earn-return-horizon-v1.0.0";
export const MODEL_VERSION = "earn-pmodel-v1.1.0";
export const IV_MODEL_VERSION = "post-event-iv-v1.1.0";
export const VALUATION_VERSION = "earn-option-value-v1.1.0";
export const SELECTION_VERSION = "earn-selection-v1.1.0";

export const MODEL_CONFIG = Object.freeze({
  model_version: MODEL_VERSION,
  coefficient_status: "V1_PRIORS_NOT_EMPIRICALLY_TRAINED",
  feature_contract_version: FEATURE_CONTRACT_VERSION,
  return_horizon_id: RETURN_HORIZON_ID,
  return_horizon_methodology_version: RETURN_HORIZON_METHODOLOGY_VERSION,
  distribution_draws: 401,
  ticker_prior_events: 16,
  sector_prior_events: 40,
  broad_prior_events: 80,
  minimum_broad_events: 20,
  minimum_history_events: 8,
  winsor_return: 0.45,
  minimum_scale: 0.0125,
  maximum_scale: 0.35,
  tail_inflation: 0.045,
  max_location_shift: 0.08,
  feature_weights: Object.freeze({
    eps_revision_z: 0.0040,
    revenue_revision_z: 0.0030,
    guidance_trajectory: 0.0080,
    consensus_dispersion_z: -0.0015,
    peer_readthrough_z: 0.0040,
    pre_earnings_drift_z: 0.0015,
    sector_regime_z: 0.0020,
    index_regime_z: 0.0015,
    company_specific_z: 0.0060,
    surprise_reaction_beta_z: 0.0030
  }),
  scale_weights: Object.freeze({
    historical_event: 0.55,
    realized_vol_20d: 0.25,
    cohort_event: 0.20
  }),
  uncertainty: Object.freeze({
    base_sigma: 0.006,
    per_missing_feature_sigma: 0.0015,
    sparse_history_sigma: 0.018,
    low_evidence_multiplier: 1.35
  })
});

export const DEFAULT_RISK_CONFIG = Object.freeze({
  risk_profile_id: "V1_PLACEHOLDER_NOT_APPROVED_FOR_LIVE",
  production_risk_approved: false,
  calibration_approved: false,
  max_core_positions: 2,
  max_capital_per_trade_usd: 750,
  max_daily_capital_usd: 1500,
  market_input_max_age_minutes: 20,
  max_spread_fraction: 0.25,
  max_leg_spread_fraction: 0.35,
  minimum_expected_net_usd: 5,
  minimum_ev_per_dollar: 0.03,
  minimum_p_profit: 0.45,
  commission_per_contract_usd: 0.65,
  regulatory_fee_per_contract_usd: 0.10,
  entry_slippage_fraction_of_spread: 0,
  exit_slippage_fraction_of_spread: 0.35,
  fallback_exit_spread_fraction: 0.12,
  risk_free_rate: 0.04,
  contract_multiplier: 100
});

export const SOURCE_HIERARCHY = Object.freeze([
  "SEC_OR_OFFICIAL_FILING",
  "COMPANY_INVESTOR_RELATIONS",
  "COMPANY_GUIDANCE",
  "CONSENSUS_AND_REVISIONS",
  "PEER_READTHROUGH",
  "INDUSTRY_OR_MACRO",
  "HISTORICAL_EARNINGS",
  "MARKET_OR_SECTOR_REGIME",
  "MATERIAL_COMPANY_NEWS"
]);

export const REQUIRED_FEATURES = Object.freeze([
  "eps_revision_z",
  "revenue_revision_z",
  "guidance_trajectory",
  "consensus_dispersion_z",
  "peer_readthrough_z",
  "pre_earnings_drift_z",
  "sector_regime_z",
  "index_regime_z",
  "company_specific_z",
  "surprise_reaction_beta_z"
]);
