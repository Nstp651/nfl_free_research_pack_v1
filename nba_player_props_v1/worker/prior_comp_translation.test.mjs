import test from 'node:test';
import assert from 'node:assert/strict';
import { buildPriorCompFeaturePatch, translatePrior } from './prior_comp_translation.js';

const promoted={status:'PROMOTED',market_data:false,head:'assists',version:'test-v1',routes:[{competition:'NCAA_D1',intercept:-.1,log_rate_coef:.9,minutes_coef:.05,role_share_coef:.1,uncertainty_multiplier:1.35,min_sample_games:12,version:'ncaa-v1'}]};

test('unpromoted translation artifacts are hard blocked',()=>{
  assert.throws(()=>translatePrior({...promoted,status:'EXPERIMENTAL'},{competition:'NCAA_D1',games:30,minutes_per_game:32,stat_per_min:.2}),/not promoted/);
});

test('no universal competition fallback is allowed',()=>{
  assert.throws(()=>translatePrior(promoted,{competition:'G_LEAGUE',games:30,minutes_per_game:32,stat_per_min:.2}),/no empirically validated route/);
});

test('competition sample minimum is enforced',()=>{
  assert.throws(()=>translatePrior(promoted,{competition:'NCAA_D1',games:5,minutes_per_game:32,stat_per_min:.2}),/insufficient/);
});

test('validated route returns rate plus explicit uncertainty',()=>{
  const t=translatePrior(promoted,{competition:'NCAA_D1',games:30,minutes_per_game:32,stat_per_min:.2,role_share:.3});
  assert.equal(t.method,'PRIOR_COMP_TRANSLATION'); assert.equal(t.uncertainty_multiplier,1.35); assert.ok(t.translated_stat_per_min>0);
  const p=buildPriorCompFeaturePatch('assists',t,28); assert.equal(p.minutes_l5,28); assert.ok(p.assists_l5>0);
});
