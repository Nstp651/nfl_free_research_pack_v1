export function requireThat(condition, message, code = "VALIDATION_ERROR") {
  if (!condition) {
    const error = new Error(message);
    error.code = code;
    throw error;
  }
}

export function canonicalize(value) {
  if (value === null || typeof value !== "object") return value;
  if (Array.isArray(value)) return value.map(canonicalize);
  return Object.fromEntries(
    Object.keys(value)
      .sort()
      .map((key) => [key, canonicalize(value[key])])
  );
}

export function canonicalJson(value) {
  return JSON.stringify(canonicalize(value));
}

export async function sha256Hex(value) {
  const bytes = new TextEncoder().encode(
    typeof value === "string" ? value : canonicalJson(value)
  );
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

export function finiteNumber(value, label) {
  const number = Number(value);
  requireThat(Number.isFinite(number), `${label} must be finite`);
  return number;
}

export function isoTimestamp(value, label) {
  const text = String(value ?? "");
  requireThat(Number.isFinite(Date.parse(text)), `${label} must be an ISO timestamp`);
  return new Date(text).toISOString();
}

export function dateOnly(value, label) {
  const text = String(value ?? "");
  requireThat(/^\d{4}-\d{2}-\d{2}$/.test(text), `${label} must be YYYY-MM-DD`);
  requireThat(!Number.isNaN(Date.parse(`${text}T00:00:00Z`)), `${label} is invalid`);
  return text;
}

export function tickerText(value) {
  const ticker = String(value ?? "").trim().toUpperCase();
  requireThat(/^[A-Z][A-Z0-9.-]{0,9}$/.test(ticker), "ticker is invalid");
  return ticker;
}

export function clamp(value, low, high) {
  return Math.min(high, Math.max(low, value));
}

export function round(value, places = 8) {
  const factor = 10 ** places;
  return Math.round((value + Number.EPSILON) * factor) / factor;
}

export function parseJsonColumn(value, fallback = null) {
  if (value === null || value === undefined || value === "") return fallback;
  return typeof value === "string" ? JSON.parse(value) : value;
}

export function randomId(prefix) {
  return `${prefix}_${crypto.randomUUID()}`;
}
