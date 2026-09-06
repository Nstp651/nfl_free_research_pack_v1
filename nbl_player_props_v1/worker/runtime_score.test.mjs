import test from 'node:test';
import assert from 'node:assert/strict';
import {assembleFeatureVector,normName,projectedMinutesScore,returningPlayerBaseline,scoreQbase} from './runtime_score.js';

function artifact(stat='assists'){
  const features=['player_games_prior','player_season_games_prior','player_minutes_mean_3','player_minutes_mean_5','player_minutes_mean_10','player_start_rate_5','player_start_rate_10','player_days_rest','team_games_prior','team_season_games_prior','team_days_rest','opponent_days_rest','team_points_mean_5','opponent_points_allowed_mean_5','home_flag'];
  return {market_data:false,stat_type:stat,model_version:'0.1.0',feature_schema:'nbl_player_pregame_v1',selected_model:{family:'poisson',features,imputer_medians:features.map(()=>0),scaler_mean:features.map(()=>0),scaler_scale:features.map(()=>1),coefficients:features.map((_,i)=>i===2?0.02:0),intercept:Math.log(2)}};
}
function snapshot(){return {market_data:false,snapshot_revision:'snap',players:{testguard:{player_key:'testguard',source_player_ids:['pid-1'],last_team:'Sydney Kings',last_season:'2025-2026',last_season_start:2025,last_match_time:'2026-03-01T00:00:00Z',features:{player_games_prior:50,player_last_season_games:30,player_minutes_mean_3:30,player_minutes_mean_5:29,player_minutes_mean_10:28,player_start_rate_5:1,player_start_rate_10:.9}},josealvarez:{player_key:'josealvarez',source_player_ids:['pid-accent'],last_team:'Sydney Kings',last_season:'2025-2026',last_season_start:2025,last_match_time:'2026-03-01T00:00:00Z',features:{player_games_prior:22,player_last_season_games:22,player_minutes_mean_3:25}}},teams:{'Sydney Kings':{team:'Sydney Kings',last_season:'2025-2026',last_season_start:2025,last_match_time:'2026-03-01T00:00:00Z',features:{team_games_prior:100,team_last_season_games:30,team_points_mean_5:90}},'Perth Wildcats':{team:'Perth Wildcats',last_season:'2025-2026',last_season_start:2025,last_match_time:'2026-03-02T00:00:00Z',features:{team_games_prior:100,team_last_season_games:30,points_allowed_mean_5:88}}}};}
const fixture={start_time:'2026-09-10T10:00:00Z',home_team:{name:'Sydney Kings'},away_team:{name:'Perth Wildcats'}};

test('serialized QBASE score is deterministic and minutes recomputation is model-native',async()=>{
  const a=artifact();const base=await scoreQbase(a,{player_minutes_mean_3:30});assert.ok(Math.abs(base.mean-2*Math.exp(.6))<1e-12);assert.match(base.quant_input_receipt_sha256,/^[0-9a-f]{64}$/);const moved=await projectedMinutesScore(a,{player_minutes_mean_3:30,player_minutes_mean_5:29,player_minutes_mean_10:28},35);assert.ok(moved.mean>base.mean);assert.equal(moved.method,'QBASE_MINUTES_RECOMPUTE');
});

test('next-fixture feature assembly resets season counts and binds opponent/home',()=>{
  const out=assembleFeatureVector(artifact(),snapshot(),{playerName:'Test Guard',playerId:'pid-1',team:'Sydney Kings',opponent:'Perth Wildcats',targetSeasonStart:2026,targetTime:fixture.start_time,homeFlag:1});assert.equal(out.features.player_games_prior,50);assert.equal(out.features.player_season_games_prior,0);assert.equal(out.features.team_season_games_prior,0);assert.equal(out.features.team_points_mean_5,90);assert.equal(out.features.opponent_points_allowed_mean_5,88);assert.equal(out.features.home_flag,1);assert.ok(out.features.player_days_rest>0);assert.deepEqual(out.player_source_player_ids,['pid-1']);
});

test('player ID wins before name fallback and accented names normalize identically',async()=>{
  assert.equal(normName('José Álvarez'), 'josealvarez');
  const byId=await returningPlayerBaseline(artifact(),snapshot(),{playerName:'Completely Different Display Name',playerId:'pid-accent',team:'Sydney Kings',fixture,targetSeasonStart:2026});assert.equal(byId.feature_context.player_prior_key,'josealvarez');
  const byName=await returningPlayerBaseline(artifact(),snapshot(),{playerName:'José Álvarez',team:'Sydney Kings',fixture,targetSeasonStart:2026});assert.equal(byName.feature_context.player_prior_key,'josealvarez');
});

test('returning player baseline is computed inside server scorer and missing imports fail closed',async()=>{
  const baseline=await returningPlayerBaseline(artifact(),snapshot(),{playerName:'Test Guard',team:'Sydney Kings',fixture,targetSeasonStart:2026});assert.ok(baseline.mean>0);assert.match(baseline.quant_input_receipt_sha256,/^[0-9a-f]{64}$/);await assert.rejects(()=>returningPlayerBaseline(artifact(),snapshot(),{playerName:'New Import',team:'Sydney Kings',fixture,targetSeasonStart:2026}),/prior-competition translation required/);
});
