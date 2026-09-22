import { clamp, finiteNumber, isoTimestamp, requireThat, round, sha256Hex, tickerText } from "./canonical.js";
import { newYorkMarketCloseUtc } from "./market-time.js";

function expiryText(value) {
  const text = String(value ?? "");
  requireThat(/^\d{4}-\d{2}-\d{2}$/.test(text), "option expiry must be YYYY-MM-DD");
  requireThat(Number.isFinite(Date.parse(newYorkMarketCloseUtc(text))), "option expiry invalid");
  return text;
}

export async function validateMarketInput(input, event, freeze, riskConfig, now = new Date()) {
  requireThat(input && typeof input === "object" && !Array.isArray(input), "market input required");
  requireThat(input.source_type === "IBKR_SCREENSHOT", "v1 market source must be IBKR_SCREENSHOT", "DATA_BLOCKED");
  requireThat(String(input.run_id) === String(freeze.run_id), "market input run_id mismatch");
  requireThat(tickerText(input.ticker) === event.ticker, "market input ticker mismatch");
  requireThat(input.freeze_receipt_sha256 === freeze.freeze_receipt_sha256, "freeze receipt mismatch");
  requireThat(/^[a-f0-9]{64}$/.test(String(input.screenshot_sha256 ?? "")), "screenshot_sha256 is required");
  const capturedAt = isoTimestamp(input.captured_at, "captured_at");
  const capturedMs = Date.parse(capturedAt);
  requireThat(capturedMs >= Date.parse(freeze.frozen_at), "market screenshot predates freeze");
  const ageMinutes = (now.getTime() - capturedMs) / 60_000;
  requireThat(ageMinutes >= -2 && ageMinutes <= riskConfig.market_input_max_age_minutes, "IBKR market input is stale", "DATA_BLOCKED");
  const underlyingPrice = finiteNumber(input.underlying_price, "underlying_price");
  requireThat(underlyingPrice > 0, "underlying_price must be positive");
  requireThat(Array.isArray(input.quotes) && input.quotes.length > 0 && input.quotes.length <= 80, "quotes must contain 1-80 rows");

  const seen = new Set();
  const quotes = input.quotes.map((row, index) => {
    requireThat(row && typeof row === "object", `quote ${index} invalid`);
    const right = String(row.right ?? "").toUpperCase();
    requireThat(right === "CALL" || right === "PUT", `quote ${index} right invalid`);
    const expiry = expiryText(row.expiry);
    const strike = finiteNumber(row.strike, `quote ${index} strike`);
    const bid = finiteNumber(row.bid, `quote ${index} bid`);
    const ask = finiteNumber(row.ask, `quote ${index} ask`);
    requireThat(strike > 0 && bid >= 0 && ask > 0 && ask >= bid, `quote ${index} has invalid executable prices`);
    const key = `${expiry}|${strike}|${right}`;
    requireThat(!seen.has(key), `duplicate option quote ${key}`);
    seen.add(key);
    const midpoint = (bid + ask) / 2;
    const spreadFraction = midpoint > 0 ? (ask - bid) / midpoint : 1;
    const visibleIv = row.iv === null || row.iv === undefined ? null : finiteNumber(row.iv, `quote ${index} iv`);
    if (visibleIv !== null) requireThat(visibleIv > 0 && visibleIv < 10, `quote ${index} iv invalid`);
    return {
      contract_key: key,
      ticker: event.ticker,
      expiry,
      strike: round(strike, 4),
      right,
      bid: round(bid, 4),
      ask: round(ask, 4),
      iv: visibleIv,
      delta: row.delta === null || row.delta === undefined ? null : finiteNumber(row.delta, `quote ${index} delta`),
      open_interest: row.open_interest === null || row.open_interest === undefined ? null : Math.trunc(finiteNumber(row.open_interest, `quote ${index} open_interest`)),
      volume: row.volume === null || row.volume === undefined ? null : Math.trunc(finiteNumber(row.volume, `quote ${index} volume`)),
      spread_fraction: round(spreadFraction),
      source_row: index
    };
  });
  const normalized = {
    source_type: "IBKR_SCREENSHOT",
    run_id: String(input.run_id),
    event_id: event.event_id,
    ticker: event.ticker,
    freeze_receipt_sha256: freeze.freeze_receipt_sha256,
    screenshot_sha256: String(input.screenshot_sha256),
    captured_at: capturedAt,
    underlying_price: round(underlyingPrice, 4),
    quotes,
    extraction_notes: String(input.extraction_notes ?? "").trim() || null,
    freshness_minutes: round(ageMinutes, 4)
  };
  return { ...normalized, market_input_sha256: await sha256Hex(normalized) };
}

export function buildCandidates(marketInput) {
  const quotes = marketInput.quotes;
  const candidates = [];
  for (const quote of quotes) {
    candidates.push({
      candidate_id: `${quote.right}:${quote.contract_key}`,
      trade_type: quote.right,
      desk: "EARN-DIRECTION",
      legs: [quote]
    });
  }
  const byExpiryStrike = new Map();
  for (const quote of quotes) {
    const key = `${quote.expiry}|${quote.strike}`;
    if (!byExpiryStrike.has(key)) byExpiryStrike.set(key, {});
    byExpiryStrike.get(key)[quote.right] = quote;
  }
  for (const pair of byExpiryStrike.values()) {
    if (pair.CALL && pair.PUT) {
      candidates.push({
        candidate_id: `STRADDLE:${pair.CALL.expiry}:${pair.CALL.strike}`,
        trade_type: "STRADDLE",
        desk: "EARN-MOVE",
        legs: [pair.CALL, pair.PUT]
      });
    }
  }
  const expiries = [...new Set(quotes.map((quote) => quote.expiry))];
  for (const expiry of expiries) {
    const calls = quotes.filter((quote) => quote.expiry === expiry && quote.right === "CALL" && quote.strike >= marketInput.underlying_price);
    const puts = quotes.filter((quote) => quote.expiry === expiry && quote.right === "PUT" && quote.strike <= marketInput.underlying_price);
    for (const call of calls) {
      for (const put of puts) {
        if (put.strike >= call.strike) continue;
        const width = (call.strike - put.strike) / marketInput.underlying_price;
        if (width > 0.20) continue;
        candidates.push({
          candidate_id: `STRANGLE:${expiry}:${put.strike}:${call.strike}`,
          trade_type: "STRANGLE",
          desk: "EARN-MOVE",
          legs: [put, call]
        });
      }
    }
  }
  return candidates;
}

export function marketLiquidity(candidate, riskConfig) {
  const legQuality = candidate.legs.map((leg) => {
    const nonzeroBid = leg.bid > 0;
    const spreadOk = leg.spread_fraction <= riskConfig.max_leg_spread_fraction;
    return {
      contract_key: leg.contract_key,
      nonzero_bid: nonzeroBid,
      spread_fraction: leg.spread_fraction,
      acceptable: nonzeroBid && spreadOk
    };
  });
  const totalAsk = candidate.legs.reduce((sum, leg) => sum + leg.ask, 0);
  const totalBid = candidate.legs.reduce((sum, leg) => sum + leg.bid, 0);
  const midpoint = (totalAsk + totalBid) / 2;
  const combinedSpread = midpoint > 0 ? (totalAsk - totalBid) / midpoint : 1;
  return {
    adequate: legQuality.every((leg) => leg.acceptable) && combinedSpread <= riskConfig.max_spread_fraction,
    combined_spread_fraction: clamp(round(combinedSpread), 0, 100),
    legs: legQuality
  };
}
