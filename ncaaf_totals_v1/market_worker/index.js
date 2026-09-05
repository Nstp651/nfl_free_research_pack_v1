/**
 * NCAA Football full-game totals market gateway.
 * POST-FREEZE ONLY. Australian region, totals market only.
 * One upstream sport-board call covers the whole NCAAF slate (1 region x 1 market).
 *
 * V0.1.1 intentionally applies commence-time bounds LOCALLY after retrieving the
 * current NCAAF board. This avoids upstream 4xx failures caused by time-filter
 * parameters while preserving the exact frozen-slate window at the Worker edge.
 */
const SPORT = 'americanfootball_ncaaf';
const ODDS_HOST = 'https://api.the-odds-api.com';
const MAX_RESPONSE_CHARS = 90000;
const MAX_UPSTREAM_CHARS = 8_000_000;
const CACHE_TTL_SECONDS = 45;
const VERSION = '0.1.1';

function reply(value, status = 200) {
  return new Response(JSON.stringify(value), {status, headers: {
    'content-type': 'application/json; charset=utf-8',
    'cache-control': 'no-store',
    'access-control-allow-origin': '*',
  }});
}
function fail(status, message, details = {}) {
  const e = new Error(message);
  e.status = status;
  Object.assign(e, details);
  throw e;
}
function integer(value, min, max, fallback) {
  if (value === null && fallback !== undefined) return fallback;
  if (!/^\d+$/.test(value || '')) fail(400, 'Invalid integer parameter');
  const n = Number(value);
  if (!Number.isSafeInteger(n) || n < min || n > max) fail(400, 'Parameter outside allowed range');
  return n;
}
function iso(value, field) {
  if (value === null) return null;
  const ms = Date.parse(value);
  if (!Number.isFinite(ms)) fail(400, `Invalid ${field} timestamp`);
  return new Date(ms).toISOString();
}
function fnv16(text) {
  let a = 0x811c9dc5, b = 0x9e3779b9;
  for (let i = 0; i < text.length; i++) {
    const c = text.charCodeAt(i);
    a ^= c; a = Math.imul(a, 0x01000193) >>> 0;
    b ^= c + (i & 255); b = Math.imul(b, 0x01000193) >>> 0;
  }
  return a.toString(16).padStart(8, '0') + b.toString(16).padStart(8, '0');
}
function number(v) {
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}
function normalizeBoard(raw) {
  if (!Array.isArray(raw)) fail(502, 'Odds source returned invalid board');
  const games = [];
  for (const g of raw) {
    if (g?.sport_key !== SPORT || !g?.id || !g?.home_team || !g?.away_team || !g?.commence_time) continue;
    const bookmakers = [];
    for (const book of Array.isArray(g.bookmakers) ? g.bookmakers : []) {
      const market = (Array.isArray(book.markets) ? book.markets : []).find(m => m?.key === 'totals');
      if (!market || !Array.isArray(market.outcomes)) continue;
      const outcomes = market.outcomes
        .filter(o => (o?.name === 'Over' || o?.name === 'Under') && number(o?.price) !== null && number(o?.point) !== null)
        .map(o => ({name: o.name, price: o.price, point: o.point}));
      if (!outcomes.length) continue;
      bookmakers.push({
        key: String(book.key || ''), title: String(book.title || book.key || ''),
        last_update: book.last_update || market.last_update || null,
        totals: outcomes,
      });
    }
    games.push({
      event_id: String(g.id), home_team: String(g.home_team), away_team: String(g.away_team),
      commence_time: String(g.commence_time), bookmakers,
    });
  }
  games.sort((a,b) => a.commence_time.localeCompare(b.commence_time) || a.event_id.localeCompare(b.event_id));
  return games;
}
function filterWindow(games, from, to) {
  const fromMs = from ? Date.parse(from) : null;
  const toMs = to ? Date.parse(to) : null;
  return games.filter(g => {
    const ms = Date.parse(g.commence_time);
    if (!Number.isFinite(ms)) return false;
    if (fromMs !== null && ms < fromMs) return false;
    if (toMs !== null && ms > toMs) return false;
    return true;
  });
}
function parseUpstreamError(rawText) {
  try {
    const value = JSON.parse(rawText);
    return {
      code: typeof value?.error_code === 'string' ? value.error_code : null,
      message: typeof value?.message === 'string' ? value.message : null,
    };
  } catch {
    return {code: null, message: null};
  }
}
async function fetchBoard(env, from, to) {
  if (!env.ODDS_API_KEY) fail(503, 'ODDS_API_KEY is not configured');

  // Deliberately do NOT send commenceTimeFrom/commenceTimeTo upstream.
  // The upstream current-board endpoint already returns current/live/upcoming
  // NCAAF events. We filter the exact frozen window locally after normalization.
  const q = new URLSearchParams({
    apiKey: env.ODDS_API_KEY,
    regions: 'au', markets: 'totals', oddsFormat: 'decimal', dateFormat: 'iso',
  });
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 12000);
  try {
    const res = await fetch(`${ODDS_HOST}/v4/sports/${SPORT}/odds?${q}`, {
      signal: controller.signal,
      headers: {'user-agent': `nick-ncaaf-totals-market/${VERSION}`},
      cf: {cacheTtl: CACHE_TTL_SECONDS, cacheEverything: true},
    });
    const rawText = await res.text();
    if (!res.ok) {
      const upstream = parseUpstreamError(rawText);
      const status = res.status === 429 ? 429 : 502;
      fail(status, `Odds source unavailable (${res.status})`, {
        upstream_status: res.status,
        upstream_code: upstream.code,
        upstream_message: upstream.message,
      });
    }
    if (rawText.length > MAX_UPSTREAM_CHARS) fail(502, 'Odds source response exceeds size limit');
    let raw;
    try { raw = JSON.parse(rawText); } catch { fail(502, 'Odds source returned invalid JSON'); }
    const allGames = normalizeBoard(raw);
    const games = filterWindow(allGames, from, to);
    const canonical = JSON.stringify(games);
    return {
      games,
      board_revision: fnv16(canonical),
      retrieved_at: new Date().toISOString(),
      quota: {
        requests_remaining: res.headers.get('x-requests-remaining'),
        requests_used: res.headers.get('x-requests-used'),
        requests_last: res.headers.get('x-requests-last'),
      },
    };
  } finally { clearTimeout(timer); }
}

export default {
  async fetch(request, env = {}) {
    if (request.method !== 'GET') return reply({error: 'GET requests only'}, 405);
    try {
      const url = new URL(request.url);
      if (!['/health', '/v1/totals'].includes(url.pathname)) return reply({error: 'Not found'}, 404);
      if (url.pathname === '/health') {
        return reply({
          ok: Boolean(env.ODDS_API_KEY), service: 'NCAAF_TOTALS_MARKET_GATEWAY', version: VERSION,
          sport_key: SPORT, region: 'au', market_group: 'ncaaf-totals', market_key: 'totals',
          configured: Boolean(env.ODDS_API_KEY),
          note: 'Health performs no Odds API market request and consumes no market-board credit.',
        }, env.ODDS_API_KEY ? 200 : 503);
      }

      const offset = integer(url.searchParams.get('offset'), 0, 1000, 0);
      const limit = integer(url.searchParams.get('limit'), 1, 25, 15);
      const from = iso(url.searchParams.get('commence_from'), 'commence_from');
      const to = iso(url.searchParams.get('commence_to'), 'commence_to');
      if (from && to && Date.parse(from) > Date.parse(to)) fail(400, 'commence_from must be <= commence_to');
      const requestedRevision = url.searchParams.get('revision');
      if (requestedRevision !== null && !/^[a-f0-9]{16}$/.test(requestedRevision)) fail(400, 'Invalid revision');

      const board = await fetchBoard(env, from, to);
      if (requestedRevision && requestedRevision !== board.board_revision) {
        return reply({error: 'Market board changed; restart at offset 0', board_revision: board.board_revision}, 409);
      }
      if (offset > board.games.length) fail(400, 'Offset exceeds game count');
      let count = Math.min(limit, board.games.length - offset);
      let result;
      do {
        result = {
          service: 'NCAAF_TOTALS_MARKET_GATEWAY', version: VERSION,
          sport_key: SPORT, region: 'au', market_group: 'ncaaf-totals', market_key: 'totals',
          retrieved_at: board.retrieved_at, board_revision: board.board_revision,
          filter: {commence_from: from, commence_to: to}, quota: board.quota,
          games: board.games.slice(offset, offset + count),
          pagination: {
            offset, returned: count, total_games: board.games.length,
            next_offset: offset + count < board.games.length ? offset + count : null,
            revision: board.board_revision,
          },
        };
        if (JSON.stringify(result).length < MAX_RESPONSE_CHARS) return reply(result);
        count -= 1;
      } while (count >= 1);
      fail(502, 'A market game record exceeds the Action response limit');
    } catch (error) {
      const status = error.status || (error?.name === 'AbortError' ? 504 : 502);
      const body = {error: error.status ? error.message : (status === 504 ? 'Odds source timed out' : 'Market service temporarily unavailable')};
      if (error.upstream_status) body.upstream_status = error.upstream_status;
      if (error.upstream_code) body.upstream_code = error.upstream_code;
      if (error.upstream_message) body.upstream_message = error.upstream_message;
      return reply(body, status);
    }
  },
};