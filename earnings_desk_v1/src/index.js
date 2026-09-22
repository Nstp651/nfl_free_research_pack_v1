import { requireOperatorAuth } from "./auth.js";
import { calibrationDashboard } from "./calibration.js";
import { requireThat } from "./canonical.js";
import { closeRun, listOpenPositions, recordExecution, recordOutcome, settlePosition, settlementGuidance } from "./execution.js";
import { getLegacyEvent, listLegacyEvents } from "./legacy-events.js";
import { riskConfigFromEnv } from "./risk-config.js";
import { createRun, dispositionEvent, freezeEvent, getFreezeArtifact, getRunState, ingestHistory, ingestIvObservations, storeMarketInput, submitResearch, valueRun } from "./run-service.js";

const CORS = {
  "access-control-allow-origin": "*",
  "access-control-allow-methods": "GET,POST,OPTIONS",
  "access-control-allow-headers": "authorization,content-type"
};

function json(value, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store", ...CORS }
  });
}

async function body(request, maxBytes = 500_000) {
  const length = Number(request.headers.get("content-length") ?? 0);
  requireThat(!Number.isFinite(length) || length <= maxBytes, "request body too large");
  const text = await request.text();
  requireThat(text.length <= maxBytes, "request body too large");
  try {
    return JSON.parse(text);
  } catch {
    requireThat(false, "request body must be valid JSON");
  }
}

function failure(error, request) {
  const code = error?.code ?? "INTERNAL_ERROR";
  const status = code === "NOT_FOUND" ? 404 : code === "UNAUTHORIZED" ? 401 : code === "CONFIGURATION_ERROR" ? 503 : code === "DATA_BLOCKED" || code === "MARKET_CONTAMINATION" ? 422 : code === "INTERNAL_ERROR" ? 500 : 400;
  const payload = { ok: false, status: code === "DATA_BLOCKED" ? "DATA BLOCKED / PASS" : code, error: error instanceof Error ? error.message : "Unknown error" };
  console.error(JSON.stringify({ message: "earnings desk request failed", method: request.method, path: new URL(request.url).pathname, code, error: payload.error }));
  return json(payload, status);
}

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: CORS });
    const url = new URL(request.url);
    try {
      if (request.method === "GET" && url.pathname === "/health") {
        const schema = env?.DB
          ? await env.DB.prepare("SELECT version, applied_at FROM earnings_schema_versions ORDER BY applied_at DESC LIMIT 1").first().catch(() => null)
          : null;
        return json({
          service: "kj-event-desk",
          status: "ok",
          mode: env?.ENVIRONMENT,
          modelVersion: env?.MODEL_VERSION,
          liveTradingEnabled: false,
          earningsDesk: {
            version: "1.0.0",
            mode: String(env?.EARNINGS_DESK_MODE ?? "SHADOW"),
            d1_bound: Boolean(env?.DB),
            schema: schema ?? "MIGRATION_REQUIRED",
            automated_broker_execution: false
          }
        });
      }
      if (request.method === "GET" && url.pathname === "/v1/events") return json(await listLegacyEvents(request, env.DB));
      const legacyEventMatch = url.pathname.match(/^\/v1\/events\/([a-zA-Z0-9_-]+)$/);
      if (request.method === "GET" && legacyEventMatch) return json(await getLegacyEvent(legacyEventMatch[1], env.DB));
      await requireOperatorAuth(request, env);
      requireThat(env?.DB, "DB binding unavailable", "CONFIGURATION_ERROR");
      const riskConfig = riskConfigFromEnv(env);

      if (request.method === "POST" && url.pathname === "/v1/earnings/history/batches") return json(await ingestHistory(env.DB, await body(request)));
      if (request.method === "POST" && url.pathname === "/v1/earnings/iv-observations") return json(await ingestIvObservations(env.DB, await body(request)));
      if (request.method === "POST" && url.pathname === "/v1/earnings/runs") return json(await createRun(env.DB, await body(request), riskConfig), 201);
      if (request.method === "GET" && url.pathname === "/v1/earnings/positions/open") return json({ positions: await listOpenPositions(env.DB) });
      if (request.method === "GET" && url.pathname === "/v1/earnings/calibration") return json(await calibrationDashboard(env.DB));

      let match = url.pathname.match(/^\/v1\/earnings\/runs\/([a-f0-9]{64})$/);
      if (request.method === "GET" && match) return json(await getRunState(env.DB, match[1]));

      match = url.pathname.match(/^\/v1\/earnings\/runs\/([a-f0-9]{64})\/research\/([^/]+)$/);
      if (request.method === "POST" && match) return json(await submitResearch(env.DB, match[1], decodeURIComponent(match[2]), await body(request)), 201);

      match = url.pathname.match(/^\/v1\/earnings\/runs\/([a-f0-9]{64})\/freeze\/([^/]+)$/);
      if (request.method === "POST" && match) return json(await freezeEvent(env.DB, match[1], decodeURIComponent(match[2])), 201);
      if (request.method === "GET" && match) return json(await getFreezeArtifact(env.DB, match[1], decodeURIComponent(match[2])));

      match = url.pathname.match(/^\/v1\/earnings\/runs\/([a-f0-9]{64})\/market-inputs\/([^/]+)$/);
      if (request.method === "POST" && match) return json(await storeMarketInput(env.DB, match[1], decodeURIComponent(match[2]), await body(request), riskConfig), 201);

      match = url.pathname.match(/^\/v1\/earnings\/runs\/([a-f0-9]{64})\/disposition\/([^/]+)$/);
      if (request.method === "POST" && match) return json(await dispositionEvent(env.DB, match[1], decodeURIComponent(match[2]), await body(request)), 201);

      match = url.pathname.match(/^\/v1\/earnings\/runs\/([a-f0-9]{64})\/value$/);
      if (request.method === "POST" && match) {
        const input = await body(request);
        return json(await valueRun(env.DB, match[1], input, riskConfig), 201);
      }

      match = url.pathname.match(/^\/v1\/earnings\/runs\/([a-f0-9]{64})\/positions$/);
      if (request.method === "POST" && match) return json(await recordExecution(env.DB, match[1], await body(request), riskConfig), 201);

      match = url.pathname.match(/^\/v1\/earnings\/positions\/([^/]+)\/(settlement-guidance|settle)$/);
      if (request.method === "POST" && match) {
        const input = await body(request);
        return json(match[2] === "settle" ? await settlePosition(env.DB, match[1], input, riskConfig) : await settlementGuidance(env.DB, match[1], input, riskConfig));
      }

      match = url.pathname.match(/^\/v1\/earnings\/runs\/([a-f0-9]{64})\/outcomes\/([^/]+)$/);
      if (request.method === "POST" && match) return json(await recordOutcome(env.DB, match[1], decodeURIComponent(match[2]), await body(request)), 201);

      match = url.pathname.match(/^\/v1\/earnings\/runs\/([a-f0-9]{64})\/close$/);
      if (request.method === "POST" && match) {
        const input = await body(request);
        return json(await closeRun(env.DB, match[1], input.operator_minutes));
      }
      return json({ ok: false, error: "Not found" }, 404);
    } catch (error) {
      return failure(error, request);
    }
  },
  async scheduled(_controller, env) {
    console.log(JSON.stringify({
      level: "info",
      event: "scheduled_scan_skipped",
      environment: env.ENVIRONMENT,
      reason: "No automated source adapter is enabled until source terms are approved",
      timestamp: new Date().toISOString()
    }));
  }
};
