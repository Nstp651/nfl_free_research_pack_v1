import { parseJsonColumn, round } from "./canonical.js";
import { mean } from "./math.js";

function safeMean(values) {
  return values.length ? mean(values) : null;
}

function group(rows, keyFn, metricFn) {
  const groups = new Map();
  for (const row of rows) {
    const key = String(keyFn(row) ?? "UNKNOWN");
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(row);
  }
  return Object.fromEntries([...groups.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([key, values]) => [key, metricFn(values)]));
}

function optionMetrics(rows) {
  const completed = rows.filter((row) => row.realized_pnl !== null && row.realized_pnl !== undefined);
  return {
    count: completed.length,
    predicted_p_profit: completed.length ? round(mean(completed.map((row) => Number(row.p_profit)))) : null,
    realized_profit_rate: completed.length ? round(mean(completed.map((row) => Number(row.realized_pnl) > 0 ? 1 : 0))) : null,
    p_profit_brier: completed.length ? round(mean(completed.map((row) => (Number(row.p_profit) - (Number(row.realized_pnl) > 0 ? 1 : 0)) ** 2))) : null,
    expected_pnl: completed.length ? round(completed.reduce((sum, row) => sum + Number(row.expected_net_dollars), 0), 2) : null,
    realized_pnl: completed.length ? round(completed.reduce((sum, row) => sum + Number(row.realized_pnl), 0), 2) : null,
    pnl_forecast_error: completed.length ? round(mean(completed.map((row) => Number(row.realized_pnl) - Number(row.expected_net_dollars))), 2) : null
  };
}

export async function calibrationDashboard(db) {
  const distributionResult = await db.prepare(`SELECT o.*, f.freeze_json, e.ticker, e.sector, e.event_timing
    FROM earnings_model_outcomes o
    JOIN earnings_freezes f ON f.freeze_id = o.freeze_id
    JOIN earnings_events e ON e.event_id = o.event_id
    ORDER BY o.recorded_at`).all();
  const distributionRows = (distributionResult.results ?? []).map((row) => ({ ...row, freeze: parseJsonColumn(row.freeze_json) }));
  const directionBrier = safeMean(distributionRows.map((row) => {
    const pUp = Number(row.freeze.return_distribution.p_up);
    const outcome = Number(row.actual_underlying_return) > 0 ? 1 : 0;
    return (pUp - outcome) ** 2;
  }));
  const absErrors = distributionRows.map((row) => Number(row.actual_absolute_move) - Number(row.freeze.return_distribution.expected_abs_move));
  const pitBins = Array.from({ length: 10 }, (_, index) => ({ lower: index / 10, upper: (index + 1) / 10, count: 0 }));
  for (const row of distributionRows) {
    const index = Math.min(9, Math.floor(Number(row.forecast_percentile) * 10));
    pitBins[index].count += 1;
  }

  const optionResult = await db.prepare(`SELECT v.p_profit, v.expected_net_dollars, v.confidence, v.trade_type,
      e.ticker, e.sector, e.event_timing, s.realized_pnl, r.operator_minutes
    FROM earnings_valuations v
    JOIN earnings_valuation_batches b ON b.valuation_batch_id = v.valuation_batch_id
    JOIN earnings_events e ON e.event_id = b.event_id
    JOIN earnings_runs r ON r.run_id = b.run_id
    LEFT JOIN earnings_positions p ON p.valuation_id = v.valuation_id
    LEFT JOIN earnings_settlements s ON s.position_id = p.position_id
    WHERE v.selection = 'CORE'`).all();
  const optionRows = optionResult.results ?? [];
  const runHoursResult = await db.prepare("SELECT SUM(operator_minutes) AS minutes FROM earnings_runs WHERE operator_minutes IS NOT NULL").first();
  const realizedTotal = optionRows.reduce((sum, row) => sum + Number(row.realized_pnl ?? 0), 0);
  const operatorHours = Number(runHoursResult?.minutes ?? 0) / 60;
  const byMetric = (rows) => optionMetrics(rows);
  return {
    generated_at: new Date().toISOString(),
    sample_sizes: { distribution_events: distributionRows.length, core_signals: optionRows.length, completed_trades: optionRows.filter((row) => row.realized_pnl !== null && row.realized_pnl !== undefined).length },
    direction: { brier_score: directionBrier === null ? null : round(directionBrier) },
    distribution_calibration: { pit_mean: distributionRows.length ? round(mean(distributionRows.map((row) => Number(row.forecast_percentile)))) : null, pit_bins: pitBins },
    absolute_move: { mean_error: absErrors.length ? round(mean(absErrors)) : null, mean_absolute_error: absErrors.length ? round(mean(absErrors.map(Math.abs))) : null },
    option_pnl: optionMetrics(optionRows),
    by_confidence: group(optionRows, (row) => row.confidence, byMetric),
    by_ticker: group(optionRows, (row) => row.ticker, byMetric),
    by_sector: group(optionRows, (row) => row.sector, byMetric),
    by_event_timing: group(optionRows, (row) => row.event_timing, byMetric),
    by_trade_type: group(optionRows, (row) => row.trade_type, byMetric),
    profit_per_operator_hour: operatorHours > 0 ? round(realizedTotal / operatorHours, 2) : null
  };
}
