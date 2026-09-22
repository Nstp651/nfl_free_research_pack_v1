import { clamp, requireThat, round } from "./canonical.js";
import { VALUATION_VERSION } from "./config.js";
import { mean, normalCdf } from "./math.js";
import { buildPostEventIvModel } from "./iv-model.js";
import { marketLiquidity } from "./market-input.js";
import { newYorkMarketCloseUtc } from "./market-time.js";

export function blackScholes({ right, spot, strike, timeYears, volatility, riskFreeRate }) {
  requireThat([spot, strike, timeYears, volatility].every((value) => Number.isFinite(value) && value >= 0), "Black-Scholes input invalid");
  if (timeYears <= 0 || volatility <= 0) return Math.max(right === "CALL" ? spot - strike : strike - spot, 0);
  const sigmaRootT = volatility * Math.sqrt(timeYears);
  const d1 = (Math.log(spot / strike) + (riskFreeRate + 0.5 * volatility ** 2) * timeYears) / sigmaRootT;
  const d2 = d1 - sigmaRootT;
  if (right === "CALL") return spot * normalCdf(d1) - strike * Math.exp(-riskFreeRate * timeYears) * normalCdf(d2);
  return strike * Math.exp(-riskFreeRate * timeYears) * normalCdf(-d2) - spot * normalCdf(-d1);
}

function confidenceFloor(...levels) {
  const rank = { HIGH: 0, MEDIUM: 1, LOW: 2 };
  return [...levels].sort((a, b) => rank[b] - rank[a])[0];
}

export function valueCandidate({ candidate, marketInput, pModel, event, ivObservations, riskConfig }) {
  const multiplier = riskConfig.contract_multiplier;
  const exitMs = Date.parse(event.intended_exit_at);
  requireThat(Number.isFinite(exitMs), "intended exit timestamp invalid");
  const legModels = candidate.legs.map((leg) => buildPostEventIvModel({ observations: ivObservations, event, leg, spot: marketInput.underlying_price, exitAt: event.intended_exit_at, riskConfig }));
  const scenarioPnls = [];
  const scenarioExitValues = [];
  const profitScenarios = [];
  const entryAsk = candidate.legs.reduce((sum, leg) => sum + leg.ask, 0);
  const entrySpreads = candidate.legs.reduce((sum, leg) => sum + (leg.ask - leg.bid), 0);
  const entryPremium = entryAsk + entrySpreads * riskConfig.entry_slippage_fraction_of_spread;
  const contractCount = candidate.legs.length;
  const fees = contractCount * (riskConfig.commission_per_contract_usd + riskConfig.regulatory_fee_per_contract_usd) * 2;

  for (const underlyingReturn of pModel.distribution_draws) {
    const exitSpot = marketInput.underlying_price * Math.max(0.01, 1 + underlyingReturn);
    const combinedNodes = legModels[0].uncertainty_nodes.map((node, nodeIndex) => {
      let grossPerShare = 0;
      let exitHaircutPerShare = 0;
      for (let legIndex = 0; legIndex < candidate.legs.length; legIndex += 1) {
        const leg = candidate.legs[legIndex];
        const model = legModels[legIndex];
        const ivNode = model.uncertainty_nodes[nodeIndex];
        const expiryMs = Date.parse(newYorkMarketCloseUtc(leg.expiry));
        const timeYears = Math.max(0, (expiryMs - exitMs) / (365.25 * 86_400_000));
        const theoretical = blackScholes({ right: leg.right, spot: exitSpot, strike: leg.strike, timeYears, volatility: ivNode.residual_iv, riskFreeRate: riskConfig.risk_free_rate });
        grossPerShare += theoretical;
        exitHaircutPerShare += theoretical * model.expected_exit_spread_fraction * riskConfig.exit_slippage_fraction_of_spread;
      }
      const executableExit = Math.max(0, grossPerShare - exitHaircutPerShare) * multiplier;
      const netPnl = executableExit - entryPremium * multiplier - fees;
      return { weight: node.weight, gross: grossPerShare * multiplier, netPnl };
    });
    scenarioExitValues.push(combinedNodes.reduce((sum, node) => sum + node.gross * node.weight, 0));
    scenarioPnls.push(combinedNodes.reduce((sum, node) => sum + node.netPnl * node.weight, 0));
    profitScenarios.push(...combinedNodes.map((node) => ({ pnl: node.netPnl, weight: node.weight / pModel.distribution_draws.length })));
  }

  const expectedExit = mean(scenarioExitValues);
  const expectedNet = mean(scenarioPnls);
  const pProfit = profitScenarios.filter((scenario) => scenario.pnl > 0).reduce((sum, scenario) => sum + scenario.weight, 0);
  const maxLoss = entryPremium * multiplier + fees;
  const maxEntryPerShare = Math.max(0, (expectedExit - fees - riskConfig.minimum_expected_net_usd) / multiplier);
  const liquidity = marketLiquidity(candidate, riskConfig);
  return {
    candidate_id: candidate.candidate_id,
    ticker: event.ticker,
    event_time: event.report_at,
    intended_exit_at: event.intended_exit_at,
    desk: candidate.desk,
    trade_type: candidate.trade_type,
    expiry: candidate.legs[0].expiry,
    strikes: candidate.legs.map((leg) => leg.strike),
    legs: candidate.legs.map((leg, index) => ({ ...leg, post_event_iv_model: legModels[index] })),
    entry_ask: round(entryAsk, 4),
    entry_capital_usd: round(entryPremium * multiplier + contractCount * riskConfig.commission_per_contract_usd, 2),
    max_entry: round(maxEntryPerShare, 2),
    expected_exit_value: round(expectedExit, 2),
    p_profit: round(pProfit),
    expected_net_dollars: round(expectedNet, 2),
    ev_per_dollar_risk: round(maxLoss > 0 ? expectedNet / maxLoss : 0),
    max_loss: round(maxLoss, 2),
    model_edge: round(maxLoss > 0 ? expectedNet / maxLoss : 0),
    confidence: confidenceFloor(pModel.confidence, ...legModels.map((model) => model.confidence)),
    liquidity,
    quantity: 1,
    valuation_version: VALUATION_VERSION,
    scenario_count: profitScenarios.length
  };
}
