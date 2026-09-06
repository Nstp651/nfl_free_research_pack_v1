import test from 'node:test';
import assert from 'node:assert/strict';
import {computeFreeze,marketKeyHits,probabilityGrid,sha256Json} from './freeze_core.js';

const close=(a,b,tol=1e-12)=>assert.ok(Math.abs(a-b)<=tol,`${a} != ${b}`);

test('NB2 grid matches scipy reference and push partition',()=>{
  const g=probabilityGrid(5,0.2,20);
  close(g.count_pmf[5].probability,0.123046875);
  const half=g.half_point_grid.find(x=>x.line===4.5); close(half.over,0.5);close(half.under,0.5);
  const int=g.integer_push_grid.find(x=>x.line===5);close(int.under,0.5);close(int.push,0.123046875);close(int.over,0.376953125);
});

test('canonical sha ignores object insertion order',async()=>{
  assert.equal(await sha256Json({b:2,a:{d:4,c:3}}),await sha256Json({a:{c:3,d:4},b:2}));
});

function research(){return {
  schema_version:'nbl_fixture_research_v1',market_data:false,fixture_id:'fixture-1',pack_revision:'pack-1',run_mode:'BOTH',checked_at:'2026-09-06T01:00:00Z',
  sources:{official:{url:'https://nbl.com.au/news/x',title:'Official',checked_at:'2026-09-06T00:55:00Z'},report:{url:'https://example.com/report',title:'Report',checked_at:'2026-09-06T00:56:00Z'}},
  fixture_context:{status:'scheduled',source_ids:['official']},
  players:[{player_id:'p1',player_name:'Test Guard',team:'Sydney Kings',availability_status:'ACTIVE',availability_source_ids:['official'],projected_minutes:{low:27,mean:30,high:33,source_ids:['official','report']},role:{state:'RETURNING_CHANGED',creation_role:'PRIMARY',frontcourt_role:'GUARD',source_ids:['report']}}]
};}
function qbase(stat){return {model_name:`${stat} q`,model_version:'0.1.0',feature_schema:'nbl_player_pregame_v1',stat_type:stat,market_data:false,walk_forward:{nb2_alpha_oos:0.2},probability_contract:{max_count:stat==='assists'?20:30}};}
function projections(){return [{player_id:'p1',player_name:'Test Guard',team:'Sydney Kings',heads:{
  assists:{qbase_mean:5.4,confidence:'B',fragility:'MEDIUM',scenarios:[{id:'base',weight:1,mean:5.6,method:'QBASE_MINUTES_RECOMPUTE',evidence_source_ids:['report'],assumptions:[]}]},
  rebounds:{qbase_mean:4.1,confidence:'B',fragility:'LOW',scenarios:[{id:'base',weight:1,mean:4.2,method:'QBASE_RUNTIME_SCORE',evidence_source_ids:['report'],assumptions:[]}]}
}}];}

test('BOTH freezes atomically with immutable receipt material',async()=>{
  const f=await computeFreeze(research(),{assists:qbase('assists'),rebounds:qbase('rebounds')},projections(),'2026-09-06T01:05:00Z');
  assert.equal(f.status,'FROZEN');assert.deepEqual(f.requested_heads,['assists','rebounds']);assert.equal(f.audits.atomic_requested_heads,'PASS');assert.match(f.freeze_receipt_sha256,/^[0-9a-f]{64}$/);assert.equal(f.players[0].heads.assists.final_mean,5.6);
});

test('BOTH refuses missing head and market contamination',async()=>{
  const p=projections();delete p[0].heads.rebounds;
  await assert.rejects(()=>computeFreeze(research(),{assists:qbase('assists'),rebounds:qbase('rebounds')},p),/missing requested head/);
  const r=research();r.sportsbook_price=2.1;assert.ok(marketKeyHits(r).length>0);
  await assert.rejects(()=>computeFreeze(r,{assists:qbase('assists'),rebounds:qbase('rebounds')},projections()),/market boundary/);
});

test('prior-comp dispersion override can widen but never narrow QBASE',async()=>{
  const p=projections();p[0].heads.assists.scenarios=[{id:'prior',weight:1,mean:5.8,method:'PRIOR_COMP_TRANSLATION',evidence_source_ids:['report'],assumptions:[],quant_input_receipt_sha256:'a'.repeat(64)}];p[0].heads.assists.dispersion_override={alpha:0.5,method:'MAX_QBASE_PRIOR_COMP',receipt_sha256:'a'.repeat(64)};
  const f=await computeFreeze(research(),{assists:qbase('assists'),rebounds:qbase('rebounds')},p);assert.equal(f.players[0].heads.assists.dispersion_alpha,0.5);
  p[0].heads.assists.dispersion_override.alpha=0.1;await assert.rejects(()=>computeFreeze(research(),{assists:qbase('assists'),rebounds:qbase('rebounds')},p),/may not narrow QBASE/);
});
