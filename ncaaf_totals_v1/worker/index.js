/** Read-only NCAA totals research API. No odds provider, betting lines or model execution. */
const DEFAULT_BASE = 'https://raw.githubusercontent.com/Nstp651/nfl_free_research_pack_v1/main/ncaaf_totals_v1/data';
const MAX_RESPONSE_CHARS = 90000;
const MAX_AGE_HOURS = 36;

function reply(value, status = 200) {
  return new Response(JSON.stringify(value), {status, headers: {
    'content-type': 'application/json; charset=utf-8',
    'cache-control': status === 200 ? 'public, max-age=60' : 'no-store',
    'access-control-allow-origin': '*',
  }});
}
function fail(status, message) { const e = new Error(message); e.status = status; throw e; }
function integer(value, min, max, fallback) {
  if (value === null && fallback !== undefined) return fallback;
  if (!/^\d+$/.test(value || '')) fail(400, 'Invalid integer parameter');
  const n = Number(value);
  if (!Number.isSafeInteger(n) || n < min || n > max) fail(400, 'Parameter outside allowed range');
  return n;
}
async function readJson(url) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 12000);
  try {
    const res = await fetch(url, {signal: controller.signal,
      headers: {'user-agent': 'ncaaf-totals-research-pack/0.1.0'},
      cf: {cacheTtl: 60, cacheEverything: true}});
    if (!res.ok) fail(502, `Research source unavailable (${res.status})`);
    const raw = await res.text();
    if (raw.length > 8_000_000) fail(502, 'Research source exceeds size limit');
    try { return JSON.parse(raw); } catch { fail(502, 'Research source returned invalid JSON'); }
  } finally { clearTimeout(timer); }
}
function freshness(manifest) {
  const checked = manifest.last_checked_at_utc || manifest.generated_at_utc;
  const ms = Date.parse(checked);
  if (!Number.isFinite(ms) || ms > Date.now() + 300000) fail(502, 'Invalid research timestamp');
  const hours = Math.max(0, (Date.now() - ms) / 3600000);
  return {last_checked_at_utc: checked, age_hours: Math.round(hours * 100) / 100,
    source_refresh_status: hours > MAX_AGE_HOURS ? 'STALE' : 'RECENT',
    note: 'Refresh time is not proof every upstream release contains newer football observations.'};
}
function verifyManifest(m) {
  if (m.schema_version !== '0.1.0' || !Array.isArray(m.slates) || !m.slates.length ||
      !['PASS', 'PARTIAL'].includes(m.source_health?.status)) fail(502, 'Invalid research manifest');
  if (new Set(m.slates.map(s => s.slate_id)).size !== m.slates.length) fail(502, 'Duplicate slate IDs');
  if (m.market_data !== false) fail(502, 'Market boundary violation');
}
function verifyNoMarketData(value) {
  if (value?.market_data !== false) fail(502, 'Market boundary violation');
}

export default {
  async fetch(request, env = {}) {
    if (request.method !== 'GET') return reply({error: 'GET requests only'}, 405);
    try {
      const url = new URL(request.url);
      const slateMatch = url.pathname.match(/^\/v1\/slates\/([0-9]{4}_[0-9]{2})$/);
      if (!['/health', '/v1/slates'].includes(url.pathname) && !slateMatch) return reply({error: 'Not found'}, 404);
      let season, week, offset, limit;
      if (url.pathname === '/v1/slates') {
        season = integer(url.searchParams.get('season'), 2000, 2100);
        week = integer(url.searchParams.get('week'), 0, 30);
      }
      if (slateMatch) {
        offset = integer(url.searchParams.get('offset'), 0, 1000, 0);
        limit = integer(url.searchParams.get('limit'), 1, 20, 8);
        const rev = url.searchParams.get('revision');
        if (rev !== null && !/^[a-f0-9]{16}$/.test(rev)) fail(400, 'Invalid revision');
      }
      const base = (env.DATA_BASE_URL || DEFAULT_BASE).replace(/\/+$/, '');
      if (!base.startsWith('https://')) fail(500, 'Research source must use HTTPS');
      const manifest = await readJson(`${base}/manifest.json`);
      verifyManifest(manifest);
      const freshnessInfo = freshness(manifest);

      if (url.pathname === '/health') {
        const ok = freshnessInfo.source_refresh_status === 'RECENT' && manifest.source_health?.failed_required?.length === 0;
        return reply({ok, service: 'NCAAF_TOTALS_RESEARCH_PACK', version: '0.1.0', market_data: false,
          slate_count: manifest.slates.length, fixture_count: manifest.fixture_count,
          source_health: manifest.source_health, freshness: freshnessInfo}, ok ? 200 : 503);
      }

      if (url.pathname === '/v1/slates') {
        const slates = manifest.slates.filter(s => s.season === season && s.week === week);
        return reply({schema_version: manifest.schema_version, market_data: false, season, week,
          slates, source_health: manifest.source_health, freshness: freshnessInfo,
          attribution: manifest.attribution, limitations: manifest.limitations || []});
      }

      const slateId = slateMatch[1];
      const entry = manifest.slates.find(s => s.slate_id === slateId);
      if (!entry) return reply({error: 'Slate not in the published active manifest', slate_id: slateId}, 404);
      const requestedRevision = url.searchParams.get('revision');
      if (requestedRevision && requestedRevision !== entry.pack_revision)
        return reply({error: 'Research pack changed; restart at offset 0', slate_id: slateId}, 409);
      const pack = await readJson(`${base}/slates/${entry.season}/${slateId}.json`);
      verifyNoMarketData(pack);
      if (pack.schema_version !== '0.1.0' || pack.slate_id !== slateId || pack.season !== entry.season ||
          pack.week !== entry.week || !Array.isArray(pack.games)) fail(502, 'Research slate or schema mismatch');
      if (pack.pack_revision !== entry.pack_revision)
        return reply({error: 'Research snapshot updating; retry from offset 0', slate_id: slateId}, 503);
      if (offset > pack.games.length) fail(400, 'Offset exceeds game count');

      const {games, ...context} = pack;
      let count = Math.min(limit, games.length - offset);
      let result;
      do {
        result = {...context, market_data: false, freshness: freshnessInfo,
          games: games.slice(offset, offset + count),
          pagination: {offset, returned: count, total_games: games.length,
            next_offset: offset + count < games.length ? offset + count : null,
            revision: pack.pack_revision}};
        if (JSON.stringify(result).length < MAX_RESPONSE_CHARS) return reply(result);
        count -= 1;
      } while (count >= 1);
      fail(502, 'A research game record exceeds the Action response limit');
    } catch (error) {
      return reply({error: error.status ? error.message : 'Research service temporarily unavailable'}, error.status || 502);
    }
  },
};
