import { DEFAULT_RISK_CONFIG } from "./config.js";
import { finiteNumber, requireThat } from "./canonical.js";

export const LIVE_RISK_ACK = "KJ_EARNINGS_PRODUCTION_RISK_APPROVED_V1";
export const LIVE_CALIBRATION_ACK = "KJ_EARNINGS_CALIBRATION_APPROVED_V1";
export const LIVE_CALIBRATION_STATUS = "BACKTESTED_AND_APPROVED";

function positiveEnv(env, name, fallback) {
  const raw = env?.[name];
  if (raw === undefined || raw === null || raw === "") return fallback;
  const value = finiteNumber(raw, name);
  requireThat(value > 0, `${name} must be positive`, "CONFIGURATION_ERROR");
  return value;
}

function optionalPositiveInteger(env, name) {
  const raw = env?.[name];
  if (raw === undefined || raw === null || raw === "") return null;
  const value = finiteNumber(raw, name);
  requireThat(Number.isInteger(value) && value > 0, `${name} must be a positive integer`, "CONFIGURATION_ERROR");
  return value;
}

export function riskConfigFromEnv(env) {
  const maxCore = Math.trunc(positiveEnv(env, "MAX_CORE_POSITIONS", DEFAULT_RISK_CONFIG.max_core_positions));
  requireThat(maxCore >= 1 && maxCore <= 20, "MAX_CORE_POSITIONS invalid", "CONFIGURATION_ERROR");
  const operatingMode = String(env?.EARNINGS_DESK_MODE ?? "SHADOW").toUpperCase();
  requireThat(operatingMode === "SHADOW" || operatingMode === "LIVE", "EARNINGS_DESK_MODE must be SHADOW or LIVE", "CONFIGURATION_ERROR");
  const riskProfileId = String(env?.EARNINGS_RISK_PROFILE_ID ?? DEFAULT_RISK_CONFIG.risk_profile_id).trim();
  const capitalLimitsStatus = String(env?.EARNINGS_CAPITAL_LIMITS_STATUS ?? "NON_PRODUCTION_PLACEHOLDERS");
  const reportSha = String(env?.EARNINGS_CALIBRATION_REPORT_SHA256 ?? "").toLowerCase();
  const calibrationRequirements = {
    minimum_shadow_runs: optionalPositiveInteger(env, "LIVE_MIN_SHADOW_RUNS"),
    minimum_settled_shadow_trades: optionalPositiveInteger(env, "LIVE_MIN_SETTLED_SHADOW_TRADES"),
    minimum_shadow_model_outcomes: optionalPositiveInteger(env, "LIVE_MIN_SHADOW_MODEL_OUTCOMES")
  };
  return {
    ...DEFAULT_RISK_CONFIG,
    operating_mode: operatingMode,
    risk_profile_id: riskProfileId,
    capital_limits_status: capitalLimitsStatus,
    production_risk_approved:
      env?.EARNINGS_PRODUCTION_RISK_ACK === LIVE_RISK_ACK &&
      riskProfileId !== DEFAULT_RISK_CONFIG.risk_profile_id &&
      capitalLimitsStatus === "APPROVED_FOR_LIVE",
    calibration_approved:
      env?.EARNINGS_CALIBRATION_ACK === LIVE_CALIBRATION_ACK &&
      env?.EARNINGS_MODEL_CALIBRATION_STATUS === LIVE_CALIBRATION_STATUS &&
      /^[a-f0-9]{64}$/.test(reportSha),
    calibration_report_sha256: reportSha || null,
    calibration_requirements: calibrationRequirements,
    max_core_positions: maxCore,
    max_capital_per_trade_usd: positiveEnv(env, "MAX_CAPITAL_PER_TRADE_USD", DEFAULT_RISK_CONFIG.max_capital_per_trade_usd),
    max_daily_capital_usd: positiveEnv(env, "MAX_DAILY_CAPITAL_USD", DEFAULT_RISK_CONFIG.max_daily_capital_usd),
    market_input_max_age_minutes: positiveEnv(env, "MARKET_INPUT_MAX_AGE_MINUTES", DEFAULT_RISK_CONFIG.market_input_max_age_minutes)
  };
}

export async function assertLiveReadiness(db, riskConfig) {
  requireThat(riskConfig.operating_mode === "LIVE", "LIVE request requires EARNINGS_DESK_MODE=LIVE", "CONFIGURATION_ERROR");
  requireThat(riskConfig.production_risk_approved, `LIVE requires approved capital limits, a non-placeholder EARNINGS_RISK_PROFILE_ID, and exact ${LIVE_RISK_ACK} acknowledgement`, "CONFIGURATION_ERROR");
  requireThat(riskConfig.calibration_approved, "LIVE requires an approved backtest/calibration status and a 64-character calibration report SHA-256", "CONFIGURATION_ERROR");
  const requirements = riskConfig.calibration_requirements;
  requireThat(Object.values(requirements).every((value) => Number.isInteger(value) && value > 0), "LIVE calibration minimums must be explicitly configured; no production defaults are supplied", "CONFIGURATION_ERROR");
  const counts = await db.prepare(`SELECT
      (SELECT COUNT(*) FROM earnings_runs WHERE mode = 'SHADOW' AND status = 'CLOSED') AS shadow_runs,
      (SELECT COUNT(*) FROM earnings_positions p JOIN earnings_settlements s ON s.position_id = p.position_id WHERE p.mode = 'SHADOW') AS settled_shadow_trades,
      (SELECT COUNT(*) FROM earnings_model_outcomes o JOIN earnings_runs r ON r.run_id = o.run_id WHERE r.mode = 'SHADOW') AS shadow_model_outcomes`).first();
  const observed = {
    shadow_runs: Number(counts?.shadow_runs ?? 0),
    settled_shadow_trades: Number(counts?.settled_shadow_trades ?? 0),
    shadow_model_outcomes: Number(counts?.shadow_model_outcomes ?? 0)
  };
  requireThat(observed.shadow_runs >= requirements.minimum_shadow_runs, "LIVE blocked: insufficient closed SHADOW runs", "DATA_BLOCKED");
  requireThat(observed.settled_shadow_trades >= requirements.minimum_settled_shadow_trades, "LIVE blocked: insufficient settled SHADOW trades", "DATA_BLOCKED");
  requireThat(observed.shadow_model_outcomes >= requirements.minimum_shadow_model_outcomes, "LIVE blocked: insufficient SHADOW model outcomes", "DATA_BLOCKED");
  return {
    risk_profile_id: riskConfig.risk_profile_id,
    calibration_report_sha256: riskConfig.calibration_report_sha256,
    requirements,
    observed
  };
}
