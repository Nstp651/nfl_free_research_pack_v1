import test from 'node:test';
import assert from 'node:assert/strict';
import worker from './index.js';

const sid = '2026_02';
const revision = '0123456789abcdef';
const qrevision = 'fedcba9876543210';
const games = Array.from({length: 55}, (_,i) => ({game_id: String(1000+i), home_team: `H${i}`, away_team: `A${i}`, note: 'x'.repeat(5000)}));
const makeGrid = () => Array.from({length:162},(_,j)=>{
  const line=20+j/2;
  const under=0.02+j*0.004;
  const push=Math.abs(line-Math.round(line))<1e-9 ? 0.002 : 0;
  const over=1-under-push;
  return {line,over,push,under};
});
const qgames = Array.from({length:55},(_,i)=>({game_id:String(1000+i),expected_total_qbase:55+i/10,probability_grid:makeGrid()}));
const entry = {slate_id: sid, season: 2026, week: 2, game_count: games.length, pack_revision: revision};
const pack = {schema_version:'0.1.0', market_data:false, slate_id:sid, season:2026, week:2, pack_revision:revision, games};
const qslate = {schema_version:'0.1.0',probability_schema_version:'0.2.0',integer_line_method:'continuity_corrected_discrete_mass',
  supported_total_grid:{min:20,max:100.5,step:0.5},market_data:false,slate_id:sid,season:2026,week:2,
  research_pack_revision:revision,qbase_model_name:'Nick NCAA Totals QBASE',qbase_model_version:'0.1.0',
  qbase_model_sha256:'a'.repeat(64),qbase_revision:qrevision,games:qgames};
const manifest = {schema_version:'0.1.0', market_data:false, slates:[entry], fixture_count:games.length,
  source_health:{status:'PASS', failed_required:[]}, last_checked_at_utc:new Date().toISOString()};
const qbase = {model_name:'Nick NCAA Totals QBASE',model_version:'0.1.0',market_data:false,
  features:['x'],coefficients:[1],imputer_medians:[0],scaler_mean:[0],scaler_scale:[1],
  walk_forward:{residual_distribution:{ALL:{n:100,residual_sd:16,quantile_levels:[0.01,0.99],residual_quantiles:[-40,40]}}}};
const originalFetch = globalThis.fetch;

async function call(path, changes = {}, method = 'GET') {
  globalThis.fetch = async url => {
    if (changes.error) return new Response('upstream failed', {status:500});
    if (changes.invalidJson) return new Response('<html>');
    const u=String(url);
    const value = u.includes('qbase_v0.1.0.json') ? (changes.qbase || qbase) :
      (u.includes('/model/slates/') ? (changes.qslate || qslate) :
      (u.endsWith('manifest.json') ? (changes.manifest || manifest) : (changes.pack || pack)));
    return new Response(JSON.stringify(value));
  };
  try {
    const res = await worker.fetch(new Request('https://test.invalid'+path, {method}));
    const raw = await res.text();
    return {status:res.status, data:JSON.parse(raw), chars:raw.length};
  } finally { globalThis.fetch = originalFetch; }
}

test('pages retrieve entire research slate at one revision below Action limit', async () => {
  const received=[]; let offset=0;
  while (offset !== null) {
    const res=await call(`/v1/slates/${sid}?offset=${offset}&limit=20&revision=${revision}`);
    assert.equal(res.status,200); assert.ok(res.chars < 90000);
    received.push(...res.data.games.map(g=>g.game_id));
    offset=res.data.pagination.next_offset;
  }
  assert.deepEqual(received,games.map(g=>g.game_id));
});

test('serves only a validated market-blind QBASE artifact', async()=>{
  const r=await call('/v1/model/qbase');
  assert.equal(r.status,200); assert.equal(r.data.market_data,false); assert.equal(r.data.model_version,'0.1.0');
  assert.ok(r.data.served_at_utc);
  assert.equal((await call('/v1/model/qbase',{qbase:{...qbase,market_data:true}})).status,502);
  assert.equal((await call('/v1/model/qbase',{qbase:{...qbase,coefficients:[1,2]}})).status,502);
});

test('pages V1.1 QBASE slate at one revision and response limit', async()=>{
  const received=[]; let offset=0;
  while(offset!==null){
    const r=await call(`/v1/qbase/${sid}?offset=${offset}&limit=20&revision=${qrevision}`);
    assert.equal(r.status,200); assert.ok(r.chars<90000); assert.equal(r.data.research_pack_revision,revision);
    assert.equal(r.data.probability_schema_version,'0.2.0');
    received.push(...r.data.games.map(g=>g.game_id)); offset=r.data.pagination.next_offset;
  }
  assert.deepEqual(received,qgames.map(g=>g.game_id));
  assert.equal((await call(`/v1/qbase/${sid}?revision=${revision}`)).status,409);
  assert.equal((await call(`/v1/qbase/${sid}`,{qslate:{...qslate,market_data:true}})).status,502);
});

test('rejects malformed push probability grids', async()=>{
  const badHalf=structuredClone(qslate); badHalf.games[0].probability_grid[1].push=0.01; badHalf.games[0].probability_grid[1].over-=0.01;
  assert.equal((await call(`/v1/qbase/${sid}`,{qslate:badHalf})).status,502);
  const badPartition=structuredClone(qslate); badPartition.games[0].probability_grid[0].push=0.2;
  assert.equal((await call(`/v1/qbase/${sid}`,{qslate:badPartition})).status,502);
  assert.equal((await call(`/v1/qbase/${sid}`,{qslate:{...qslate,probability_schema_version:'0.1.0'}})).status,502);
});

test('changed revision prevents mixed research slate pages', async()=>{
  assert.equal((await call(`/v1/slates/${sid}?revision=ffffffffffffffff`)).status,409);
});
test('updating snapshot fails visibly', async()=>{
  assert.equal((await call(`/v1/slates/${sid}`, {pack:{...pack,pack_revision:'ffffffffffffffff'}})).status,503);
});
test('market boundary violation fails', async()=>{
  assert.equal((await call(`/v1/slates/${sid}`, {pack:{...pack,market_data:true}})).status,502);
  assert.equal((await call('/health', {manifest:{...manifest,market_data:true}})).status,502);
});
test('unknown research slate is not served', async()=>{
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
  assert.equal((await call(`/v1/qbase/${sid}?offset=-1`)).status,400);
  assert.equal((await call('/health',{},'POST')).status,405);
});