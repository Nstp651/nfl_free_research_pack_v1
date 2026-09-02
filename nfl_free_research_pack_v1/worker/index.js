/**
 * Cloudflare Worker: NFL Free Research Pack API
 *
 * Required environment variable:
 *   DATA_BASE_URL
 * Example:
 *   https://raw.githubusercontent.com/YOUR_GITHUB_USERNAME/nfl-free-research-pack/main/data
 *
 * This Worker never reads sportsbook data.
 */

const JSON_HEADERS = {
  "content-type": "application/json; charset=utf-8",
  "cache-control": "public, max-age=120",
};

function j(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: JSON_HEADERS });
}

function validGameId(id) {
  return /^[0-9]{4}_[0-9]{2}_[A-Z0-9]{2,4}_[A-Z0-9]{2,4}$/.test(id || "");
}

async function fetchJson(url) {
  const r = await fetch(url, {
    headers: { "user-agent": "nfl-free-research-pack-worker/1.0" },
    cf: { cacheTtl: 180, cacheEverything: true },
  });
  if (!r.ok) return { ok: false, status: r.status, data: null };
  return { ok: true, status: r.status, data: await r.json() };
}

export default {
  async fetch(request, env) {
    try {
      const url = new URL(request.url);
      const base = (env.DATA_BASE_URL || "").replace(/\/+$/, "");
      if (!base) return j({ error: "DATA_BASE_URL is not configured" }, 500);

      if (url.pathname === "/health") {
        return j({
          ok: true,
          service: "NFL_FREE_RESEARCH_PACK",
          market_data: false,
          version: "1.1.0",
        });
      }

      if (url.pathname === "/v1/packs") {
        const season = url.searchParams.get("season");
        const week = url.searchParams.get("week");
        const res = await fetchJson(`${base}/manifest.json`);
        if (!res.ok) return j({ error: "manifest unavailable", upstream_status: res.status }, 502);

        let games = res.data.games || [];
        if (season) games = games.filter(g => String(g.season) === String(season));
        if (week) games = games.filter(g => String(g.week) === String(Number(week)));

        return j({
          schema_version: res.data.schema_version,
          generated_at_utc: res.data.generated_at_utc,
          market_data: false,
          games,
          source_status: res.data.source_status,
          attribution: res.data.attribution,
        });
      }

      const m = url.pathname.match(/^\/v1\/packs\/([^/]+)$/);
      if (m) {
        const gameId = decodeURIComponent(m[1]).toUpperCase();
        if (!validGameId(gameId)) return j({ error: "invalid game_id format" }, 400);
        const season = gameId.slice(0, 4);
        const res = await fetchJson(`${base}/games/${season}/${gameId}.json`);
        if (!res.ok) {
          if (res.status === 404) return j({ error: "research pack not found", game_id: gameId }, 404);
          return j({ error: "research pack upstream unavailable", upstream_status: res.status }, 502);
        }
        return j(res.data);
      }

      return j({
        error: "not found",
        routes: [
          "GET /health",
          "GET /v1/packs?season=2026&week=1",
          "GET /v1/packs/{game_id}"
        ],
      }, 404);
    } catch (err) {
      return j({ error: "internal error", detail: String(err?.message || err) }, 500);
    }
  },
};
