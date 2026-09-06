import test from 'node:test';
import assert from 'node:assert/strict';
import {NblMatchRun} from './freeze_run_entry.js';
import {sha256Json} from './freeze_core.js';

class MemoryStorage{constructor(){this.m=new Map();}async get(k){return this.m.get(k);}async put(k,v){this.m.set(k,v);}async transaction(fn){return fn(this);}}
class MemoryState{constructor(){this.storage=new MemoryStorage();}async blockConcurrencyWhile(fn){return fn();}}
const jr=(x,status=200)=>new Response(JSON.stringify(x),{status,headers:{'content-type':'application/json'}});

async function harness(){
  const commit='1'.repeat(40);
  const qA={model_name:'assists q',model_version:'0.1.0',feature_schema:'nbl_player_pregame_v1',stat_type:'assists',market_data:false,walk_forward:{nb2_alpha_oos:0.2},probability_contract:{max_count:20}};
  const qR={model_name:'rebounds q',model_version:'0.1.0',feature_schema:'nbl_player_pregame_v1',stat_type:'rebounds',market_data:false,walk_forward:{nb2_alpha_oos:0.25},probability_contract:{max_count:30}};
  const prior={schema_version:'nbl_historical_prior_snapshot_v1',market_data:false,snapshot_revision:'snap123',players:{testguard:{player_key:'testguard',last_team:'Sydney Kings',last_season:'2025-2026',last_match_time:'2026-02-01T00:00:00Z',features:{player_assists_mean_3:5}}},teams:{}};
  const manifest={schema_version:'nbl_runtime_assets_v1',market_data:false,asset_revision:'abcdef1234567890',qbase:{assists:{path:'model/qbase_assists_v0.1.0.json',canonical_sha256:await sha256Json(qA)},rebounds:{path:'model/qbase_rebounds_v0.1.0.json',canonical_sha256:await sha256Json(qR)}},prior_snapshot:{path:'prior_snapshot.json',canonical_sha256:await sha256Json(prior),snapshot_revision:'snap123'}};
  const schedule={data:[{id:'fixture-1',start_time_datetime:new Date(Date.now()+2*86400000).toISOString(),match_status:'scheduled',home_team:{id:'home-id',name:'Sydney Kings'},away_team:{id:'away-id',name:'Perth Wildcats'},venue:{id:'v1',name:'Arena'}}]};
  const original=globalThis.fetch;globalThis.fetch=async url=>{url=String(url);if(url.endsWith('/commits/main'))return jr({sha:commit});if(url.endsWith('/data/manifest.json'))return jr(manifest);if(url.endsWith('/data/model/qbase_assists_v0.1.0.json'))return jr(qA);if(url.endsWith('/data/model/qbase_rebounds_v0.1.0.json'))return jr(qR);if(url.endsWith('/data/prior_snapshot.json'))return jr(prior);if(url.includes('/matches/in/season/2026/all'))return jr(schedule);if(url.includes('/players/for/team/home-id/in/season/2026'))return jr({data:[{id:'p1',name:'Test Guard',position:'G'}]});if(url.includes('/players/for/team/away-id/in/season/2026'))return jr({data:[{id:'p2',name:'Away Guard',position:'G'}]});return jr({error:'unexpected '+url},404);};
  return {manifest,restore:()=>globalThis.fetch=original};
}
const runId='a'.repeat(64);
async function req(run,method,path,body){return run.fetch(new Request(`https://example.test/v1/match-runs/${runId}${path}`,{method,headers:{'content-type':'application/json'},...(body===undefined?{}:{body:JSON.stringify(body)})}));}
function research(rev){return {schema_version:'nbl_fixture_research_v1',market_data:false,fixture_id:'fixture-1',pack_revision:rev,run_mode:'BOTH',checked_at:'2026-09-06T01:00:00Z',sources:{official:{url:'https://nbl.com.au/news/x',title:'Official',checked_at:'2026-09-06T00:55:00Z'},report:{url:'https://example.com/report',title:'Report',checked_at:'2026-09-06T00:56:00Z'}},fixture_context:{status:'scheduled',source_ids:['official']},players:[{player_id:'p1',player_name:'Test Guard',team:'Sydney Kings',availability_status:'ACTIVE',availability_source_ids:['official'],projected_minutes:{low:27,mean:30,high:33,source_ids:['official','report']},role:{state:'RETURNING_SAME',creation_role:'PRIMARY',frontcourt_role:'GUARD',source_ids:['report']}}]};}
function projections(){return [{player_id:'p1',player_name:'Test Guard',team:'Sydney Kings',heads:{assists:{qbase_mean:5.2,confidence:'B',fragility:'LOW',scenarios:[{id:'base',weight:1,mean:5.4,method:'QBASE_MINUTES_RECOMPUTE',evidence_source_ids:['report'],assumptions:[]}]},rebounds:{qbase_mean:4,confidence:'B',fragility:'LOW',scenarios:[{id:'base',weight:1,mean:4.1,method:'QBASE_RUNTIME_SCORE',evidence_source_ids:['report'],assumptions:[]}]}}}];}

test('persistent run initializes cleanly, serves research seed, checkpoints, freezes and preserves receipt',async()=>{
  const h=await harness();try{
    const run=new NblMatchRun(new MemoryState(),{});
    let res=await req(run,'POST','',{fixture_id:'fixture-1',season_start:2026,run_mode:'BOTH'});assert.equal(res.status,200);let d=await res.json();assert.equal(d.status,'RESEARCH_PENDING');assert.equal(d.lock.asset_revision,h.manifest.asset_revision);
    res=await req(run,'GET','/research');d=await res.json();assert.equal(d.home_roster[0].nbl_history_status,'NBL_HISTORY_AVAILABLE');assert.equal(d.away_roster[0].nbl_history_status,'PRIOR_COMP_TRANSLATION_REQUIRED');
    res=await req(run,'POST','/research',research(h.manifest.asset_revision));assert.equal(res.status,200);
    res=await req(run,'POST','/compute',{projections:projections()});assert.equal(res.status,200);const f=await res.json();assert.equal(f.status,'FROZEN');assert.match(f.freeze_receipt_sha256,/^[0-9a-f]{64}$/);const stamp=f.frozen_at,receipt=f.freeze_receipt_sha256;
    res=await req(run,'POST','/compute',{projections:[]});d=await res.json();assert.equal(d.frozen_at,stamp);assert.equal(d.freeze_receipt_sha256,receipt);
    res=await req(run,'GET','/players/id%3Ap1');d=await res.json();assert.equal(d.player.player_name,'Test Guard');assert.equal(d.freeze_receipt_sha256,receipt);assert.ok(d.player.heads.assists.probability_grid.half_point_grid.length>0);
  }finally{h.restore();}
});

test('locked asset revision cannot drift',async()=>{
  const h=await harness();try{const run=new NblMatchRun(new MemoryState(),{});await req(run,'POST','',{fixture_id:'fixture-1',season_start:2026,run_mode:'BOTH'});const res=await req(run,'POST','/research',research('wrong'));assert.equal(res.status,422);assert.match((await res.json()).error,/identity mismatch/);}finally{h.restore();}
});
