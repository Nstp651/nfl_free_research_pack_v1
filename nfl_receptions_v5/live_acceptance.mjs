import assert from 'node:assert/strict';

const CONTROL = 'https://nfl-receptions-platform-v5.nickarnott01.workers.dev';
const MARKET = 'https://nfl-receptions-market-v5.nickarnott01.workers.dev';
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function jsonFetch(url, options = {}) {
  const res = await fetch(url, options);
  const text = await res.text();
  let data;
  try { data = JSON.parse(text); } catch { throw new Error(`Non-JSON response ${res.status} from ${url}: ${text.slice(0, 300)}`); }
  return {res, data};
}

async function waitForHealth(url, predicate, label) {
  let last;
  for (let i = 0; i < 18; i++) {
    try {
      const out = await jsonFetch(`${url}/health`);
      last = out;
      if (out.res.ok && predicate(out.data)) return out.data;
    } catch (e) { last = e; }
    await sleep(5000);
  }
  throw new Error(`${label} health did not become ready: ${JSON.stringify(last?.data || String(last))}`);
}

const controlHealth = await waitForHealth(CONTROL,
  x => x.ok === true && x.durable_state === true && x.market_data === false,
  'control');
const marketHealth = await waitForHealth(MARKET,
  x => x.ok === true && x.configured === true && x.service === 'NFL_RECEPTIONS_MARKET_GATEWAY',
  'market');

const init = {
  season: 2026,
  week: 1,
  game_id: '2026_01_NE_SEA',
  fixture_date_sydney: '2026-09-10',
  validated_kickoff_utc: '2026-09-10T03:20:00Z',
};

let created;
for (let i = 0; i < 18; i++) {
  const out = await jsonFetch(`${CONTROL}/v1/runs`, {
    method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify(init),
  });
  if (out.res.ok && /^[a-f0-9]{64}$/.test(out.data.run_id || '') && out.data.status === 'RESEARCH_IN_PROGRESS') {
    created = out.data;
    break;
  }
  if (out.res.status === 422 && out.data.error === 'Unknown run operation') {
    await sleep(5000);
    continue;
  }
  throw new Error(`Run initialization failed ${out.res.status}: ${JSON.stringify(out.data)}`);
}
assert.ok(created, 'Updated control Worker did not become available');
const runId = created.run_id;
assert.equal(created.p_model_status, 'NOT FROZEN');
assert.equal(created.freeze, null);

const before = await jsonFetch(`${CONTROL}/v1/runs/${runId}`);
assert.equal(before.res.status, 200);
assert.equal(before.data.status, 'RESEARCH_IN_PROGRESS');
assert.equal(before.data.p_model_status, 'NOT FROZEN');
assert.equal(before.data.research.checkpointed, false);
assert.equal(before.data.freeze, null);

const denied = await jsonFetch(`${MARKET}/v1/receptions?run_id=${runId}`);
console.log('PRE_FREEZE_DENIAL', JSON.stringify({status: denied.res.status, data: denied.data}));
assert.equal(denied.res.status, 422, `Expected pre-freeze market denial, got ${denied.res.status}: ${JSON.stringify(denied.data)}`);
assert.match(String(denied.data.error || ''), /not frozen/i);
assert.equal('quota' in denied.data, false, 'Pre-freeze denial must not expose an Odds API quota receipt');
assert.equal('event' in denied.data, false, 'Pre-freeze denial must occur before event-market resolution');
assert.equal('best_prices' in denied.data, false, 'Pre-freeze denial must occur before price integration');

const after = await jsonFetch(`${CONTROL}/v1/runs/${runId}`);
assert.equal(after.res.status, 200);
assert.equal(after.data.status, 'RESEARCH_IN_PROGRESS');
assert.equal(after.data.p_model_status, 'NOT FROZEN');
assert.equal(after.data.research.checkpointed, false);
assert.equal(after.data.freeze, null);

console.log(JSON.stringify({
  acceptance: 'PASS',
  control_health: controlHealth,
  market_health: marketHealth,
  run_id: runId,
  locked_game_id: after.data.lock.game_id,
  source_commit: after.data.lock.source_commit,
  pack_revision: after.data.lock.pack_revision,
  pre_freeze_market_status: denied.res.status,
  pre_freeze_market_error: denied.data.error,
  state_after_denial: after.data.status,
  p_model_status_after_denial: after.data.p_model_status,
}, null, 2));
