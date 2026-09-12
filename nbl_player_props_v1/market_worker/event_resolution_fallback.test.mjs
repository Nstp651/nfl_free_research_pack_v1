import test from 'node:test';
import assert from 'node:assert/strict';
import {fetchAndEvaluateOddsApi,sha256Json} from './index.js';

const RUN='a'.repeat(64),RECEIPT='b'.repeat(64),FROZEN_AT='2026-09-11T09:51:10.890Z';
const frozenPlayer={player_id:'p1',player_name:'Test Guard',team:'Adelaide 36ers',heads:{assists:{confidence:'B',fragility:'LOW',probability_grid:{half_point_grid:[{line:4.5,over:.55,push:0,under:.45}],integer_push_grid:[]}},rebounds:{confidence:'C',fragility:'MEDIUM',probability_grid:{half_point_grid:[{line:5.5,over:.4,push:0,under:.6}],integer_push_grid:[]}}}};
const PLAYER_HASH=await sha256Json(frozenPlayer);
const fixture={id:'fixture-1',start_time:'2026-09-19T09:30:00Z',home_team:{id:'h',name:'Melbourne United'},away_team:{id:'a',name:'Adelaide 36ers'}};
const runBody={status:'FROZEN',lock:{fixture},freeze:{status:'FROZEN',fixture_id:'fixture-1',freeze_receipt_sha256:RECEIPT,frozen_at:FROZEN_AT,players:[{player_key:'id:p1',player_model_sha256:PLAYER_HASH,player_id:'p1',player_name:'Test Guard',team:'Adelaide 36ers'}]}};
const playerBody={freeze_receipt_sha256:RECEIPT,frozen_at:FROZEN_AT,player_model_sha256:PLAYER_HASH,player:frozenPlayer};
const oddsEvent={id:'evt1',sport_key:'basketball_nbl',commence_time:'2026-09-19T09:30:00Z',home_team:'Melbourne United',away_team:'Adelaide 36ers'};
const props={...oddsEvent,bookmakers:[{key:'sportsbet',title:'SportsBet',markets:[{key:'player_assists',outcomes:[{name:'Over',description:'Test Guard',price:2.05,point:4.5}]}]}]};
const env={RESEARCH_BASE:'https://research.example.workers.dev',ODDS_API_KEY:'secret'};
function jr(x,status=200,headers={}){return new Response(JSON.stringify(x),{status,headers:{'content-type':'application/json',...headers}});}

test('falls back to featured h2h odds feed when events endpoint omits frozen fixture',async()=>{
  const old=globalThis.fetch;const calls=[];
  try{
    globalThis.fetch=async input=>{const url=String(input);calls.push(url);if(url.endsWith(`/v1/match-runs/${RUN}`))return jr(runBody);if(url.includes(`/v1/match-runs/${RUN}/players/`))return jr(playerBody);if(url.includes('/v4/sports/basketball_nbl/events?'))return jr([],200,{'x-requests-last':'0'});if(url.includes('/v4/sports/basketball_nbl/odds?'))return jr([oddsEvent],200,{'x-requests-last':'1'});if(url.includes('/events/evt1/odds?'))return jr(props,200,{'x-requests-last':'4'});return jr({error:'unexpected '+url},404);};
    const out=await fetchAndEvaluateOddsApi({run_id:RUN,expected_freeze_receipt_sha256:RECEIPT,markets:['player_assists']},env);
    assert.equal(out.odds_api_support,'SUPPORTED_WITH_ROWS');
    assert.equal(out.event_resolution_source,'featured_h2h_odds_fallback');
    assert.equal(out.event.event_id,'evt1');
    assert.equal(out.evaluation.best_single.player_name,'Test Guard');
    assert.ok(calls.find(x=>x.includes('/v4/sports/basketball_nbl/odds?')));
  }finally{globalThis.fetch=old;}
});

test('EVENT_NOT_FOUND reports diagnostics after both resolution feeds fail',async()=>{
  const old=globalThis.fetch;
  try{
    globalThis.fetch=async input=>{const url=String(input);if(url.endsWith(`/v1/match-runs/${RUN}`))return jr(runBody);if(url.includes('/v4/sports/basketball_nbl/events?'))return jr([]);if(url.includes('/v4/sports/basketball_nbl/odds?'))return jr([{id:'other',commence_time:'2026-09-19T09:30:00Z',home_team:'Sydney Kings',away_team:'Perth Wildcats'}]);return jr({},404);};
    const out=await fetchAndEvaluateOddsApi({run_id:RUN,expected_freeze_receipt_sha256:RECEIPT,markets:['player_assists']},env);
    assert.equal(out.odds_api_support,'EVENT_NOT_FOUND');
    assert.equal(out.event_resolution_source,'none');
    assert.equal(out.event_resolution_diagnostics.events_endpoint_count,0);
    assert.equal(out.event_resolution_diagnostics.featured_odds_count,1);
  }finally{globalThis.fetch=old;}
});
