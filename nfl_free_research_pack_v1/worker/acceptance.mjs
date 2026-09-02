/** Real-source acceptance. --base-url tests a deployed API; otherwise runs the
 * Worker handler locally against the public GitHub data (NOT a deployment test).
 * Usage: node worker/acceptance.mjs [--base-url https://...workers.dev] [--output report.json]
 */
import assert from 'node:assert/strict';
import {writeFile} from 'node:fs/promises';
import worker from './index.js';

const args = process.argv.slice(2);
const option = (name, fallback) => args.includes(name) ? args[args.indexOf(name) + 1] : fallback;
const base = option('--base-url', null)?.replace(/\/+$/, '');
const dataBase = option('--data-base-url', null);
const season = Number(option('--season', '2026'));
const week = Number(option('--week', '1'));
const report = {tested_at_utc: new Date().toISOString(),
  mode: base ? 'DEPLOYED_HTTP_API' : 'LOCAL_HANDLER_WITH_LIVE_GITHUB_SOURCE',
  deployment_verified: false, base_url: base, upstream_override: dataBase, season, week, games: []};
const forbidden = new Set(['odds', 'price', 'spread_line', 'total_line', 'home_moneyline',
  'away_moneyline', 'p_model', 'implied_probability', 'fantasy_points', 'fantasy_points_ppr']);
function checkKeys(value) {
  if (!value || typeof value !== 'object') return;
  for (const [key, child] of Object.entries(value)) {
    assert(!forbidden.has(key.toLowerCase()), `Forbidden field: ${key}`);
    checkKeys(child);
  }
}
async function request(path, expected = 200, method = 'GET') {
  const url = `${base || 'https://local-handler.invalid'}${path}`;
  const response = base ? await fetch(url, {method}) : await worker.fetch(new Request(url, {method}),
    dataBase ? {DATA_BASE_URL: dataBase} : {});
  const raw = await response.text();
  assert.equal(response.status, expected, `${path}: ${raw.slice(0, 400)}`);
  assert(raw.length < 90000, 'Response exceeds Action size budget');
  const body = JSON.parse(raw);
  checkKeys(body);
  return {body, chars: raw.length, bytes: Buffer.byteLength(raw)};
}

try {
  const health = (await request('/health')).body;
  assert.equal(health.ok, true);
  assert.equal(health.market_data, false);
  assert.equal(health.freshness.source_refresh_status, 'RECENT');
  report.health = health;
  const manifest = (await request(`/v1/packs?season=${season}&week=${week}`)).body;
  assert(manifest.games.length >= 2, 'Two real fixtures are required');
  assert.equal(manifest.market_data, false);
  assert.equal(new Set(manifest.games.map(g => g.game_id)).size, manifest.games.length);
  report.fixture_count = manifest.games.length;
  // Resolve actual fixture IDs from the manifest, never hard-code an ID.
  const preferred = [['NE', 'SEA'], ['SF', 'LA']];
  const selected = preferred.map(teams => manifest.games.find(g =>
    teams.includes(g.away_team) && teams.includes(g.home_team))).filter(Boolean);
  for (const game of manifest.games) {
    if (selected.length >= 2) break;
    if (!selected.includes(game)) selected.push(game);
  }
  for (const entry of selected) {
    const players = [], sizes = [], offsets = new Set();
    let offset = 0, expectedTotal, first;
    do {
      assert(!offsets.has(offset), 'Pagination loop');
      offsets.add(offset);
      const result = await request(`/v1/packs/${entry.game_id}?offset=${offset}&revision=${entry.pack_revision}`);
      const page = result.body;
      first ||= page;
      for (const key of ['season', 'week', 'away_team', 'home_team'])
        assert.equal(page.fixture[key], entry[key], `Fixture mismatch: ${key}`);
      assert.equal(page.game_id, entry.game_id);
      assert.equal(page.pack_revision, entry.pack_revision);
      assert.equal(page.pagination.revision, entry.pack_revision);
      assert.equal(page.pagination.offset, offset);
      assert.equal(page.players.length, page.pagination.returned);
      assert.equal(page.market_data, false);
      expectedTotal ??= page.pagination.total_players;
      assert.equal(page.pagination.total_players, expectedTotal);
      assert(page.players.length > 0, 'Empty page before completion');
      assert(page.data_state.current_season_data_through_week === null ||
        page.data_state.current_season_data_through_week < week, 'Look-ahead data');
      if (week === 1) {
        assert.equal(page.data_state.current_season_data_through_week, null);
        for (const player of page.players)
          assert(Object.values(player.current_season_to_date).every(v => v === null));
      }
      players.push(...page.players);
      sizes.push({chars: result.chars, bytes: result.bytes});
      const next = page.pagination.next_offset;
      assert(next === null || next === offset + page.players.length, 'Skipped player offset');
      offset = next;
    } while (offset !== null);
    assert.equal(players.length, expectedTotal);
    const ids = players.map(p => p.player_id || `${p.current_team}:${p.player_name}`);
    assert.equal(new Set(ids).size, players.length, 'Duplicate player');
    assert.deepEqual([...new Set(players.map(p => p.current_team))].sort(),
      [entry.away_team, entry.home_team].sort());
    await request(`/v1/packs/${entry.game_id}?revision=0000000000000000`, 409);
    report.games.push({game_id: entry.game_id, pack_revision: entry.pack_revision,
      fixture: first.fixture, total_players: players.length, pages: sizes.length,
      page_sizes: sizes, players_by_team: Object.fromEntries([entry.away_team, entry.home_team]
        .map(t => [t, players.filter(p => p.current_team === t).length])),
      rookies: players.filter(p => p.rookie_flag).map(p => p.player_name),
      transfers: players.filter(p => p.team_change_since_prior_season).map(p => p.player_name),
      missing_prior_ngs: players.filter(p => !p.historical?.[season - 1]?.next_gen_receiving).length,
      missing_prior_ftn: players.filter(p => !p.historical?.[season - 1]?.ftn_charting).length,
      source_receipt: first.source_receipt, statistical_cutoff: first.data_state});
  }
  await request('/health', 405, 'POST');
  await request(`/v1/packs?season=${season}&week=0`, 400);
  report.result = 'PASS';
  report.deployment_verified = Boolean(base);
} catch (error) {
  report.result = 'FAIL';
  report.error = error.message;
  process.exitCode = 1;
}
const text = JSON.stringify(report, null, 2) + '\n';
if (option('--output')) await writeFile(option('--output'), text);
console.log(text);
