import test from 'node:test';
import assert from 'node:assert/strict';
import {computeFrozenModel, validateModelInput} from './model_core.js';

const context = {
  game_id: '2026_01_NE_SEA',
  fixture: {away_team: 'NE', home_team: 'SEA'},
  evidence: [
    {evidence_id: 'E_NE_ROLE'}, {evidence_id: 'E_SEA_ROLE'}, {evidence_id: 'E_DEF'}
  ],
  players: [
    {player_id: '00-0011111', player_name: 'NE Receiver', team: 'NE', research_status: 'INCLUDE'},
    {player_id: '00-0022222', player_name: 'SEA Receiver', team: 'SEA', research_status: 'INCLUDE'},
    {player_id: '00-0033333', player_name: 'NE Receiver', team: 'NE', research_status: 'WATCHLIST'},
  ],
  research_receipt_sha256: 'a'.repeat(64),
};

function rate(mean, strength = 50) { return {mean, strength}; }
function team(code, playerId, method = 'A') {
  return {
    team: code,
    players: [{player_id: playerId, player_name: `${code} Receiver`, confidence: 'HIGH', fragility: 'LOW', key_assumptions: ['stable role']}],
    scenarios: [{
      scenario_id: 'BASE', weight: 1,
      targetable_passes: [{value: 30, probability: 0.5}, {value: 34, probability: 0.5}],
      other_share: method === 'A' ? 0.75 : 0.8,
      player_params: [{
        player_id: playerId, target_method: method,
        target_rate: method === 'A' ? rate(0.25, 80) : rate(0.20, 80),
        catch_rate: rate(0.65, 100),
        route_counts: method === 'A' ? null : [{value: 30, probability: 0.5}, {value: 34, probability: 0.5}],
      }],
      football_rationale: 'Market-blind football evidence supports the base state.'
    }]
  };
}
function input() {
  return {
    game_id: context.game_id,
    engine_version: 'NFL_RECEPTIONS_V5_EXACT_HBB_1.0.0',
    threshold_max: 12,
    teams: [team('NE', '00-0011111'), team('SEA', '00-0022222')],
    source_to_parameter_ledger: [
      {parameter_path: 'teams.NE', evidence_ids: ['E_NE_ROLE','E_DEF'], rationale: 'NE opportunity and conversion parameters.'},
      {parameter_path: 'teams.SEA', evidence_ids: ['E_SEA_ROLE','E_DEF'], rationale: 'SEA opportunity and conversion parameters.'},
    ],
  };
}

test('valid model freezes exact monotonic ladders and allocation receipts', async () => {
  const frozen = await computeFrozenModel(input(), context, Date.parse('2026-09-06T02:00:00Z'));
  assert.equal(frozen.players.length, 2);
  assert.equal(frozen.team_allocation_audits.every(x => x.allocation_status === 'PASS'), true);
  assert.equal(frozen.players.every(x => x.distribution_method === 'EXACT_HIERARCHICAL_BETA_BINOMIAL'), true);
  for (const p of frozen.players) {
    let prior = 1;
    for (let k = 1; k <= 12; k++) { assert.ok(p.ladder[String(k)] <= prior + 1e-12); prior = p.ladder[String(k)]; }
    assert.ok(p.expected_receptions > 0);
  }
  assert.match(frozen.freeze_receipt_sha256, /^[a-f0-9]{64}$/);
});

test('103% target allocation is rejected', () => {
  const value = input();
  value.teams[0].scenarios[0].other_share = 0.78;
  assert.throws(() => validateModelInput(value, context), /target allocation/);
});

test('method B uses route x TPRR equivalent allocation', async () => {
  const value = input();
  value.teams[0] = team('NE', '00-0033333', 'B');
  const frozen = await computeFrozenModel(value, context);
  const p = frozen.players.find(x => x.player_id === '00-0033333');
  assert.ok(Math.abs(p.expected_targets - 6.4) < 1e-10);
});

test('unknown evidence reference blocks freeze', () => {
  const value = input();
  value.source_to_parameter_ledger[0].evidence_ids = ['DOES_NOT_EXIST'];
  assert.throws(() => validateModelInput(value, context), /unknown evidence_id/);
});

test('model player must be exactly bound to checkpointed research identity', () => {
  const value = input();
  value.teams[0].players[0].player_id = '00-0099999';
  value.teams[0].scenarios[0].player_params[0].player_id = '00-0099999';
  assert.throws(() => validateModelInput(value, context), /not present in checkpointed research/);
});
