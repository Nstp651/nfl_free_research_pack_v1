import test from 'node:test';
import assert from 'node:assert/strict';
import { applyTypedTransform, scoreQbase, scoreRuntime } from './runtime_score.js';

const artifact = {
  family:'regularized_poisson_glm', head:'assists', trained_before_season:2026,
  features:['minutes_l5','start_rate_l5','assists_l5','assist_share_l5','team_assists_l5','opponent_assists_allowed_l5','team_possessions_l5'],
  medians:[30,.5,5,.2,25,25,100], centers:[30,.5,5,.2,25,25,100], scales:[5,.3,2,.1,4,4,5], coefficients:[.2,.1,.3,.15,.05,.04,.02], intercept:1, dispersion_alpha:.12
};
const base = {minutes_l5:30,start_rate_l5:.5,assists_l5:5,assist_share_l5:.2,team_assists_l5:25,opponent_assists_allowed_l5:25,team_possessions_l5:100};

test('portable QBASE score is deterministic', async()=>{
  const a=await scoreQbase(artifact,base); const b=await scoreQbase(artifact,base);
  assert.equal(a.mean,b.mean); assert.equal(a.quant_input_receipt_sha256,b.quant_input_receipt_sha256);
});

test('minutes recompute changes model features, not mean directly', async()=>{
  const r=applyTypedTransform(artifact,base,{type:'MINUTES_RECOMPUTE',projected_minutes:36,starter_probability:.9});
  assert.equal(r.features.minutes_l5,36); assert.equal(r.features.start_rate_l5,.9);
  const scored=await scoreRuntime(artifact,base,[{type:'MINUTES_RECOMPUTE',projected_minutes:36,starter_probability:.9}]);
  assert.ok(scored.mean>0); assert.equal(scored.transform_receipts[0].type,'MINUTES_RECOMPUTE');
});

test('role recompute is whitelist and bounded',()=>{
  assert.throws(()=>applyTypedTransform(artifact,base,{type:'ROLE_OPPORTUNITY_RECOMPUTE',inputs:{arbitrary_mean:9}}),/unsupported role feature/);
  assert.throws(()=>applyTypedTransform(artifact,base,{type:'ROLE_OPPORTUNITY_RECOMPUTE',inputs:{assist_share_l5:1.5}}),/must be in/);
  const r=applyTypedTransform(artifact,base,{type:'ROLE_OPPORTUNITY_RECOMPUTE',inputs:{assists_l5:7,assist_share_l5:.3}});
  assert.equal(r.features.assists_l5,7); assert.equal(r.features.assist_share_l5,.3);
});

test('lineup dependency transform is head specific',()=>{
  const r=applyTypedTransform(artifact,base,{type:'LINEUP_DEPENDENCY_RECOMPUTE',inputs:{team_assists_l5:28,opponent_assists_allowed_l5:27}});
  assert.equal(r.features.team_assists_l5,28);
  assert.throws(()=>applyTypedTransform(artifact,base,{type:'LINEUP_DEPENDENCY_RECOMPUTE',inputs:{team_rebounds_l5:50}}),/unsupported lineup feature/);
});

test('free-form transform and invalid head artifact are rejected',()=>{
  assert.throws(()=>applyTypedTransform(artifact,base,{type:'NARRATIVE_MEAN_OVERRIDE',mean:8}),/unsupported transform/);
  assert.throws(()=>scoreQbase({...artifact,head:'points'},base),/artifact head required/);
});
