import test from 'node:test';
import assert from 'node:assert/strict';
import {NBA_PROP_MARKETS,budgetSnapshot,estimatedEventCredits,estimatedSlateCredits} from './odds_api_budget.js';

test('four prop keys in one region cost 40 credits per event',()=>{
  assert.equal(NBA_PROP_MARKETS.length,4);
  assert.equal(estimatedEventCredits({}),40);
});

test('ten-game and fifteen-game slate estimates are deterministic',()=>{
  assert.equal(estimatedSlateCredits({games:10}),400);
  assert.equal(estimatedSlateCredits({games:15}),600);
});

test('multiple regions multiply cost',()=>{
  assert.equal(estimatedEventCredits({regions:2}),80);
});

test('20k monthly plan exposes simple slate budget receipt',()=>{
  const out=budgetSnapshot({games:10});
  assert.equal(out.monthly_credits,20000);
  assert.equal(out.estimated_slate_credits,400);
  assert.equal(out.estimated_full_slates_per_month,50);
});
