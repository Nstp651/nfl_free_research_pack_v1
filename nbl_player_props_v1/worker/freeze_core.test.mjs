import test from 'node:test';
import assert from 'node:assert/strict';
import {computeFreeze,marketKeyHits,probabilityGrid,sha256Json} from './freeze_core.js';

const close=(a,b,tol=1e-12)=>assert.ok(Math.abs(a-b)<=tol,`${a} != ${b}`);
const H={server:'a'.repeat(64),assistScenario:'b'.repeat(64),reboundScenario:'c'.repeat(64),priorScenario:'d'.repeat(64),dispersion:'e'.repeat(64)};

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
  players:[{player_id:'p1',player_name:'Test Guard',team:'Sydney Kings',availability_status:'ACTIVE',availability_source_ids:['official'],projected_minutes:{low:27,mean:30,high:33,source_ids:['official','report']},role:{state:'RETURNING_CHANGED',creation_role:'PRIMARY',frontcourt_role:'GUARD',source_ids:['report']},stat_context:{assists:{source_ids:['report'],notes:['Primary creator role researched']},rebounds:{source_ids:['report'],notes:['Guard rebound role researched']}}}]
};}
function qbase(stat){return {model_name:`${stat} q`,model_version:'0.1.0',feature_schema:'nbl_player_pregame_v1',stat_type:stat,market_data:false,walk_forward:{nb2_alpha_oos:0.2},probability_contract:{max_count:stat==='assists'?20:30}};}
function runtimeHead(qbaseMean,mean,confidence,fragility,scenarioReceipt){return {
  qbase_mean:qbaseMean,server_qbase_source:'SERVER_QBASE_RUNTIME_SCORE',server_qbase_receipt_sha256:H.server,server_player_prior_key:'testguard',confidence,fragility,
  scenarios:[{id:'base',weight:1,mean,method:'QBASE_RUNTIME_SCORE',evidence_source_ids:['report'],assumptions:[],quant_input_receipt_sha256:scenarioReceipt}]
};}
function projections(){return [{player_id:'p1',player_name:'Test Guard',team:'Sydney Kings',heads:{
  assists:{...runtimeHead(5.4,5.6,'B','MEDIUM',H.assistScenario),scenarios:[{id:'base',weight:1,mean:5.6,method:'QBASE_MINUTES_RECOMPUTE',evidence_source_ids:['report'],assumptions:[],quant_input_receipt_sha256:H.assistScenario}]},
  rebounds:runtimeHead(4.1,4.2,'B','LOW',H.reboundScenario)
}}];}

test('BOTH freezes atomically with immutable server-attested receipt material',async()=>{
  const f=await computeFreeze(research(),{assists:qbase('assists'),rebounds:qbase('rebounds')},projections(),'2026-09-06T01:05:00Z');
  assert.equal(f.status,'FROZEN');assert.deepEqual(f.requested_heads,['assists','rebounds']);assert.equal(f.audits.atomic_requested_heads,'PASS');assert.equal(f.audits.server_qbase_authority,'PASS');assert.match(f.freeze_receipt_sha256,/^[0-9a-f]{64}$/);assert.equal(f.players[0].heads.assists.final_mean,5.6);assert.equal(f.players[0].heads.assists.server_quantitative_attestation.source,'SERVER_QBASE_RUNTIME_SCORE');assert.equal(f.players[0].heads.assists.server_quantitative_attestation.player_prior_key,'testguard');
});

test('BOTH refuses incomplete stat-specific current research',async()=>{
  const r=research();delete r.players[0].stat_context.rebounds;
  await assert.rejects(()=>computeFreeze(r,{assists:qbase('assists'),rebounds:qbase('rebounds')},projections()),/stat_context missing requested head rebounds/);
  const empty=research();empty.players[0].stat_context.assists.notes=[];
  await assert.rejects(()=>computeFreeze(empty,{assists:qbase('assists'),rebounds:qbase('rebounds')},projections()),/research note required/);
});

test('BOTH refuses missing head and market contamination',async()=>{
  const p=projections();delete p[0].heads.rebounds;
  await assert.rejects(()=>computeFreeze(research(),{assists:qbase('assists'),rebounds:qbase('rebounds')},p),/missing requested head/);
  const r=research();r.sportsbook_price=2.1;assert.ok(marketKeyHits(r).length>0);
  await assert.rejects(()=>computeFreeze(r,{assists:qbase('assists'),rebounds:qbase('rebounds')},projections()),/market boundary/);
});

test('freeze rejects missing/tampered quantitative attestations',async()=>{
  const missing=projections();delete missing[0].heads.assists.server_qbase_source;
  await assert.rejects(()=>computeFreeze(research(),{assists:qbase('assists'),rebounds:qbase('rebounds')},missing),/server_qbase_source invalid/);
  const noReceipt=projections();delete noReceipt[0].heads.rebounds.scenarios[0].quant_input_receipt_sha256;
  await assert.rejects(()=>computeFreeze(research(),{assists:qbase('assists'),rebounds:qbase('rebounds')},noReceipt),/quant input receipt required/);
  const badServer=projections();badServer[0].heads.assists.server_qbase_receipt_sha256='bad';
  await assert.rejects(()=>computeFreeze(research(),{assists:qbase('assists'),rebounds:qbase('rebounds')},badServer),/server QBASE receipt required/);
});

test('prior-comp dispersion override can widen but never narrow QBASE',async()=>{
  const p=projections();p[0].heads.assists={qbase_mean:5.8,server_qbase_source:'PRIOR_COMP_TRANSLATION',server_qbase_receipt_sha256:null,server_player_prior_key:null,confidence:'C',fragility:'HIGH',scenarios:[{id:'prior',weight:1,mean:5.8,method:'PRIOR_COMP_TRANSLATION',evidence_source_ids:['report'],assumptions:[],quant_input_receipt_sha256:H.priorScenario}],dispersion_override:{alpha:0.5,method:'MAX_QBASE_PRIOR_COMP',receipt_sha256:H.dispersion}};
  const f=await computeFreeze(research(),{assists:qbase('assists'),rebounds:qbase('rebounds')},p);assert.equal(f.players[0].heads.assists.dispersion_alpha,0.5);assert.equal(f.players[0].heads.assists.server_quantitative_attestation.source,'PRIOR_COMP_TRANSLATION');
  p[0].heads.assists.dispersion_override.alpha=0.1;await assert.rejects(()=>computeFreeze(research(),{assists:qbase('assists'),rebounds:qbase('rebounds')},p),/may not narrow QBASE/);
});

test('translated head cannot claim a returning-player QBASE receipt',async()=>{
  const p=projections();p[0].heads.assists={qbase_mean:5.8,server_qbase_source:'PRIOR_COMP_TRANSLATION',server_qbase_receipt_sha256:H.server,server_player_prior_key:null,confidence:'C',fragility:'HIGH',scenarios:[{id:'prior',weight:1,mean:5.8,method:'PRIOR_COMP_TRANSLATION',evidence_source_ids:['report'],assumptions:[],quant_input_receipt_sha256:H.priorScenario}],dispersion_override:{alpha:0.5,method:'MAX_QBASE_PRIOR_COMP',receipt_sha256:H.dispersion}};
  await assert.rejects(()=>computeFreeze(research(),{assists:qbase('assists'),rebounds:qbase('rebounds')},p),/translated head cannot claim server QBASE receipt/);
});
