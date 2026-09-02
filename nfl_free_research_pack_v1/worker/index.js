/** Read-only NFL research API. No odds provider, model execution or paid services. */
const DEFAULT_BASE = 'https://raw.githubusercontent.com/Nstp651/nfl_free_research_pack_v1/main/nfl_free_research_pack_v1/data';
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
      headers: {'user-agent': 'nfl-free-research-pack/1.1.1'},
      cf: {cacheTtl: 60, cacheEverything: true}});
    if (!res.ok) fail(502, `Research source unavailable (${res.status})`);
    const raw = await res.text();
    if (raw.length > 5_000_000) fail(502, 'Research source exceeds size limit');
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
    note: 'Refresh time is not proof that every upstream source has published new data.'};
}
function verifyManifest(m) {
  if (m.schema_version !== '1.1.0' || !Array.isArray(m.games) || !m.games.length ||
      !['PASS', 'PARTIAL'].includes(m.source_health?.status)) fail(502, 'Invalid research manifest');
  if (new Set(m.games.map(g => g.game_id)).size !== m.games.length) fail(502, 'Duplicate research fixture IDs');
}

export default {
  async fetch(request, env = {}) {
    if (request.method !== 'GET') return reply({error: 'GET requests only'}, 405);
    try {
      const url = new URL(request.url);
      const gameMatch = url.pathname.match(/^\/v1\/packs\/([0-9]{4}_[0-9]{2}_[A-Z0-9]{2,4}_[A-Z0-9]{2,4})$/);
      if (!['/health', '/v1/packs'].includes(url.pathname) && !gameMatch) return reply({error: 'Not found'}, 404);
      let season, week, offset, limit;
      if (url.pathname === '/v1/packs') {
        season = integer(url.searchParams.get('season'), 2000, 2100);
        week = integer(url.searchParams.get('week'), 1, 18);
      }
      if (gameMatch) {
        offset = integer(url.searchParams.get('offset'), 0, 10000, 0);
        limit = integer(url.searchParams.get('limit'), 1, 20, 10);
        const rev = url.searchParams.get('revision');
        if (rev !== null && !/^[a-f0-9]{16}$/.test(rev)) fail(400, 'Invalid revision');
      }
      const base = (env.DATA_BASE_URL || DEFAULT_BASE).replace(/\/+$/, '');
      if (!base.startsWith('https://')) fail(500, 'Research source must use HTTPS');
      const manifest = await readJson(`${base}/manifest.json`);
      verifyManifest(manifest);
      const freshnessInfo = freshness(manifest);
      if (url.pathname === '/health') {
        const ok = freshnessInfo.source_refresh_status === 'RECENT';
        return reply({ok, service: 'NFL_FREE_RESEARCH_PACK', version: '1.1.1', market_data: false,
          fixture_count: manifest.games.length, source_health: manifest.source_health,
          freshness: freshnessInfo}, ok ? 200 : 503);
      }
      if (url.pathname === '/v1/packs') {
        const games = manifest.games.filter(g => g.season === season && g.week === week);
        return reply({schema_version: manifest.schema_version, market_data: false,
          season, week, games, source_health: manifest.source_health,
          freshness: freshnessInfo, attribution: manifest.attribution});
      }
      const gameId = gameMatch[1];
      const entry = manifest.games.find(g => g.game_id === gameId);
      if (!entry) return reply({error: 'Fixture not in the published active-week manifest', game_id: gameId}, 404);
      const requestedRevision = url.searchParams.get('revision');
      if (requestedRevision && requestedRevision !== entry.pack_revision)
        return reply({error: 'Research pack changed; restart at offset 0', game_id: gameId}, 409);
      const pack = await readJson(`${base}/games/${entry.season}/${gameId}.json`);
      if (pack.schema_version !== '1.1.0' || pack.game_id !== gameId ||
          pack.fixture?.home_team !== entry.home_team || pack.fixture?.away_team !== entry.away_team ||
          pack.fixture?.week !== entry.week || pack.fixture?.season !== entry.season || !Array.isArray(pack.players))
        fail(502, 'Research fixture or schema mismatch');
      if (pack.pack_revision !== entry.pack_revision)
        return reply({error: 'Research snapshot updating; retry from offset 0', game_id: gameId}, 503);
      if (offset > pack.players.length) fail(400, 'Offset exceeds player count');
      const {players, ...context} = pack;
      let count = Math.min(limit, players.length - offset);
      let result;
      do {
        result = {...context, market_data: false, freshness: freshnessInfo,
          players: players.slice(offset, offset + count),
          pagination: {offset, returned: count, total_players: players.length,
            next_offset: offset + count < players.length ? offset + count : null,
            revision: pack.pack_revision}};
        if (JSON.stringify(result).length < MAX_RESPONSE_CHARS) return reply(result);
        count -= 1;
      } while (count >= 1);
      fail(502, 'A research record exceeds the Action response limit');
    } catch (error) {
      return reply({error: error.status ? error.message : 'Research service temporarily unavailable'}, error.status || 502);
    }
  },
};
