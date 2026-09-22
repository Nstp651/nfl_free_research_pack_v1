import { requireThat } from "./canonical.js";

async function digest(value) {
  return crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
}

export async function requireOperatorAuth(request, env) {
  const expected = String(env?.OPERATOR_TOKEN ?? "");
  requireThat(expected.length >= 24, "OPERATOR_TOKEN is not configured", "CONFIGURATION_ERROR");
  const authorization = String(request.headers.get("authorization") ?? "");
  const match = authorization.match(/^Bearer\s+(.+)$/i);
  requireThat(match, "operator authorization required", "UNAUTHORIZED");
  const [providedHash, expectedHash] = await Promise.all([digest(match[1]), digest(expected)]);
  requireThat(crypto.subtle.timingSafeEqual(providedHash, expectedHash), "operator authorization invalid", "UNAUTHORIZED");
}
