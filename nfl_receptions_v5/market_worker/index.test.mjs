import test from 'node:test';
import assert from 'node:assert/strict';
import worker,{resolveEvent} from './index.js';

const runId='a'.repeat(64);
const frozen={run_id:runId,status:'FROZEN',p_model_status:'FROZEN',lock:{away_team:'NE',home_team:'SEA',validated_kickoff_utc:'2026-09-10T00:20:00Z'},freeze:{freeze_receipt_sha256:'b'.repeat(64),frozen_at:'2026-09-06T02:00:00Z'}};
const artifact={run_id:runId,p_model_status:'FROZEN',freeze:{freeze_receipt_sha256:'b'.repeat(64),players:[{player_id:'00-0011111',player_name:'Player One',ladder:{'5':0.60,'6':0.45},confidence:'HIGH',fragility:'LOW'}]}};
const event={id:'c'.repeat(32),sport_key:'americanfootball_nfl',away_team:'New England Patriots',home_team:'Seattle Seahawks',commence_time:'2026-09-10T00:20:00Z'};
function json(value,status=200,headers={}){return new Response(JSON.stringify(value),{status,headers});}

test('non-frozen run blocks through service binding before any Odds API call',async()=>{
  const controlCalls=[]; const oddsCalls=[];
  globalThis.fetch=async url=>{oddsCalls.push(String(url));throw new Error('Odds API must not be called before freeze');};
  const CONTROL_SERVICE={fetch:async req=>{controlCalls.push(new URL(req.url).pathname);return json({...frozen,status:'RESEARCH_COMPLETE',p_model_status:'NOT FROZEN',freeze:null});}};
  const res=await worker.fetch(new Request(`https://x/v1/receptions?run_id=${runId}`),{CONTROL_SERVICE,ODDS_API_KEY:'secret'});
  assert.equal(res.status,422); assert.deepEqual(controlCalls,[`/v1/runs/${runId}`]); assert.equal(oddsCalls.length,0);
  const body=await res.json(); assert.match(body.error,/not frozen/i);
});

test('frozen run resolves exact event and returns only valid Over reception ladders',async()=>{
  const controlCalls=[]; const oddsCalls=[];
  const CONTROL_SERVICE={fetch:async req=>{const path=new URL(req.url).pathname;controlCalls.push(path);return path.endsWith('/freeze')?json(artifact):json(frozen);}};
  globalThis.fetch=async url=>{oddsCalls.push(String(url));
    if(oddsCalls.length===1) return json([event]);
    return json({...event,bookmakers:[{key:'sportsbet',title:'SportsBet',last_update:'2026-09-06T02:10:00Z',markets:[
      {key:'player_receptions',outcomes:[{name:'Over',description:'Player One',price:1.9,point:4.5},{name:'Under',description:'Player One',price:1.9,point:4.5}]},
      {key:'player_receptions_alternate',outcomes:[{name:'Over',description:'Player One',price:2.5,point:5.5},{name:'Over',description:'Bad Line',price:3,point:5.2}]}
    ]},{key:'tab',title:'TAB',last_update:'2026-09-06T02:11:00Z',markets:[{key:'player_receptions',outcomes:[{name:'Over',description:'Player One',price:2.0,point:4.5}]}]}]},200,{'x-requests-remaining':'999'});
  };
  const res=await worker.fetch(new Request(`https://x/v1/receptions?run_id=${runId}`),{CONTROL_SERVICE,ODDS_API_KEY:'secret'});
  assert.equal(res.status,200); const body=await res.json();
  assert.deepEqual(controlCalls,[`/v1/runs/${runId}`,`/v1/runs/${runId}/freeze`]);
  assert.equal(oddsCalls.length,2); assert.match(oddsCalls[0],/\/events\?/); assert.match(oddsCalls[1],/player_receptions%2Cplayer_receptions_alternate/);
  assert.equal(body.raw_selection_count,3); assert.equal(body.mapped_selection_count,2); assert.deepEqual(body.best_prices.map(x=>x.reception_threshold),[5,6]); assert.equal(body.best_prices.find(x=>x.reception_threshold===5).bookmaker,'TAB');
  assert.equal(body.positive_edge_count,2); assert.ok(body.positive_edge_ranked[0].expected_roi >= body.positive_edge_ranked[1].expected_roi);
  assert.equal(body.freeze_receipt_sha256,'b'.repeat(64));
});

test('fixture resolution requires exact teams and kickoff',()=>{
  assert.throws(()=>resolveEvent([{...event,home_team:'Los Angeles Rams'}],frozen.lock),/exactly one/);
});

test('health consumes no upstream requests and requires service binding plus secret',async()=>{
  let oddsCalls=0; globalThis.fetch=async()=>{oddsCalls++;throw new Error('should not call');};
  const CONTROL_SERVICE={fetch:async()=>{throw new Error('health should not call control');}};
  const res=await worker.fetch(new Request('https://x/health'),{CONTROL_SERVICE,ODDS_API_KEY:'secret'});
  assert.equal(res.status,200); assert.equal(oddsCalls,0); const body=await res.json(); assert.equal(body.control_transport,'SERVICE_BINDING');
});
