import test from 'node:test';
import assert from 'node:assert/strict';
import {resolveOddsEvent,eventOrientation} from './index.js';

const fixture={
  id:'fixture-1',
  start_time:'2026-09-19T09:30:00Z',
  home_team:{name:'Melbourne United'},
  away_team:{name:'Adelaide 36ers'}
};

const reversed={
  id:'evt-reversed',
  sport_key:'basketball_nbl',
  commence_time:'2026-09-19T09:36:00Z',
  home_team:'Adelaide 36ers',
  away_team:'Melbourne United'
};

const exact={
  id:'evt-exact',
  sport_key:'basketball_nbl',
  commence_time:'2026-09-19T09:30:00Z',
  home_team:'Melbourne United',
  away_team:'Adelaide 36ers'
};

test('accepts exact NBL home-away orientation',()=>{
  assert.equal(eventOrientation(exact,fixture),'exact');
  assert.equal(resolveOddsEvent([exact],fixture).id,'evt-exact');
});

test('accepts reversed bookmaker/API team orientation when pair and tipoff are unique',()=>{
  assert.equal(eventOrientation(reversed,fixture),'swapped');
  assert.equal(resolveOddsEvent([reversed],fixture).id,'evt-reversed');
});

test('rejects unrelated teams even at the same tipoff',()=>{
  assert.throws(()=>resolveOddsEvent([{...reversed,id:'wrong',home_team:'Perth Wildcats'}],fixture),/found 0/);
});

test('still rejects ambiguity if both exact and swapped representations are present',()=>{
  assert.throws(()=>resolveOddsEvent([exact,reversed],fixture),/found 2/);
});
