import test from 'node:test';
import assert from 'node:assert/strict';
import {classifyMarketThreshold,evaluate,sha256Json} from './index.js';

const RUN='a'.repeat(64),RECEIPT='b'.repeat(64),FROZEN_AT='2026-09-06T06:10:00Z';
const assistPolicy={schema_version:'nbl_threshold_validation_v1',direct_validated_thresholds:[2,3,4,5,6,7,8,9],tail_supported_thresholds:[1],extreme_tail_thresholds:[10,11,12,13,14,15,16,17,18,19,20],best_single_eligible_thresholds:[1,2,3,4,5,6,7,8,9],evidence_sha256:'1'.repeat(64)};
const reboundPolicy={schema_version:'nbl_threshold_validation_v1',direct_validated_thresholds:[3,4,5,6,7,8,9,10,11,12],tail_supported_thresholds:[1,2,13],extreme_tail_thresholds:[14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30],best_single_eligible_thresholds:[1,2,3,4,5,6,7,8,9,10,11,12],evidence_sha256:'2'.repeat(64)};
const frozenPlayer={player_id:'p1',player_name:'Test Guard',team:'Sydney Kings',heads:{
  assists:{confidence:'B',fragility:'LOW',qbase_anchor:{max_count:20,threshold_validation_policy:assistPolicy},probability_grid:{max_count:20,half_point_grid:[{line:4.5,over:.55,push:0,under:.45},{line:8.5,over:.6,push:0,under:.4},{line:11.5,over:.25,push:0,under:.75}],integer_push_grid:[{line:5,over:.35,push:.2,under:.45}]}},
  rebounds:{confidence:'C',fragility:'MEDIUM',qbase_anchor:{max_count:30,threshold_validation_policy:reboundPolicy},probability_grid:{max_count:30,half_point_grid:[{line:5.5,over:.4,push:0,under:.6},{line:12.5,over:.2,push:0,under:.8}],integer_push_grid:[{line:6,over:.25,push:.15,under:.6}]}}
}};
const PLAYER_HASH=await sha256Json(frozenPlayer);
const runBody={status:'FROZEN',freeze:{status:'FROZEN',fixture_id:'fixture-1',freeze_receipt_sha256:RECEIPT,frozen_at:FROZEN_AT,players:[{player_key:'id:p1',player_model_sha256:PLAYER_HASH,player_id:'p1',player_name:'Test Guard',team:'Sydney Kings'}]}};
const playerBody={freeze_receipt_sha256:RECEIPT,frozen_at:FROZEN_AT,player_model_sha256:PLAYER_HASH,player:frozenPlayer};
function market(overrides={}){return {fixture_id:'fixture-1',player_name:'Test Guard',stat_type:'assists',side:'over',threshold:4.5,decimal_price:2.0,bookmaker:'Book A',captured_at:'2026-09-06T06:11:00Z',source_type:'screenshot',...overrides};}
function mockResearch({run=runBody,player=playerBody}={}){const calls=[];globalThis.fetch=async url=>{calls.push(String(url));if(String(url).endsWith(`/v1/match-runs/${RUN}`))return new Response(JSON.stringify(run),{status:200});if(String(url).includes(`/v1/match-runs/${RUN}/players/`))return new Response(JSON.stringify(player),{status:200});return new Response(JSON.stringify({error:'unexpected'}),{status:404});};return calls;}
async function mockCustomPlayer(player){const hash=await sha256Json(player),run={...runBody,freeze:{...runBody.freeze,players:[{...runBody.freeze.players[0],player_model_sha256:hash}]}},body={...playerBody,player_model_sha256:hash,player};return mockResearch({run,player:body});}
const env={RESEARCH_BASE:'https://research.example.workers.dev'};

test('refuses all market evaluation before immutable P_model freeze',async()=>{
  const old=globalThis.fetch;try{mockResearch({run:{status:'RESEARCH_COMPLETE',freeze:null}});await assert.rejects(()=>evaluate({run_id:RUN,expected_freeze_receipt_sha256:RECEIPT,markets:[market()]},env),/P_MODEL_STATUS must be FROZEN/);}finally{globalThis.fetch=old;}
});

test('requires exact caller freeze receipt binding',async()=>{
  const old=globalThis.fetch;try{mockResearch();await assert.rejects(()=>evaluate({run_id:RUN,expected_freeze_receipt_sha256:'c'.repeat(64),markets:[market()]},env),/Freeze receipt mismatch/);}finally{globalThis.fetch=old;}
});

test('rejects market observations captured before P_model freeze',async()=>{
  const old=globalThis.fetch;try{mockResearch();await assert.rejects(()=>evaluate({run_id:RUN,expected_freeze_receipt_sha256:RECEIPT,markets:[market({captured_at:'2026-09-06T06:09:59Z'})]},env),/predates P_model freeze/);}finally{globalThis.fetch=old;}
});

test('half-point EV is exact, positive and bound to frozen player receipt',async()=>{
  const old=globalThis.fetch;try{const calls=mockResearch();const out=await evaluate({run_id:RUN,expected_freeze_receipt_sha256:RECEIPT,markets:[market()]},env);assert.equal(out.p_model_status,'FROZEN');assert.equal(out.p_model_mutated,false);assert.equal(out.market_records_evaluated,1);assert.equal(out.positive_edges.length,1);assert.equal(out.best_single.player_name,'Test Guard');assert.ok(Math.abs(out.best_single.ev_per_unit-.10)<1e-12);assert.equal(out.best_single.p_win,.55);assert.equal(out.best_single.p_push,0);assert.equal(out.best_single.threshold_validation,'DIRECT_VALIDATED');assert.equal(out.best_single.grade,'B+');assert.equal(out.best_single.best_single_eligible,true);assert.equal(out.best_single.best_single_exclusion_reason,null);assert.equal(calls.length,2);assert.ok(calls[1].endsWith('/players/id%3Ap1'));}finally{globalThis.fetch=old;}
});

test('huge-EV EXTREME_TAIL stays ranked but cannot displace eligible direct BEST SINGLE',async()=>{
  const old=globalThis.fetch;try{mockResearch();const out=await evaluate({run_id:RUN,expected_freeze_receipt_sha256:RECEIPT,markets:[market({threshold:11.5,decimal_price:8}),market({threshold:8.5,decimal_price:2})]},env);assert.equal(out.positive_edges[0].threshold,11.5);assert.equal(out.positive_edges[0].threshold_validation,'EXTREME_TAIL');assert.equal(out.positive_edges[0].grade,'C+');assert.equal(out.positive_edges[0].best_single_eligible,false);assert.equal(out.positive_edges[0].best_single_exclusion_reason,'EXTREME_TAIL');assert.equal(out.best_single.threshold,8.5);assert.equal(out.best_single.threshold_validation,'DIRECT_VALIDATED');}finally{globalThis.fetch=old;}
});

test('TAIL_SUPPORTED threshold follows audit eligibility and grade ceiling',async()=>{
  const old=globalThis.fetch;try{const player={...frozenPlayer,heads:{...frozenPlayer.heads,rebounds:{...frozenPlayer.heads.rebounds,confidence:'B',fragility:'LOW'}}};await mockCustomPlayer(player);const out=await evaluate({run_id:RUN,expected_freeze_receipt_sha256:RECEIPT,markets:[market({stat_type:'rebounds',threshold:12.5,decimal_price:6})]},env);const row=out.evaluated[0];assert.equal(row.threshold_validation,'TAIL_SUPPORTED');assert.equal(row.grade,'B');assert.equal(row.best_single_eligible,false);assert.equal(row.best_single_exclusion_reason,'THRESHOLD_VALIDATION_NOT_BEST_SINGLE_ELIGIBLE');assert.equal(out.best_single,null);assert.equal(out.no_forced_bet,true);}finally{globalThis.fetch=old;}
});

test('legacy frozen QBASE receipt resolves the same audit policy without mutation',()=>{
  const legacyHead={qbase_anchor:{qbase_sha256:'8e714c693f0a1eddfd3989c6717f120079ec3fa0e1c42e1eaf5c1d670d265eab',max_count:20}};
  const direct=classifyMarketThreshold(legacyHead,8.5),extreme=classifyMarketThreshold(legacyHead,11.5);
  assert.equal(direct.threshold_validation,'DIRECT_VALIDATED');
  assert.equal(direct.threshold_validation_evidence_sha256,'a77126faacc0304962060b76caae79a358de2723d10210c2be3ff67adcd0d446');
  assert.equal(extreme.threshold_validation,'EXTREME_TAIL');
  assert.equal(extreme.threshold_best_single_supported,false);
});

test('confidence C and HIGH fragility deterministically cap huge direct EV at PASS',async()=>{
  const old=globalThis.fetch;try{const player={...frozenPlayer,heads:{...frozenPlayer.heads,assists:{...frozenPlayer.heads.assists,confidence:'C',fragility:'HIGH'}}};await mockCustomPlayer(player);const input={run_id:RUN,expected_freeze_receipt_sha256:RECEIPT,markets:[market({decimal_price:4})]};const first=await evaluate(input,env);await mockCustomPlayer(player);const second=await evaluate(input,env);assert.equal(first.evaluated[0].grade,'PASS');assert.equal(first.evaluated[0].best_single_eligible,false);assert.equal(first.evaluated[0].best_single_exclusion_reason,'CONFIDENCE_C');assert.deepEqual(first.evaluated[0],second.evaluated[0]);}finally{globalThis.fetch=old;}
});

test('integer line uses push-aware EV and fair price',async()=>{
  const old=globalThis.fetch;try{mockResearch();const out=await evaluate({run_id:RUN,expected_freeze_receipt_sha256:RECEIPT,markets:[market({threshold:5,decimal_price:3})]},env);const row=out.evaluated[0];assert.equal(row.p_win,.35);assert.equal(row.p_push,.2);assert.equal(row.p_loss,.45);assert.ok(Math.abs(row.ev_per_unit-.25)<1e-12);assert.ok(Math.abs(row.conditional_win_probability-(.35/.8))<1e-12);assert.ok(Math.abs(row.fair_decimal_price-(.8/.35))<1e-12);}finally{globalThis.fetch=old;}
});

test('keeps only best price for exact frozen player/stat/side/threshold',async()=>{
  const old=globalThis.fetch;try{const calls=mockResearch();const out=await evaluate({run_id:RUN,expected_freeze_receipt_sha256:RECEIPT,markets:[market({decimal_price:1.91,bookmaker:'Book Low'}),market({decimal_price:2.05,bookmaker:'Book High'})]},env);assert.equal(out.market_records_received,2);assert.equal(out.market_records_evaluated,1);assert.equal(out.evaluated[0].bookmaker,'Book High');assert.equal(out.evaluated[0].decimal_price,2.05);assert.equal(calls.length,2);}finally{globalThis.fetch=old;}
});

test('dedupes mixed ID and name-only sources after frozen player resolution',async()=>{
  const old=globalThis.fetch;try{const calls=mockResearch();const out=await evaluate({run_id:RUN,expected_freeze_receipt_sha256:RECEIPT,markets:[market({player_id:'p1',decimal_price:1.95,bookmaker:'API'}),market({player_id:null,decimal_price:2.10,bookmaker:'Bet365'})]},env);assert.equal(out.market_records_received,2);assert.equal(out.market_records_evaluated,1);assert.equal(out.evaluated[0].bookmaker,'Bet365');assert.equal(out.evaluated[0].frozen_player_id,'p1');assert.equal(calls.length,2);}finally{globalThis.fetch=old;}
});

test('name-only screenshot row resolves server frozen player key',async()=>{
  const old=globalThis.fetch;try{const calls=mockResearch();const out=await evaluate({run_id:RUN,expected_freeze_receipt_sha256:RECEIPT,markets:[market({player_id:null})]},env);assert.equal(out.evaluated[0].frozen_player_id,'p1');assert.ok(calls[1].endsWith('/players/id%3Ap1'));}finally{globalThis.fetch=old;}
});

test('rejects unsupported threshold rather than interpolating',async()=>{
  const old=globalThis.fetch;try{mockResearch();await assert.rejects(()=>evaluate({run_id:RUN,expected_freeze_receipt_sha256:RECEIPT,markets:[market({threshold:4.25})]},env),/integer\/half-point/);}finally{globalThis.fetch=old;}
});

test('rejects player receipt drift after run receipt was verified',async()=>{
  const old=globalThis.fetch;try{mockResearch({player:{...playerBody,freeze_receipt_sha256:'d'.repeat(64)}});await assert.rejects(()=>evaluate({run_id:RUN,expected_freeze_receipt_sha256:RECEIPT,markets:[market()]},env),/Frozen player receipt\/timestamp mismatch/);}finally{globalThis.fetch=old;}
});

test('rejects frozen player hash receipt drift',async()=>{
  const old=globalThis.fetch;try{mockResearch({player:{...playerBody,player_model_sha256:'d'.repeat(64)}});await assert.rejects(()=>evaluate({run_id:RUN,expected_freeze_receipt_sha256:RECEIPT,markets:[market()]},env),/Frozen player hash receipt mismatch/);}finally{globalThis.fetch=old;}
});

test('rejects mutated frozen player payload even with matching run receipt',async()=>{
  const old=globalThis.fetch;try{const mutated={...frozenPlayer,team:'Other Team'};mockResearch({player:{...playerBody,player:mutated}});await assert.rejects(()=>evaluate({run_id:RUN,expected_freeze_receipt_sha256:RECEIPT,markets:[market()]},env),/Frozen player payload hash mismatch/);}finally{globalThis.fetch=old;}
});

test('no positive EV produces no forced bet',async()=>{
  const old=globalThis.fetch;try{mockResearch();const out=await evaluate({run_id:RUN,expected_freeze_receipt_sha256:RECEIPT,markets:[market({decimal_price:1.5})]},env);assert.equal(out.positive_edges.length,0);assert.equal(out.best_single,null);assert.equal(out.no_forced_bet,true);}finally{globalThis.fetch=old;}
});
