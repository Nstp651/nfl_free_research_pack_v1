import { DEFAULT_RISK_CONFIG } from "./config.js";
import { finiteNumber, requireThat } from "./canonical.js";

function positiveEnv(env, name, fallback) {
  const raw = env?.[name];
  if (raw === undefined || raw === null || raw === "") return fallback;
  const value = finiteNumber(raw, name);
  requireThat(value > 0, `${name} must be positive`);
  return value;
}

export function riskConfigFromEnv(env) {
  const maxCore = Math.trunc(positiveEnv(env, "MAX_CORE_POSITIONS", DEFAULT_RISK_CONFIG.max_core_positions));
  requireThat(maxCore >= 1 && maxCore <= 20, "MAX_CORE_POSITIONS invalid");
  return {
    ...DEFAULT_RISK_CONFIG,
    max_core_positions: maxCore,
    max_capital_per_trade_usd: positiveEnv(env, "MAX_CAPITAL_PER_TRADE_USD", DEFAULT_RISK_CONFIG.max_capital_per_trade_usd),
    max_daily_capital_usd: positiveEnv(env, "MAX_DAILY_CAPITAL_USD", DEFAULT_RISK_CONFIG.max_daily_capital_usd),
    market_input_max_age_minutes: positiveEnv(env, "MARKET_INPUT_MAX_AGE_MINUTES", DEFAULT_RISK_CONFIG.market_input_max_age_minutes)
  };
}
