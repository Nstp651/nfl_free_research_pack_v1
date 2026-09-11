import test from 'node:test';
import assert from 'node:assert/strict';
import {chooseBestExactPrices,evaluateExactMarket,findExactFrozenLine,rankPositiveEdges} from './market_core.js';

const grid={
  half_point_grid:[{line:4.5,over:0.55,under:0.45}],
  integer_push_grid:[{line:5,over:0.40,push:0.20,under:0.40}],
};

function row(overrides={}){
  return {
    game_id:'0022600001',player_id:'2544',player_name:'Example Player',stat_type:'assists',side:'over',threshold:4.5,
    decimal_price:2.0,bookmaker:'Book A',captured_at:'2026-10-20T12:00:00Z',...overrides,
  };
}

test('half-point market has no push and exact EV',()=>{
  const out=evaluateExactMarket(row(),grid);
  assert.equal(out.p_push,0);
  assert.ok(Math.abs(out.ev_per_unit-0.10)<1e-12);
  assert.ok(Math.abs(out.push_adjusted_market_probability-0.5)<1e-12);
  assert.ok(Math.abs(out.push_adjusted_probability_edge-0.05)<1e-12);
  assert.equal(out.positive_ev,true);
});

test('integer market is push-aware with tracker-compatible edge',()=>{
  const out=evaluateExactMarket(row({threshold:5,decimal_price:2.1}),grid);
  assert.equal(out.p_push,0.20);
  assert.ok(Math.abs(out.ev_per_unit-0.04)<1e-12);
  assert.ok(Math.abs(out.conditional_win_probability-0.5)<1e-12);
  assert.ok(Math.abs(out.push_adjusted_market_probability-(0.8/2.1))<1e-12);
  assert.ok(Math.abs(out.push_adjusted_probability_edge-(0.4-0.8/2.1))<1e-12);
  assert.ok(Math.abs(out.fair_decimal_price-2.0)<1e-12);
});

test('no interpolation is allowed',()=>{
  assert.throws(()=>findExactFrozenLine(grid,5.5),/unavailable/);
});

test('best valid price wins for exact duplicate market',()=>{
  const best=chooseBestExactPrices([
    row({decimal_price:1.95,bookmaker:'A'}),
    row({decimal_price:2.05,bookmaker:'B'}),
    row({decimal_price:2.00,bookmaker:'C'}),
  ]);
  assert.equal(best.length,1);
  assert.equal(best[0].decimal_price,2.05);
  assert.equal(best[0].bookmaker,'B');
});

test('positive edges rank by EV across both heads',()=>{
  const ranked=rankPositiveEdges([
    {...row(),stat_type:'assists',ev_per_unit:0.05,positive_ev:true},
    {...row(),stat_type:'rebounds',ev_per_unit:0.12,positive_ev:true},
    {...row(),stat_type:'assists',ev_per_unit:-0.01,positive_ev:false},
  ]);
  assert.equal(ranked.length,2);
  assert.equal(ranked[0].stat_type,'rebounds');
  assert.equal(ranked[0].positive_edge_rank,1);
});
