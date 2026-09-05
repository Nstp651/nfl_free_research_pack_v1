import test from 'node:test';
import assert from 'node:assert/strict';
import worker from './index.js';

const originalFetch = globalThis.fetch;
const board = Array.from({length: 35}, (_, i) => ({
  id: String(i).padStart(32, 'a'), sport_key: 'americanfootball_ncaaf', sport_title: 'NCAAF',
  commence_time: `2026-09-${String(5 + Math.floor(i/10)).padStart(2,'0')}T${String(i%10).padStart(2,'0')}:00:00Z`,
  home_team: `Home ${i}`, away_team: `Away ${i}`,
  bookmakers: [{key:'sportsbet', title:'Sportsbet', last_update:'2026-09-05T00:00:00Z', markets:[{
    key:'totals', outcomes:[
      {name:'Over', price:1.91, point:52.5}, {name:'Under', price:1.91, point:52.5},
    ]
  }]}, {key:'wrong', title:'Wrong', markets:[{key:'h2h', outcomes:[]}]}],
}));

async function call(path, {data=board, status=200, env={ODDS_API_KEY:'secret'}, method='GET', onFetch=null}={}) {
  globalThis.fetch = async (url) => {
    if (onFetch) onFetch(String(url));
    return new Response(JSON.stringify(data), {status, headers:{
      'x-requests-remaining':'999', 'x-requests-used':'1', 'x-requests-last':'1'
    }});
  };
  try {
    const res = await worker.fetch(new Request('https://test.invalid'+path, {method}), env);
    const raw = await res.text();
    return {status:res.status, data:JSON.parse(raw), chars:raw.length};
  } finally { globalThis.fetch = originalFetch; }
}

test('health is no-market-call and requires configured key', async () => {
  let called = false;
  globalThis.fetch = async () => { called = true; throw new Error('should not call'); };
  try {
    const good = await worker.fetch(new Request('https://test.invalid/health'), {ODDS_API_KEY:'x'});
    assert.equal(good.status, 200);
    assert.equal(called, false);
    const body = await good.json();
    assert.equal(body.version, '0.1.1');
    const bad = await worker.fetch(new Request('https://test.invalid/health'), {});
    assert.equal(bad.status, 503);
    assert.equal(called, false);
  } finally { globalThis.fetch = originalFetch; }
});

test('board is totals-only, AU-labelled and paginates at one revision', async () => {
  const first = await call('/v1/totals?offset=0&limit=20');
  assert.equal(first.status, 200);
  assert.equal(first.data.region, 'au');
  assert.equal(first.data.market_key, 'totals');
  assert.equal(first.data.games.length, 20);
  assert.equal(first.data.games[0].bookmakers.length, 1);
  assert.ok(first.chars < 90000);
  const rev = first.data.board_revision;
  const second = await call(`/v1/totals?offset=${first.data.pagination.next_offset}&limit=20&revision=${rev}`);
  assert.equal(second.status, 200);
  assert.equal(second.data.board_revision, rev);
  assert.equal(second.data.pagination.next_offset, null);
  assert.equal(first.data.games.length + second.data.games.length, 35);
});

test('commence window is validated at gateway and filtered locally, not sent upstream', async () => {
  let upstreamUrl = null;
  const r = await call(
    '/v1/totals?commence_from=2026-09-06T02:00:00Z&commence_to=2026-09-06T05:00:00Z',
    {onFetch: url => { upstreamUrl = url; }}
  );
  assert.equal(r.status, 200);
  assert.equal(r.data.games.length, 4);
  assert.deepEqual(r.data.games.map(g => g.commence_time), [
    '2026-09-06T02:00:00Z', '2026-09-06T03:00:00Z',
    '2026-09-06T04:00:00Z', '2026-09-06T05:00:00Z'
  ]);
  assert.ok(upstreamUrl);
  assert.equal(upstreamUrl.includes('commenceTimeFrom'), false);
  assert.equal(upstreamUrl.includes('commenceTimeTo'), false);
  assert.equal(r.data.filter.commence_from, '2026-09-06T02:00:00.000Z');
  assert.equal(r.data.filter.commence_to, '2026-09-06T05:00:00.000Z');
});

test('changed board revision prevents mixed market pages', async () => {
  const first = await call('/v1/totals?limit=10');
  const changed = structuredClone(board);
  changed[0].bookmakers[0].markets[0].outcomes[0].price = 2.01;
  const second = await call(`/v1/totals?offset=10&revision=${first.data.board_revision}`, {data:changed});
  assert.equal(second.status, 409);
});

test('filters and parameters are validated', async () => {
  assert.equal((await call('/v1/totals?offset=-1')).status, 400);
  assert.equal((await call('/v1/totals?revision=bad')).status, 400);
  assert.equal((await call('/v1/totals?commence_from=nope')).status, 400);
  assert.equal((await call('/v1/totals?commence_from=2026-09-10T00:00:00Z&commence_to=2026-09-01T00:00:00Z')).status, 400);
  assert.equal((await call('/v1/totals', {method:'POST'})).status, 405);
});

test('upstream failures and malformed boards fail visibly', async () => {
  assert.equal((await call('/v1/totals', {status:500})).status, 502);
  assert.equal((await call('/v1/totals', {status:429})).status, 429);
  const upstream422 = await call('/v1/totals', {status:422, data:{error_code:'INVALID_COMMENCE_TIME_FROM', message:'bad time'}});
  assert.equal(upstream422.status, 502);
  assert.equal(upstream422.data.upstream_status, 422);
  assert.equal(upstream422.data.upstream_code, 'INVALID_COMMENCE_TIME_FROM');
  assert.equal((await call('/v1/totals', {data:{oops:true}})).status, 502);
});

test('unconfigured market gateway fails before upstream', async () => {
  const r = await call('/v1/totals', {env:{}});
  assert.equal(r.status, 503);
});