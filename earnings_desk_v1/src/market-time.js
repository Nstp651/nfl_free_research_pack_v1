import { RETURN_HORIZON_ID, RETURN_HORIZON_METHODOLOGY_VERSION } from "./config.js";
import { dateOnly, isoTimestamp, requireThat } from "./canonical.js";

const NEW_YORK = "America/New_York";

function zonedParts(date, timeZone) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23"
  }).formatToParts(date);
  return Object.fromEntries(parts.map((part) => [part.type, part.value]));
}

function zonedDateTimeToUtc(dateText, hour, minute, second, timeZone) {
  const [year, month, day] = dateText.split("-").map(Number);
  const targetWallMs = Date.UTC(year, month - 1, day, hour, minute, second);
  let utcMs = targetWallMs;
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const parts = zonedParts(new Date(utcMs), timeZone);
    const representedWallMs = Date.UTC(Number(parts.year), Number(parts.month) - 1, Number(parts.day), Number(parts.hour), Number(parts.minute), Number(parts.second));
    utcMs += targetWallMs - representedWallMs;
  }
  return new Date(utcMs);
}

export function newYorkMarketCloseUtc(dateText) {
  return zonedDateTimeToUtc(dateOnly(dateText, "US market date"), 16, 0, 0, NEW_YORK).toISOString();
}

export function newYorkDate(timestamp) {
  const parts = zonedParts(new Date(isoTimestamp(timestamp, "timestamp")), NEW_YORK);
  return `${parts.year}-${parts.month}-${parts.day}`;
}

export function isNewYorkRegularClose(timestamp) {
  const normalized = isoTimestamp(timestamp, "market close timestamp");
  return normalized === newYorkMarketCloseUtc(newYorkDate(normalized));
}

export function validateHistoricalHorizon(raw, eventDate, eventTiming) {
  const preEventPriceTimestamp = isoTimestamp(raw.pre_event_price_timestamp, "pre_event_price_timestamp");
  const exitPriceTimestamp = isoTimestamp(raw.exit_price_timestamp, "exit_price_timestamp");
  requireThat(raw.return_horizon_id === RETURN_HORIZON_ID, `return_horizon_id must be ${RETURN_HORIZON_ID}`, "DATA_BLOCKED");
  requireThat(raw.return_horizon_methodology_version === RETURN_HORIZON_METHODOLOGY_VERSION, `return_horizon_methodology_version must be ${RETURN_HORIZON_METHODOLOGY_VERSION}`, "DATA_BLOCKED");
  requireThat(isNewYorkRegularClose(preEventPriceTimestamp), "pre-event price timestamp must be 16:00 America/New_York", "DATA_BLOCKED");
  requireThat(isNewYorkRegularClose(exitPriceTimestamp), "exit price timestamp must be 16:00 America/New_York", "DATA_BLOCKED");
  requireThat(Date.parse(exitPriceTimestamp) > Date.parse(preEventPriceTimestamp), "historical exit must follow pre-event price", "DATA_BLOCKED");
  requireThat(Date.parse(exitPriceTimestamp) - Date.parse(preEventPriceTimestamp) <= 7 * 86_400_000, "historical horizon exceeds seven calendar days", "DATA_BLOCKED");
  const preDate = newYorkDate(preEventPriceTimestamp);
  const exitDate = newYorkDate(exitPriceTimestamp);
  requireThat(eventTiming === "AMC" ? preDate === eventDate : exitDate === eventDate, `${eventTiming} timestamps do not match event_date horizon convention`, "DATA_BLOCKED");
  return {
    pre_event_price_timestamp: preEventPriceTimestamp,
    exit_price_timestamp: exitPriceTimestamp,
    return_horizon_id: RETURN_HORIZON_ID,
    return_horizon_methodology_version: RETURN_HORIZON_METHODOLOGY_VERSION
  };
}
