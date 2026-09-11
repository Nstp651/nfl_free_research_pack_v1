import test from 'node:test';
import assert from 'node:assert/strict';
import { validateResearchHealth, validateMarketHealth, validateTrackerHealth } from './post_deploy_preflight.mjs';

const commit = 'a'.repeat(40);

test('research health accepts exact production contract', () => {
  const out = validateResearchHealth({
    ok: true,
    service: 'nba-player-props-research-freeze',
    version: '1.0.0',
    market_data: false,
    source_commit: commit,
    source_commit_ready: true,
    durable_object_binding: true,
  }, commit);
  assert.equal(out.source_commit, commit);
});

test('research health rejects deployment commit mismatch', () => {
  assert.throws(() => validateResearchHealth({
    ok: true,
    service: 'nba-player-props-research-freeze',
    market_data: false,
    source_commit: commit,
    source_commit_ready: true,
    durable_object_binding: true,
  }, 'b'.repeat(40)), /source commit mismatch/);
});

test('market health enforces bindings, key, region and market allowlist', () => {
  const out = validateMarketHealth({
    ok: true,
    service: 'nba-player-props-market',
    version: '1.0.0',
    post_freeze_only: true,
    markets: ['player_assists','player_assists_alternate','player_rebounds','player_rebounds_alternate'],
    default_regions: 'au',
    research_service_binding: true,
    durable_object_binding: true,
    odds_api_key_configured: true,
  });
  assert.equal(out.post_freeze_only, true);
});

test('market health fails closed without Odds API key', () => {
  assert.throws(() => validateMarketHealth({
    ok: true,
    service: 'nba-player-props-market',
    post_freeze_only: true,
    markets: ['player_assists','player_assists_alternate','player_rebounds','player_rebounds_alternate'],
    default_regions: 'au',
    research_service_binding: true,
    durable_object_binding: true,
    odds_api_key_configured: false,
  }), /ODDS_API_KEY/);
});

test('tracker health requires exact shared production schema', () => {
  assert.equal(validateTrackerHealth({ status: 'ok', schema_version: '2.1.0', api_version: '1' }).schema_version, '2.1.0');
  assert.throws(() => validateTrackerHealth({ status: 'ok', schema_version: '2.0.0' }), /tracker schema/);
});
