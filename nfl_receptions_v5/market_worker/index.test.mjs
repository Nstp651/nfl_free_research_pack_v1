import test from 'node:test';
import assert from 'node:assert/strict';
import worker,{resolveEvent} from './index.js';

const runId='a'.repeat(64);
const frozen={run_id:runId,status:'FROZEN',p_model_status:'FROZEN',lock:{away_team:'NE',home_team:'SEA',validated_kickoff_utc:'2026-09-10T00:20:00Z'},freeze:{freeze_receipt_sha256:'b'.repeat(64),frozen_at:'2026-09-06T02:00:00Z'}};
const artifact={run_id:runId,p_model_status:'FROZEN',freeze:{freeze_receipt_sha256:'b'.repeat(64),players:[{player_id:'00-0011111',player_name:'Player One',ladder:{'5':0.60,'6':0.45},confidence:'HIGH',fragility:'LOW'}]}};
const event={id:'c'.repeat(32),sport_key:'americanfootball_nfl',away_team:'New England Patriots',home_team:'Seattle Seahawks',commence_time:'2026-09-10T00:20:00Z'};
function json(value,status=200,headers={}){return new Response(JSON.stringify(value),{status,headers});}

test('non-frozen run blocks before any Odds API call',async()=>{
  const calls=[]; globalThis.fetch=async url=>{calls.push(String(url));return json({...frozen,status:'RESEARCH_COMPLETE',p_model_status:'NOT FROZEN',freeze:null});};
  const res=await worker.fetch(new Request(`https://x/v1/receptions?run_id=${runId}`),{CONTROL_BASE_URL:'https://control.example',ODDS_API_KEY:'secret'});
  assert.equal(res.status,422); assert.equal(calls.length,1); assert.match(calls[0],/control\.example/);
});

test('frozen run resolves exact event and returns only valid Over reception ladders',async()=>{
  const calls=[]; globalThis.fetch=async url=>{calls.push(String(url));
    if(calls.length===1) return json(frozen);
    if(calls.length===2) return json(artifact);
    if(calls.length===3) return json([event]);
    return json({...event,bookmakers:[{key:'sportsbet',title:'SportsBet',last_update:'2026-09-06T02:10:00Z',markets:[
      {key:'player_receptions',outcomes:[{name:'Over',description:'Player One',price:1.9,point:4.5},{name:'Under',description:'Player One',price:1.9,point:4.5}]},
      {key:'player_receptions_alternate',outcomes:[{name:'Over',description:'Player One',price:2.5,point:5.5},{name:'Over',description:'Bad Line',price:3,point:5.2}]}
    ]},{key:'tab',title:'TAB',last_update:'2026-09-06T02:11:00Z',markets:[{key:'player_receptions',outcomes:[{name:'Over',description:'Player One',price:2.0,point:4.5}]}]}]},200,{'x-requests-remaining':'999'});
  };
  const res=await worker.fetch(new Request(`https://x/v1/receptions?run_id=${runId}`),{CONTROL_BASE_URL:'https://control.example',ODDS_API_KEY:'secret'});
  assert.equal(res.status,200); const body=await res.json();
  assert.equal(calls.length,4); assert.match(calls[1],/\/freeze$/); assert.match(calls[2],/\/events\?/); assert.match(calls[3],/player_receptions%2Cplayer_receptions_alternate/);
  assert.equal(body.raw_selection_count,3); assert.equal(body.mapped_selection_count,2); assert.deepEqual(body.best_prices.map(x=>x.reception_threshold),[5,6]); assert.equal(body.best_prices.find(x=>x.reception_threshold===5).bookmaker,'TAB');
  assert.equal(body.positive_edge_count,2); assert.ok(body.positive_edge_ranked[0].expected_roi >= body.positive_edge_ranked[1].expected_roi);
  assert.equal(body.freeze_receipt_sha256,'b'.repeat(64));
});

test('fixture resolution requires exact teams and kickoff',()=>{
  assert.throws(()=>resolveEvent([{...event,home_team:'Los Angeles Rams'}],frozen.lock),/exactly one/);
});

test('health consumes no upstream requests',async()=>{
  let calls=0; globalThis.fetch=async()=>{calls++;throw new Error('should not call');};
  const res=await worker.fetch(new Request('https://x/health'),{CONTROL_BASE_URL:'https://control.example',ODDS_API_KEY:'secret'});
  assert.equal(res.status,200); assert.equal(calls,0);
});
