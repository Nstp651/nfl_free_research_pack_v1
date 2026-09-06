import test from 'node:test';
import assert from 'node:assert/strict';
import {evaluate} from './index.js';

const RUN='a'.repeat(64),RECEIPT='b'.repeat(64),FROZEN_AT='2026-09-06T06:10:00Z';
const runBody={status:'FROZEN',freeze:{status:'FROZEN',fixture_id:'fixture-1',freeze_receipt_sha256:RECEIPT,frozen_at:FROZEN_AT,players:[{player_key:'id:p1',player_id:'p1',player_name:'Test Guard',team:'Sydney Kings'}]}};
const playerBody={freeze_receipt_sha256:RECEIPT,frozen_at:FROZEN_AT,player:{player_id:'p1',player_name:'Test Guard',team:'Sydney Kings',heads:{
  assists:{confidence:'B',fragility:'LOW',probability_grid:{half_point_grid:[{line:4.5,over:.55,push:0,under:.45}],integer_push_grid:[{line:5,over:.35,push:.2,under:.45}]}},
  rebounds:{confidence:'C',fragility:'MEDIUM',probability_grid:{half_point_grid:[{line:5.5,over:.4,push:0,under:.6}],integer_push_grid:[{line:6,over:.25,push:.15,under:.6}]}}
}}};
function market(overrides={}){return {fixture_id:'fixture-1',player_name:'Test Guard',stat_type:'assists',side:'over',threshold:4.5,decimal_price:2.0,bookmaker:'Book A',captured_at:'2026-09-06T06:11:00Z',source_type:'screenshot',...overrides};}
function mockResearch({run=runBody,player=playerBody}={}){const calls=[];globalThis.fetch=async url=>{calls.push(String(url));if(String(url).endsWith(`/v1/match-runs/${RUN}`))return new Response(JSON.stringify(run),{status:200});if(String(url).includes(`/v1/match-runs/${RUN}/players/`))return new Response(JSON.stringify(player),{status:200});return new Response(JSON.stringify({error:'unexpected'}),{status:404});};return calls;}
const env={RESEARCH_BASE:'https://research.example.workers.dev'};

test('refuses all market evaluation before immutable P_model freeze',async()=>{
  const old=globalThis.fetch;try{mockResearch({run:{status:'RESEARCH_COMPLETE',freeze:null}});await assert.rejects(()=>evaluate({run_id:RUN,expected_freeze_receipt_sha256:RECEIPT,markets:[market()]},env),/P_MODEL_STATUS must be FROZEN/);}finally{globalThis.fetch=old;}
});

test('requires exact caller freeze receipt binding',async()=>{
  const old=globalThis.fetch;try{mockResearch();await assert.rejects(()=>evaluate({run_id:RUN,expected_freeze_receipt_sha256:'c'.repeat(64),markets:[market()]},env),/Freeze receipt mismatch/);}finally{globalThis.fetch=old;}
});

test('half-point EV is exact, positive and bound to frozen player receipt',async()=>{
  const old=globalThis.fetch;try{const calls=mockResearch();const out=await evaluate({run_id:RUN,expected_freeze_receipt_sha256:RECEIPT,markets:[market()]},env);assert.equal(out.p_model_status,'FROZEN');assert.equal(out.p_model_mutated,false);assert.equal(out.market_records_evaluated,1);assert.equal(out.positive_edges.length,1);assert.equal(out.best_single.player_name,'Test Guard');assert.ok(Math.abs(out.best_single.ev_per_unit-.10)<1e-12);assert.equal(out.best_single.p_win,.55);assert.equal(out.best_single.p_push,0);assert.equal(calls.length,2);assert.ok(calls[1].endsWith('/players/id%3Ap1'));}finally{globalThis.fetch=old;}
});

test('integer line uses push-aware EV and fair price',async()=>{
  const old=globalThis.fetch;try{mockResearch();const out=await evaluate({run_id:RUN,expected_freeze_receipt_sha256:RECEIPT,markets:[market({threshold:5,decimal_price:3})]},env);const row=out.evaluated[0];assert.equal(row.p_win,.35);assert.equal(row.p_push,.2);assert.equal(row.p_loss,.45);assert.ok(Math.abs(row.ev_per_unit-.25)<1e-12);assert.ok(Math.abs(row.conditional_win_probability-(.35/.8))<1e-12);assert.ok(Math.abs(row.fair_decimal_price-(.8/.35))<1e-12);}finally{globalThis.fetch=old;}
});

test('keeps only best price for exact player/stat/side/threshold',async()=>{
  const old=globalThis.fetch;try{const calls=mockResearch();const out=await evaluate({run_id:RUN,expected_freeze_receipt_sha256:RECEIPT,markets:[market({decimal_price:1.91,bookmaker:'Book Low'}),market({decimal_price:2.05,bookmaker:'Book High'})]},env);assert.equal(out.market_records_received,2);assert.equal(out.market_records_evaluated,1);assert.equal(out.evaluated[0].bookmaker,'Book High');assert.equal(out.evaluated[0].decimal_price,2.05);assert.equal(calls.length,2);}finally{globalThis.fetch=old;}
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

test('no positive EV produces no forced bet',async()=>{
  const old=globalThis.fetch;try{mockResearch();const out=await evaluate({run_id:RUN,expected_freeze_receipt_sha256:RECEIPT,markets:[market({decimal_price:1.5})]},env);assert.equal(out.positive_edges.length,0);assert.equal(out.best_single,null);assert.equal(out.no_forced_bet,true);}finally{globalThis.fetch=old;}
});
