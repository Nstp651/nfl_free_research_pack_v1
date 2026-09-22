import { round } from "./canonical.js";

const CONFIDENCE_RANK = { HIGH: 3, MEDIUM: 2, LOW: 1 };

function rank(a, b) {
  return b.expected_net_dollars - a.expected_net_dollars ||
    b.ev_per_dollar_risk - a.ev_per_dollar_risk ||
    b.p_profit - a.p_profit ||
    (CONFIDENCE_RANK[b.confidence] ?? 0) - (CONFIDENCE_RANK[a.confidence] ?? 0) ||
    a.liquidity.combined_spread_fraction - b.liquidity.combined_spread_fraction ||
    a.candidate_id.localeCompare(b.candidate_id);
}

export function selectCandidates(valuations, riskConfig) {
  const ranked = [...valuations].sort(rank);
  const results = [];
  let coreCount = 0;
  let committedCapital = 0;
  for (let index = 0; index < ranked.length; index += 1) {
    const value = ranked[index];
    const hardFailures = [];
    if (!value.liquidity.adequate) hardFailures.push("INADEQUATE_OPTION_LIQUIDITY");
    if (value.entry_ask > value.max_entry) hardFailures.push("ASK_ABOVE_MAX_ENTRY");
    if (value.expected_net_dollars <= 0) hardFailures.push("NON_POSITIVE_EV_AFTER_COSTS");
    if (value.entry_capital_usd > riskConfig.max_capital_per_trade_usd) hardFailures.push("PER_TRADE_CAPITAL_LIMIT");
    const meetsCore = hardFailures.length === 0 &&
      value.expected_net_dollars >= riskConfig.minimum_expected_net_usd &&
      value.ev_per_dollar_risk >= riskConfig.minimum_ev_per_dollar &&
      value.p_profit >= riskConfig.minimum_p_profit;
    let selection = "PASS";
    const reasons = [...hardFailures];
    if (meetsCore && coreCount < riskConfig.max_core_positions && committedCapital + value.entry_capital_usd <= riskConfig.max_daily_capital_usd) {
      selection = "CORE";
      coreCount += 1;
      committedCapital += value.entry_capital_usd;
    } else if (hardFailures.length === 0 && value.expected_net_dollars > 0) {
      selection = "WATCH";
      if (!meetsCore) reasons.push("BELOW_CORE_EDGE_OR_PROBABILITY_GATE");
      else reasons.push("CORE_COUNT_OR_DAILY_CAPITAL_LIMIT");
    }
    results.push({ ...value, rank: index + 1, selection, selection_reasons: reasons });
  }
  return {
    selections: results,
    core_count: coreCount,
    capital_at_risk_usd: round(committedCapital, 2),
    no_forced_trade: coreCount === 0
  };
}

export function tradeCard(selection) {
  if (selection.selection !== "CORE") return null;
  return {
    classification: `CORE — ${selection.trade_type}`,
    ticker: selection.ticker,
    event_time: selection.event_time,
    expiry: selection.expiry,
    strikes: selection.strikes,
    max_entry: selection.max_entry,
    quantity: 1,
    max_capital_at_risk: selection.max_loss,
    p_profit: selection.p_profit,
    expected_net_dollars: selection.expected_net_dollars,
    model_edge: selection.model_edge,
    confidence: selection.confidence,
    exit: "NEXT MORNING RUN"
  };
}
