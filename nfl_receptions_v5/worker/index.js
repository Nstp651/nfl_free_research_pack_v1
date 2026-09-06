import {NflReceptionsRun, routeRun, reply} from './run.js';
export {NflReceptionsRun};

const CANONICAL_PATHWAYS = new Set([
  'TEAM_PASS_OPPORTUNITY', 'ROUTES', 'TARGETS', 'CATCH_CONVERSION', 'QB',
  'PERSONNEL', 'DEFENSE', 'WEATHER', 'ROLE', 'AVAILABILITY', 'SYSTEM', 'OTHER'
]);

function canonicalModelPathway(value) {
  const raw = String(value || '').trim().toUpperCase().replace(/[^A-Z0-9]+/g, '_').replace(/^_+|_+$/g, '');
  if (CANONICAL_PATHWAYS.has(raw)) return raw;
  if (/PASS|VOLUME|OPPORTUNIT/.test(raw)) return 'TEAM_PASS_OPPORTUNITY';
  if (/ROUTE/.test(raw)) return 'ROUTES';
  if (/TARGET/.test(raw)) return 'TARGETS';
  if (/CATCH|RECEPTION|CONVERSION/.test(raw)) return 'CATCH_CONVERSION';
  if (/QB|QUARTERBACK/.test(raw)) return 'QB';
  if (/PERSONNEL|ROSTER/.test(raw)) return 'PERSONNEL';
  if (/DEFEN|COVERAGE|CONCESSION|PRESSURE|PROTECTION/.test(raw)) return 'DEFENSE';
  if (/WEATHER|WIND|RAIN|SNOW/.test(raw)) return 'WEATHER';
  if (/ROLE|DEPLOYMENT|SNAP/.test(raw)) return 'ROLE';
  if (/AVAIL|INJUR|ACTIVE|INACTIVE|STATUS/.test(raw)) return 'AVAILABILITY';
  if (/SYSTEM|COACH|SCHEME|PLAY_CALL|PLAYCALL/.test(raw)) return 'SYSTEM';
  return 'OTHER';
}

async function normalizeCheckpointRequest(request) {
  const url = new URL(request.url);
  if (request.method !== 'POST' || !/^\/v1\/runs\/[a-f0-9]{64}\/research$/.test(url.pathname)) return request;
  const raw = await request.clone().text();
  if (!raw) return request;
  let body;
  try { body = JSON.parse(raw); } catch { return request; }
  const evidence = body?.context?.evidence;
  if (!Array.isArray(evidence)) return request;
  for (const item of evidence) {
    if (!item || typeof item !== 'object' || Array.isArray(item)) continue;
    if (!Object.prototype.hasOwnProperty.call(item, 'source_url')) item.source_url = null;
    if (!Object.prototype.hasOwnProperty.call(item, 'source_date')) item.source_date = null;
    item.model_pathway = canonicalModelPathway(item.model_pathway);
  }
  return new Request(request.url, {
    method: request.method,
    headers: request.headers,
    body: JSON.stringify(body),
  });
}

export default {
  async fetch(request, env = {}) {
    const url = new URL(request.url);
    if (url.pathname === '/health') {
      return reply({
        ok: Boolean(env.NFL_RECEPTIONS_RUNS),
        service: 'NFL_RECEPTIONS_PLATFORM_V5_CONTROL',
        version: '1.2.1',
        market_data: false,
        durable_state: Boolean(env.NFL_RECEPTIONS_RUNS),
        source_lock: 'CONTENT_SHA256',
        fixture_binding: 'SERVER_LOCKED',
        checkpoint_pathway_normalization: true,
        note: 'Health is pre-market and never accesses sportsbook data.'
      }, env.NFL_RECEPTIONS_RUNS ? 200 : 503);
    }
    const normalizedRequest = await normalizeCheckpointRequest(request);
    const run = await routeRun(normalizedRequest, env);
    if (run) return run;
    return reply({error: 'Not found', market_data: false}, 404);
  }
};
