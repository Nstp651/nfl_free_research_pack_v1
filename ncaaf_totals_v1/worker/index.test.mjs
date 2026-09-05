import test from 'node:test';
import assert from 'node:assert/strict';
import worker from './index.js';

const sid = '2026_02';
const revision = '0123456789abcdef';
const games = Array.from({length: 55}, (_,i) => ({game_id: String(1000+i), home_team: `H${i}`, away_team: `A${i}`, note: 'x'.repeat(5000)}));
const entry = {slate_id: sid, season: 2026, week: 2, game_count: games.length, pack_revision: revision};
const pack = {schema_version:'0.1.0', market_data:false, slate_id:sid, season:2026, week:2, pack_revision:revision, games};
const manifest = {schema_version:'0.1.0', market_data:false, slates:[entry], fixture_count:games.length,
  source_health:{status:'PASS', failed_required:[]}, last_checked_at_utc:new Date().toISOString()};
const originalFetch = globalThis.fetch;

async function call(path, changes = {}, method = 'GET') {
  globalThis.fetch = async url => {
    if (changes.error) return new Response('upstream failed', {status:500});
    if (changes.invalidJson) return new Response('<html>');
    const value = String(url).endsWith('manifest.json') ? (changes.manifest || manifest) : (changes.pack || pack);
    return new Response(JSON.stringify(value));
  };
  try {
    const res = await worker.fetch(new Request('https://test.invalid'+path, {method}));
    const raw = await res.text();
    return {status:res.status, data:JSON.parse(raw), chars:raw.length};
  } finally { globalThis.fetch = originalFetch; }
}

test('pages retrieve entire slate at one revision below Action limit', async () => {
  const received=[]; let offset=0;
  while (offset !== null) {
    const res=await call(`/v1/slates/${sid}?offset=${offset}&limit=20&revision=${revision}`);
    assert.equal(res.status,200); assert.ok(res.chars < 90000);
    received.push(...res.data.games.map(g=>g.game_id));
    offset=res.data.pagination.next_offset;
  }
  assert.deepEqual(received,games.map(g=>g.game_id));
});

test('changed revision prevents mixed slate pages', async()=>{
  assert.equal((await call(`/v1/slates/${sid}?revision=ffffffffffffffff`)).status,409);
});
test('updating snapshot fails visibly', async()=>{
  assert.equal((await call(`/v1/slates/${sid}`, {pack:{...pack,pack_revision:'ffffffffffffffff'}})).status,503);
});
test('market boundary violation fails', async()=>{
  assert.equal((await call(`/v1/slates/${sid}`, {pack:{...pack,market_data:true}})).status,502);
  assert.equal((await call('/health', {manifest:{...manifest,market_data:true}})).status,502);
});
test('unknown slate is not served', async()=>{
  assert.equal((await call('/v1/slates/2026_03')).status,404);
});
test('health marks stale refresh', async()=>{
  assert.equal((await call('/health')).data.ok,true);
  const res=await call('/health',{manifest:{...manifest,last_checked_at_utc:'2020-01-01T00:00:00Z'}});
  assert.equal(res.status,503); assert.equal(res.data.freshness.source_refresh_status,'STALE');
});
test('required source failure makes health non-ok', async()=>{
  const res=await call('/health',{manifest:{...manifest,source_health:{status:'PARTIAL',failed_required:['cfb_schedules']}}});
  assert.equal(res.status,503); assert.equal(res.data.ok,false);
});
test('invalid parameters and writes rejected', async()=>{
  assert.equal((await call('/v1/slates?season=2026&week=-1')).status,400);
  assert.equal((await call(`/v1/slates/${sid}?offset=-1`)).status,400);
  assert.equal((await call('/health',{},'POST')).status,405);
});
