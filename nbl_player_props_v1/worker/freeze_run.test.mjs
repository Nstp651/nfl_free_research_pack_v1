import test from 'node:test';
import assert from 'node:assert/strict';
import {NblMatchRun} from './freeze_run.js';
import {sha256Json} from './freeze_core.js';

class MemoryStorage{
  constructor(){this.m=new Map();}
  async get(k){return this.m.get(k);}
  async put(k,v){this.m.set(k,v);}
  async transaction(fn){return fn(this);}
}
class MemoryState{
  constructor(){this.storage=new MemoryStorage();}
  async blockConcurrencyWhile(fn){return fn();}
}
const jsonResponse=(x,status=200)=>new Response(JSON.stringify(x),{status,headers:{'content-type':'application/json'}});

async function fixtureHarness(){
  const commit='1'.repeat(40);
  const qA={model_name:'assists q',model_version:'0.1.0',feature_schema:'nbl_player_pregame_v1',stat_type:'assists',market_data:false,walk_forward:{nb2_alpha_oos:0.2},probability_contract:{max_count:20}};
  const qR={model_name:'rebounds q',model_version:'0.1.0',feature_schema:'nbl_player_pregame_v1',stat_type:'rebounds',market_data:false,walk_forward:{nb2_alpha_oos:0.25},probability_contract:{max_count:30}};
  const prior={schema_version:'nbl_historical_prior_snapshot_v1',market_data:false,snapshot_revision:'snap123',players:{testguard:{player_key:'testguard',last_team:'Sydney Kings',last_season:'2025-2026',last_match_time:'2026-02-01T00:00:00Z',features:{player_assists_mean_3:5}}},teams:{}};
  const manifest={schema_version:'nbl_runtime_assets_v1',market_data:false,asset_revision:'abcdef1234567890',qbase:{assists:{path:'model/qbase_assists_v0.1.0.json',canonical_sha256:await sha256Json(qA)},rebounds:{path:'model/qbase_rebounds_v0.1.0.json',canonical_sha256:await sha256Json(qR)}},prior_snapshot:{path:'prior_snapshot.json',canonical_sha256:await sha256Json(prior),snapshot_revision:'snap123'}};
  const start=new Date(Date.now()+2*86400000).toISOString();
  const schedule={data:[{id:'fixture-1',start_time_datetime:start,match_status:'scheduled',home_team:{id:'home-id',name:'Sydney Kings'},away_team:{id:'away-id',name:'Perth Wildcats'},venue:{id:'v1',name:'Arena'}}]};
  const homeRoster={data:[{id:'p1',name:'Test Guard',position:'G'}]},awayRoster={data:[{id:'p2',name:'Away Guard',position:'G'}]};
  const original=globalThis.fetch;
  globalThis.fetch=async url=>{
    url=String(url);
    if(url.endsWith('/commits/main'))return jsonResponse({sha:commit});
    if(url.endsWith('/data/manifest.json'))return jsonResponse(manifest);
    if(url.endsWith('/data/model/qbase_assists_v0.1.0.json'))return jsonResponse(qA);
    if(url.endsWith('/data/model/qbase_rebounds_v0.1.0.json'))return jsonResponse(qR);
    if(url.endsWith('/data/prior_snapshot.json'))return jsonResponse(prior);
    if(url.includes('/matches/in/season/2026/all'))return jsonResponse(schedule);
    if(url.includes('/players/for/team/home-id/in/season/2026'))return jsonResponse(homeRoster);
    if(url.includes('/players/for/team/away-id/in/season/2026'))return jsonResponse(awayRoster);
    return jsonResponse({error:'unexpected '+url},404);
  };
  return {manifest,restore:()=>{globalThis.fetch=original;}};
}
function research(packRevision){return {schema_version:'nbl_fixture_research_v1',market_data:false,fixture_id:'fixture-1',pack_revision:packRevision,run_mode:'BOTH',checked_at:'2026-09-06T01:00:00Z',sources:{official:{url:'https://nbl.com.au/news/x',title:'Official',checked_at:'2026-09-06T00:55:00Z'},report:{url:'https://example.com/report',title:'Report',checked_at:'2026-09-06T00:56:00Z'}},fixture_context:{status:'scheduled',source_ids:['official']},players:[{player_id:'p1',player_name:'Test Guard',team:'Sydney Kings',availability_status:'ACTIVE',availability_source_ids:['official'],projected_minutes:{low:27,mean:30,high:33,source_ids:['official','report']},role:{state:'RETURNING_SAME',creation_role:'PRIMARY',frontcourt_role:'GUARD',source_ids:['report']}}]};}
function projections(){return [{player_id:'p1',player_name:'Test Guard',team:'Sydney Kings',heads:{assists:{qbase_mean:5.2,confidence:'B',fragility:'LOW',scenarios:[{id:'base',weight:1,mean:5.4,method:'QBASE_MINUTES_RECOMPUTE',evidence_source_ids:['report'],assumptions:[]}]},rebounds:{qbase_mean:4.0,confidence:'B',fragility:'LOW',scenarios:[{id:'base',weight:1,mean:4.1,method:'QBASE_RUNTIME_SCORE',evidence_source_ids:['report'],assumptions:[]}]}}}];}

async function req(run,method,path,body){return run.fetch(new Request(`https://example.test/v1/match-runs/${'a'.repeat(64)}${path}`,{method,headers:{'content-type':'application/json'},...(body===undefined?{}:{body:JSON.stringify(body)})}));}

test('persistent NBL run locks assets, checkpoints research, freezes atomically and is idempotent',async()=>{
  const h=await fixtureHarness();try{
    const run=new NblMatchRun(new MemoryState(),{});
    let res=await req(run,'POST','',{fixture_id:'fixture-1',season_start:2026,run_mode:'BOTH'});assert.equal(res.status,200);let data=await res.json();assert.equal(data.status,'RESEARCH_PENDING');assert.equal(data.lock.asset_revision,h.manifest.asset_revision);
    res=await req(run,'GET','/research');data=await res.json();assert.equal(data.home_roster[0].nbl_history_status,'NBL_HISTORY_AVAILABLE');assert.equal(data.away_roster[0].nbl_history_status,'PRIOR_COMP_TRANSLATION_REQUIRED');
    res=await req(run,'POST','/research',research(h.manifest.asset_revision));assert.equal(res.status,200);data=await res.json();assert.equal(data.status,'RESEARCH_COMPLETE');
    res=await req(run,'POST','/compute',{projections:projections()});assert.equal(res.status,200);const frozen=await res.json();assert.equal(frozen.status,'FROZEN');assert.equal(frozen.players.length,1);assert.match(frozen.freeze_receipt_sha256,/^[0-9a-f]{64}$/);
    const originalFrozenAt=frozen.frozen_at,originalReceipt=frozen.freeze_receipt_sha256;
    res=await req(run,'POST','/compute',{projections:[]});data=await res.json();assert.equal(data.freeze_receipt_sha256,originalReceipt);assert.equal(data.frozen_at,originalFrozenAt);
    res=await req(run,'GET','/players/id%3Ap1');data=await res.json();assert.equal(data.player.player_name,'Test Guard');assert.equal(data.freeze_receipt_sha256,originalReceipt);assert.ok(data.player.heads.assists.probability_grid.half_point_grid.length>0);
  }finally{h.restore();}
});

test('research identity cannot drift from locked fixture/assets',async()=>{
  const h=await fixtureHarness();try{
    const run=new NblMatchRun(new MemoryState(),{});await req(run,'POST','',{fixture_id:'fixture-1',season_start:2026,run_mode:'BOTH'});
    const c=research('wrong-revision');const res=await req(run,'POST','/research',c);assert.equal(res.status,422);const data=await res.json();assert.match(data.error,/identity mismatch/);
  }finally{h.restore();}
});
