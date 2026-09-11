import { writeFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';

function need(ok, message) {
  if (!ok) throw new Error(message);
}

function trimBase(value, label) {
  const raw = String(value || '').trim();
  need(raw, `${label} required`);
  const url = new URL(raw);
  need(url.protocol === 'https:', `${label} must use https`);
  return raw.replace(/\/+$/, '');
}

export function validateResearchHealth(value, expectedSourceCommit) {
  need(value?.ok === true, 'research health ok=true required');
  need(value?.service === 'nba-player-props-research-freeze', 'research service identity mismatch');
  need(value?.market_data === false, 'research must be market_data=false');
  need(value?.source_commit_ready === true, 'research source_commit_ready=true required');
  need(value?.durable_object_binding === true, 'research Durable Object binding missing');
  need(/^[0-9a-f]{40}$/.test(String(value?.source_commit || '')), 'research source_commit invalid');
  if (expectedSourceCommit) need(value.source_commit === expectedSourceCommit, 'research deployment source commit mismatch');
  return {
    ok: true,
    service: value.service,
    version: value.version,
    source_commit: value.source_commit,
    source_commit_ready: true,
    durable_object_binding: true,
    market_data: false,
  };
}

export function validateMarketHealth(value) {
  need(value?.ok === true, 'market health ok=true required');
  need(value?.service === 'nba-player-props-market', 'market service identity mismatch');
  need(value?.post_freeze_only === true, 'market post_freeze_only=true required');
  need(value?.research_service_binding === true, 'market Research service binding missing');
  need(value?.durable_object_binding === true, 'market Durable Object binding missing');
  need(value?.odds_api_key_configured === true, 'market ODDS_API_KEY missing');
  need(String(value?.default_regions || '') === 'au', 'market default region must be au');
  const expected = ['player_assists', 'player_assists_alternate', 'player_rebounds', 'player_rebounds_alternate'];
  need(Array.isArray(value?.markets) && expected.every((x) => value.markets.includes(x)), 'market allowlist incomplete');
  return {
    ok: true,
    service: value.service,
    version: value.version,
    post_freeze_only: true,
    research_service_binding: true,
    durable_object_binding: true,
    odds_api_key_configured: true,
    default_regions: 'au',
    markets: expected,
  };
}

export function validateTrackerHealth(value, expectedSchema = '2.1.0') {
  need(value?.status === 'ok', 'tracker status=ok required');
  need(String(value?.schema_version || '') === expectedSchema, `tracker schema ${expectedSchema} required`);
  return {
    status: 'ok',
    schema_version: value.schema_version,
    api_version: value.api_version,
    database_binding: value.database_binding,
  };
}

async function fetchJson(url, { method = 'GET', headers = {}, body, expectedStatus = 200 } = {}) {
  const response = await fetch(url, {
    method,
    headers: { accept: 'application/json', ...headers },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await response.text();
  let value;
  try { value = text ? JSON.parse(text) : {}; }
  catch { throw new Error(`${method} ${url} returned non-JSON ${response.status}`); }
  need(response.status === expectedStatus, `${method} ${url} expected ${expectedStatus}, got ${response.status}: ${value?.error || text.slice(0, 200)}`);
  return value;
}

async function assertUnauthorized(url) {
  const response = await fetch(url, { headers: { accept: 'application/json' } });
  const text = await response.text();
  let value = {};
  try { value = text ? JSON.parse(text) : {}; } catch {}
  need(response.status === 401, `unauthenticated ${url} must return 401, got ${response.status}`);
  need(String(value?.error || '').toLowerCase().includes('unauthorized'), `unauthenticated ${url} missing Unauthorized error`);
  return true;
}

function bearer(token, label) {
  const value = String(token || '').trim();
  need(value, `${label} required`);
  return { authorization: `Bearer ${value}` };
}

export async function runPostDeployPreflight(env = process.env) {
  const researchBase = trimBase(env.NBA_RESEARCH_URL, 'NBA_RESEARCH_URL');
  const marketBase = trimBase(env.NBA_MARKET_URL, 'NBA_MARKET_URL');
  const trackerBase = trimBase(env.NBA_TRACKER_URL || 'https://nick-betting-api.nickarnott01.workers.dev', 'NBA_TRACKER_URL');
  const expectedCommit = String(env.EXPECTED_SOURCE_COMMIT || '').trim();
  need(/^[0-9a-f]{40}$/.test(expectedCommit), 'EXPECTED_SOURCE_COMMIT must be exact 40-char deployment Git SHA');

  const researchHeaders = bearer(env.NBA_RESEARCH_ACTION_TOKEN || env.NBA_ACTION_TOKEN, 'NBA_RESEARCH_ACTION_TOKEN/NBA_ACTION_TOKEN');
  const marketHeaders = bearer(env.NBA_MARKET_ACTION_TOKEN || env.NBA_ACTION_TOKEN, 'NBA_MARKET_ACTION_TOKEN/NBA_ACTION_TOKEN');
  const trackerKey = String(env.NBA_TRACKER_ACTION_KEY || '').trim();
  need(trackerKey, 'NBA_TRACKER_ACTION_KEY required');

  await assertUnauthorized(`${researchBase}/health`);
  await assertUnauthorized(`${marketBase}/health`);

  const research = validateResearchHealth(await fetchJson(`${researchBase}/health`, { headers: researchHeaders }), expectedCommit);
  const market = validateMarketHealth(await fetchJson(`${marketBase}/health`, { headers: marketHeaders }));
  const tracker = validateTrackerHealth(await fetchJson(`${trackerBase}/tracker/health`, {
    headers: { 'X-GPT-Action-Key': trackerKey },
  }), env.EXPECTED_TRACKER_SCHEMA || '2.1.0');

  let fixtureCheck = { checked: false };
  const leagueDate = String(env.NBA_ACCEPTANCE_ET_DATE || '').trim();
  if (leagueDate) {
    need(/^\d{4}-\d{2}-\d{2}$/.test(leagueDate), 'NBA_ACCEPTANCE_ET_DATE must be YYYY-MM-DD');
    const fixtureResult = await fetchJson(`${researchBase}/v1/fixtures?date=${encodeURIComponent(leagueDate)}`, { headers: researchHeaders });
    need(Array.isArray(fixtureResult?.fixtures), 'fixture response missing fixtures array');
    need(fixtureResult.fixtures.length > 0, `no eligible future fixtures for ${leagueDate}`);
    fixtureCheck = {
      checked: true,
      slate_date_et: leagueDate,
      fixture_count: fixtureResult.fixtures.length,
      fixture_source: fixtureResult.source || null,
      game_ids: fixtureResult.fixtures.map((x) => x.game_id),
    };
  }

  // Safe post-freeze boundary control: an unknown run must fail during the Market ->
  // Research grant lookup, before fetchOddsApiSlate can be reached or spend quota.
  const smokeRun = `nba-preflight-unknown-${Date.now()}`;
  const prefreeze = await fetchJson(`${marketBase}/v1/runs/${encodeURIComponent(smokeRun)}/refresh`, {
    method: 'POST',
    headers: { ...marketHeaders, 'content-type': 'application/json' },
    body: { regions: 'au', refresh_request_id: `preflight_${Date.now()}` },
    expectedStatus: 422,
  });
  need(/research service 422: Unknown run/i.test(String(prefreeze?.error || '')), 'market negative control did not fail at Research grant boundary');

  const receipt = {
    schema_version: 'nba_post_deploy_preflight_v1',
    passed: true,
    checked_at: new Date().toISOString(),
    expected_source_commit: expectedCommit,
    research,
    market,
    tracker,
    auth_required: { research: true, market: true },
    prefreeze_negative_control: {
      passed: true,
      odds_api_request_permitted: false,
      failure_boundary: 'RESEARCH_MARKET_ACCESS_GRANT',
    },
    fixtures: fixtureCheck,
    no_wager_written: true,
    no_tracker_model_run_written: true,
  };

  const outputPath = String(env.PREFLIGHT_RECEIPT_PATH || '').trim();
  if (outputPath) await writeFile(outputPath, `${JSON.stringify(receipt, null, 2)}\n`, 'utf8');
  return receipt;
}

const isMain = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (isMain) {
  runPostDeployPreflight()
    .then((receipt) => console.log(JSON.stringify(receipt, null, 2)))
    .catch((error) => {
      console.error(JSON.stringify({ passed: false, error: error.message }));
      process.exitCode = 1;
    });
}
