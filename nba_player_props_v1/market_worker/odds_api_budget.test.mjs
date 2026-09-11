import test from 'node:test';
import assert from 'node:assert/strict';
import {NBA_PROP_MARKETS,budgetSnapshot,estimatedEventCredits,estimatedSlateCredits} from './odds_api_budget.js';

test('four prop keys in one region cost up to 4 credits per current event call',()=>{
  assert.equal(NBA_PROP_MARKETS.length,4);
  assert.equal(estimatedEventCredits({}),4);
});

test('ten-game and fifteen-game current slate estimates are deterministic',()=>{
  assert.equal(estimatedSlateCredits({games:10}),40);
  assert.equal(estimatedSlateCredits({games:15}),60);
});

test('multiple regions multiply current event-odds cost',()=>{
  assert.equal(estimatedEventCredits({regions:2}),8);
});

test('20k monthly plan exposes simple slate budget receipt',()=>{
  const out=budgetSnapshot({games:10});
  assert.equal(out.monthly_credits,20000);
  assert.equal(out.estimated_slate_credits,40);
  assert.equal(out.estimated_full_slates_per_month,500);
  assert.equal(out.quota_basis,'CURRENT_EVENT_ODDS_UNIQUE_MARKETS_X_REGIONS');
});
