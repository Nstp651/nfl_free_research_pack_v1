import test from 'node:test';
import assert from 'node:assert/strict';
import worker from './index.js';
const gid = '2026_01_AA_BB';
const revision = '0123456789abcdef';
const entry = {game_id: gid, season: 2026, week: 1, away_team: 'AA', home_team: 'BB', pack_revision: revision};
const pack = {schema_version: '1.1.0', game_id: gid, pack_revision: revision,
  fixture: {...entry}, players: Array.from({length: 25}, (_,i) => ({player_id: String(i), note: 'x'.repeat(6000)}))};
const manifest = {schema_version: '1.1.0', games: [entry], source_health: {status: 'PARTIAL'}, last_checked_at_utc: new Date().toISOString()};
const originalFetch = globalThis.fetch;
async function call(path, changes = {}, method = 'GET') {
  globalThis.fetch = async url => {
    if (changes.error) return new Response('upstream failed', {status: 500});
    if (changes.invalidJson) return new Response('<html>');
    const value = String(url).endsWith('manifest.json') ? (changes.manifest || manifest) : (changes.pack || pack);
    return new Response(JSON.stringify(value));
  };
  try {
    const res = await worker.fetch(new Request('https://test.invalid'+path, {method}));
    const raw = await res.text();
    return {status: res.status, data: JSON.parse(raw), chars: raw.length};
  } finally { globalThis.fetch = originalFetch; }
}
test('pages return every player below the Action limit', async () => {
  const received = [];
  let offset = 0;
  while (offset !== null) {
    const res = await call(`/v1/packs/${gid}?offset=${offset}&limit=20&revision=${revision}`);
    assert.equal(res.status, 200);
    assert.ok(res.chars < 90000);
    received.push(...res.data.players.map(p=>p.player_id));
    offset = res.data.pagination.next_offset;
  }
  assert.deepEqual(received, pack.players.map(p=>p.player_id));
});
test('changed revision prevents mixing pages', async () => {
  assert.equal((await call(`/v1/packs/${gid}?revision=ffffffffffffffff`)).status, 409);
});
test('updating snapshot fails instead of mixing files', async () => {
  assert.equal((await call(`/v1/packs/${gid}`, {pack: {...pack, pack_revision:'ffffffffffffffff'}})).status, 503);
});
test('fixture mismatch fails', async () => {
  assert.equal((await call(`/v1/packs/${gid}`, {pack:{...pack, fixture:{...entry, home_team:'CC'}}})).status, 502);
});
test('unknown fixture is not served from old archives', async () => {
  assert.equal((await call('/v1/packs/2026_02_AA_BB')).status, 404);
});
test('source outage and malformed JSON fail visibly', async () => {
  assert.equal((await call('/health', {error:true})).status, 502);
  assert.equal((await call('/health', {invalidJson:true})).status, 502);
});
test('health tests upstream and marks stale refresh', async () => {
  assert.equal((await call('/health')).data.ok, true);
  const result = await call('/health', {manifest:{...manifest,last_checked_at_utc:'2020-01-01T00:00:00Z'}});
  assert.equal(result.status,503);
  assert.equal(result.data.freshness.source_refresh_status,'STALE');
});
test('invalid parameter and write methods rejected', async () => {
  assert.equal((await call('/v1/packs?season=2026&week=0')).status,400);
  assert.equal((await call(`/v1/packs/${gid}?offset=-1`)).status,400);
  assert.equal((await call('/health', {}, 'POST')).status,405);
});
test('list carries source health', async () => {
  const result = await call('/v1/packs?season=2026&week=1');
  assert.equal(result.data.games.length,1);
  assert.equal(result.data.source_health.status,'PARTIAL');
});
