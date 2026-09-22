import { clamp, requireThat, round } from "./canonical.js";
import { credibleWeight, mean, sampleStd } from "./math.js";

function dteBucket(days) {
  if (days <= 2) return "0_2";
  if (days <= 7) return "3_7";
  if (days <= 21) return "8_21";
  return "22_PLUS";
}

function moneynessBucket(leg, spot) {
  const absolute = Math.abs(leg.strike / spot - 1);
  if (absolute <= 0.02) return "ATM_2PCT";
  const isOtm = leg.right === "CALL" ? leg.strike > spot : leg.strike < spot;
  if (absolute <= 0.07) return isOtm ? "OTM_2_7" : "ITM_2_7";
  return isOtm ? "OTM_7_PLUS" : "ITM_7_PLUS";
}

function summarize(rows, fallbackSpread) {
  return {
    count: rows.length,
    mean_iv: mean(rows.map((row) => Number(row.residual_iv))),
    sd_iv: Math.max(0.03, sampleStd(rows.map((row) => Number(row.residual_iv)))),
    mean_exit_spread: rows.some((row) => Number.isFinite(Number(row.exit_spread_fraction)))
      ? mean(rows.filter((row) => Number.isFinite(Number(row.exit_spread_fraction))).map((row) => Number(row.exit_spread_fraction)))
      : fallbackSpread
  };
}

export function buildPostEventIvModel({ observations, event, leg, spot, exitAt, riskConfig }) {
  const expiryAt = Date.parse(`${leg.expiry}T20:00:00Z`);
  const remainingDays = Math.max(0, (expiryAt - Date.parse(exitAt)) / 86_400_000);
  requireThat(remainingDays > 0, "option expires before intended exit", "DATA_BLOCKED");
  const dte = dteBucket(remainingDays);
  const moneyness = moneynessBucket(leg, spot);
  const clean = observations.filter((row) => Number.isFinite(Number(row.residual_iv)) && Number(row.residual_iv) > 0 && Number(row.residual_iv) < 8);
  requireThat(clean.length >= 8, "POST_EVENT_IV history requires at least 8 observations", "DATA_BLOCKED");
  const broad = summarize(clean, riskConfig.fallback_exit_spread_fraction);
  const cohortRows = clean.filter((row) => row.sector === event.sector && row.market_cap_cohort === event.market_cap_cohort && row.moneyness_bucket === moneyness && row.dte_bucket === dte);
  const cohort = cohortRows.length >= 4 ? summarize(cohortRows, broad.mean_exit_spread) : broad;
  const tickerRows = clean.filter((row) => row.ticker === event.ticker && row.moneyness_bucket === moneyness && row.dte_bucket === dte);
  const ticker = tickerRows.length >= 3 ? summarize(tickerRows, cohort.mean_exit_spread) : cohort;
  const tickerWeight = credibleWeight(tickerRows.length, 10);
  const cohortWeight = credibleWeight(cohortRows.length, 24);
  const expectedIv = tickerWeight * ticker.mean_iv + (1 - tickerWeight) * (cohortWeight * cohort.mean_iv + (1 - cohortWeight) * broad.mean_iv);
  const expectedSd = tickerWeight * ticker.sd_iv + (1 - tickerWeight) * (cohortWeight * cohort.sd_iv + (1 - cohortWeight) * broad.sd_iv);
  const exitSpread = tickerWeight * ticker.mean_exit_spread + (1 - tickerWeight) * (cohortWeight * cohort.mean_exit_spread + (1 - cohortWeight) * broad.mean_exit_spread);
  const confidence = tickerRows.length >= 10 ? "HIGH" : cohortRows.length >= 18 ? "MEDIUM" : "LOW";
  const zNodes = [-2, -1, 0, 1, 2];
  const weights = [0.0625, 0.25, 0.375, 0.25, 0.0625];
  return {
    version: "post-event-iv-v1.0.0",
    expected_residual_iv: round(clamp(expectedIv, 0.05, 5)),
    residual_iv_sd: round(clamp(expectedSd, 0.03, 2)),
    expected_exit_spread_fraction: round(clamp(exitSpread, 0.01, 0.60)),
    uncertainty_nodes: zNodes.map((z, index) => ({
      residual_iv: round(clamp(expectedIv + z * expectedSd, 0.05, 5)),
      weight: weights[index]
    })),
    confidence,
    cohort: { ticker: event.ticker, sector: event.sector, market_cap_cohort: event.market_cap_cohort, moneyness_bucket: moneyness, dte_bucket: dte },
    samples: { ticker: tickerRows.length, cohort: cohortRows.length, broad: clean.length },
    remaining_dte_at_exit: round(remainingDays, 6)
  };
}
