import test from 'node:test';
import assert from 'node:assert/strict';
import { validateResearchCheckpoint } from './research_contract.js';
import { buildTransformsFromResearch } from './research_to_transforms.js';

const evidence=[{evidence_id:'e1',url:'https://example.com/a',title:'Rotation report',checked_at:'2026-09-08T07:00:00Z',published_at:'2026-09-08T06:00:00Z',source_tier:1,evidence_type:'ROLE'}];
function player(){return {player_id:'100',player_name:'Test Guard',team:'BOS',availability:'ACTIVE',role_state:'RETURNING_CHANGED',projected_minutes:{low:30,mean:34,high:37},expected_starter_probability:.9,evidence_ids:['e1'],confidence_inputs:{current_role:true},fragility_inputs:{late_news:false},stat_context:{assists:{causal_pathway:'Primary creator with more on-ball reps',evidence_ids:['e1'],current_opportunity:{expected_assist_share:.31,expected_team_assists:27,expected_possessions:101,evidence_ids:['e1']}},rebounds:{causal_pathway:'Stable guard rebound role',evidence_ids:['e1'],current_opportunity:{expected_rebound_share:.08,expected_team_rebounds:44,expected_possessions:101,evidence_ids:['e1']}}}};}
function checkpoint(){return {schema_version:'nba_game_research_v1',market_data:false,run_mode:'BOTH',game_id:'4019999999',slate_date_et:'2026-10-20',fixture:{home_team:'BOS',away_team:'NYK',start_time_utc:'2026-10-21T00:00:00Z',evidence_ids:['e1']},evidence,specialist_metrics:{potential_assists:{status:'UNAVAILABLE'}},players:[player()]};}
function artifact(head){const features=head==='assists'?['minutes_l5','minutes_l10','start_rate_l5','start_rate_l10','starter_prev','assist_share_l5','assist_share_l10','team_assists_l5','team_assists_l10','team_possessions_l5','team_possessions_l10']:['minutes_l5','minutes_l10','start_rate_l5','start_rate_l10','starter_prev','rebound_share_l5','rebound_share_l10','team_rebounds_l5','team_rebounds_l10','team_possessions_l5','team_possessions_l10'];return {family:'regularized_poisson_glm',head,features,medians:features.map(()=>1),centers:features.map(()=>1),scales:features.map(()=>1),coefficients:features.map(()=>.01),intercept:0,dispersion_alpha:.2};}

test('research contract requires market-blind evidence-bound current opportunity',()=>{
  const out=validateResearchCheckpoint(checkpoint(),Date.parse('2026-09-08T08:00:00Z'));
  assert.equal(out.ok,true); assert.deepEqual(out.heads,['assists','rebounds']);
});

test('market leakage is rejected before freeze',()=>{
  const c=checkpoint(); c.players[0].sportsbook='x';
  assert.throws(()=>validateResearchCheckpoint(c,Date.parse('2026-09-08T08:00:00Z')),/market boundary/);
});

test('assists research becomes only typed feature transforms',()=>{
  const t=buildTransformsFromResearch(artifact('assists'),player());
  assert.deepEqual(t.map(x=>x.type),['MINUTES_RECOMPUTE','ROLE_OPPORTUNITY_RECOMPUTE','LINEUP_DEPENDENCY_RECOMPUTE']);
  assert.equal(t[1].inputs.assist_share_l5,.31);assert.equal(t[1].inputs.team_assists_l10,27);assert.equal(t[2].inputs.team_possessions_l5,101);
  assert.equal('mean' in t[1],false);
});

test('rebounds research maps to rebound opportunity rather than assist fields',()=>{
  const t=buildTransformsFromResearch(artifact('rebounds'),player());
  assert.equal(t[1].inputs.rebound_share_l5,.08);assert.equal(t[1].inputs.team_rebounds_l10,44);assert.equal(t[1].inputs.assist_share_l5,undefined);
});
