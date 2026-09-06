import test from 'node:test';
import assert from 'node:assert/strict';
import {validateResearchContext} from './run.js';

const lock = {
  game_id: '2026_01_NE_SEA', source_commit: 'a'.repeat(40), pack_revision: 'b'.repeat(16),
  away_team: 'NE', home_team: 'SEA', created_at: Date.parse('2026-09-06T01:00:00Z')
};
const part = id => ({status: 'VERIFIED', summary: 'Verified current football evidence.', evidence_ids: [id]});
function context() {
  return {
    game_id: lock.game_id,
    completed_at: '2026-09-06T02:00:00Z',
    pack_receipt: {source_commit: lock.source_commit, pack_revision: lock.pack_revision, retrieved_player_count: 30},
    current_information_state: {practice: 'PARTIAL', inactives: 'NOT AVAILABLE'},
    research_quality_permission: 'YES',
    evidence: [
      {evidence_id: 'EV1', source: 'Official team', source_url: 'https://example.com/1', source_date: '2026-09-05T00:00:00Z', checked_at: '2026-09-06T01:30:00Z', subject: 'NE role', finding: 'Role verified.', model_pathway: 'ROLE', availability: 'VERIFIED'},
      {evidence_id: 'EV2', source: 'Official team', source_url: 'https://example.com/2', source_date: '2026-09-05T00:00:00Z', checked_at: '2026-09-06T01:30:00Z', subject: 'SEA role', finding: 'Role verified.', model_pathway: 'ROLE', availability: 'VERIFIED'},
      {evidence_id: 'EV3', source: 'Gamebook', source_url: null, source_date: '2025-12-01T00:00:00Z', checked_at: '2026-09-06T01:30:00Z', subject: 'NE defense', finding: 'Defensive profile evidence.', model_pathway: 'DEFENSE', availability: 'VERIFIED'},
      {evidence_id: 'EV4', source: 'Gamebook', source_url: null, source_date: '2025-12-01T00:00:00Z', checked_at: '2026-09-06T01:30:00Z', subject: 'SEA defense', finding: 'Defensive profile evidence.', model_pathway: 'DEFENSE', availability: 'VERIFIED'},
    ],
    team_contexts: [
      {team: 'NE', summary: 'New England current offensive context.', evidence_ids: ['EV1']},
      {team: 'SEA', summary: 'Seattle current offensive context.', evidence_ids: ['EV2']},
    ],
    defensive_profiles: [
      {team: 'NE', passing_opportunities_faced: part('EV3'), position_depth_concessions: part('EV3'), pressure_protection: part('EV3'), current_personnel: part('EV3'), limitations: []},
      {team: 'SEA', passing_opportunities_faced: part('EV4'), position_depth_concessions: part('EV4'), pressure_protection: part('EV4'), current_personnel: part('EV4'), limitations: []},
    ],
    players: [
      {player_id: '00-0011111', player_name: 'NE Receiver', team: 'NE', research_status: 'INCLUDE', evidence_ids: ['EV1'], handoff_summary: 'Verified route and target role.'},
      {player_id: '00-0022222', player_name: 'SEA Receiver', team: 'SEA', research_status: 'INCLUDE', evidence_ids: ['EV2'], handoff_summary: 'Verified route and target role.'},
    ],
    material_unknowns: [],
    research_summary: 'Complete market-blind fixture research with current role translation and both four-part defensive profiles.'
  };
}

test('complete market-blind research checkpoint passes', () => {
  assert.doesNotThrow(() => validateResearchContext(context(), lock, 30, Date.parse('2026-09-06T02:01:00Z')));
});

test('market fields are rejected before freeze', () => {
  const c = context(); c.current_information_state.odds = 2.0;
  assert.throws(() => validateResearchContext(c, lock, 30, Date.parse('2026-09-06T02:01:00Z')), /Market field prohibited/);
});

test('missing defensive component blocks checkpoint', () => {
  const c = context(); delete c.defensive_profiles[0].pressure_protection;
  assert.throws(() => validateResearchContext(c, lock, 30, Date.parse('2026-09-06T02:01:00Z')), /keys mismatch/);
});

test('incomplete locked pack receipt blocks checkpoint', () => {
  const c = context(); c.pack_receipt.retrieved_player_count = 29;
  assert.throws(() => validateResearchContext(c, lock, 30, Date.parse('2026-09-06T02:01:00Z')), /Incomplete research pack/);
});
