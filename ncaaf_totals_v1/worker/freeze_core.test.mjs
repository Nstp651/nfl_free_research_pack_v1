import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {computeFreeze,verifySources,anchorHash,gridHash,validateFrozenGame,fixed,TEAM_CHECKS,GAME_CHECKS,normalCDF,residualCDF} from './freeze_core.js';
import bundle from './residual_bundle.js';
import {pack,qbase,now,ids,lock,context} from './freeze_test_helpers.mjs';
const contexts=()=>ids.map(context);
const clone=structuredClone;
test('all 51 real source anchors verify; order-independent full eligible freeze; zero market capability',async()=>{
 const old=globalThis.fetch; globalThis.fetch=()=>{throw Error('NETWORK FORBIDDEN');};
 try {
 const begin=performance.now();
 const a=await computeFreeze(pack,qbase,lock,contexts(),now);
 const b=await computeFreeze({...pack,games:[...pack.games].reverse()},{...qbase,games:[...qbase.games].reverse()},{...lock,eligible_game_ids:[...ids].reverse()},contexts().reverse(),now);
 // Eligible identity order is a canonical part of the lock as well.
 assert.equal(a.freeze_receipt_sha256,b.freeze_receipt_sha256);
 assert.equal(a.numerical_output_sha256,b.numerical_output_sha256);
 assert.equal(a.identity_receipt_sha256,b.identity_receipt_sha256);
 assert.equal(a.market_data,false); assert.equal(a.verified_anchor_count,51);
 assert.equal(a.games.length,ids.length);
 for(const g of a.games) assert.equal(g.qbase_probability_grid_sha256,g.frozen_probability_grid_sha256);
 assert.ok(performance.now()-begin<10000);
 console.log('REAL_SOURCE_DETERMINISTIC_TEST',ids.length,'games',Math.round(performance.now()-begin),'ms; synthetic research, NOT a live freeze');
 } finally { globalThis.fetch=old; }
});
for(const [label,mutate] of [
 ['duplicate research', (p,q,l,c)=>p.games.push(p.games[0])],
 ['duplicate QBASE',(p,q)=>q.games.push(q.games[0])],
 ['missing eligible',(p,q)=>q.games=q.games.filter(g=>g.game_id!==ids[0])],
 ['team mismatch',(p,q)=>q.games[0].home_team='wrong'],
 ['bad anchor',(p,q)=>q.games[0].qbase_anchor_sha256='0'.repeat(64)],
 ['missing anchor',(p,q)=>delete q.games[0].qbase_anchor_sha256],
 ['revision mismatch',(p,q)=>q.research_pack_revision='0'.repeat(16)],
 ['model mismatch',(p,q)=>q.qbase_model_sha256='0'.repeat(64)],
 ['null cutoff payload',(p)=>p.games[0].home_profile.current.summary={epa:1}],
 ['missing game research',(p,q,l,c)=>c.pop()],
 ['missing both-team check',(p,q,l,c)=>delete c[0].research.away.qb_backup],
 ['stale research',(p,q,l,c)=>c[0].research.home.qb_backup.checked_at='2020-01-01'],
 ['trigger without deep research',(p,q,l,c)=>c[0].research.deep_triggers=['QB unknown']],
 ['unledgered shift',(p,q,l,c)=>{c[0].contextual_shift=1;c[0].scenarios[0].shift=1;}],
 ['invalid flag',(p,q,l,c)=>c[0].distribution_changed='false'],
 ['unknown input',(p,q,l,c)=>c[0].odds=2],
 ['market marker',(p,q)=>p.market_data=true],
 ['incomplete grid',(p,q)=>q.games[0].probability_grid.pop()],
 ['started fixture',(p)=>p.games.find(g=>g.game_id===ids[0]).fixture.start_utc='2020-01-01']
]) test(label+' fails closed',async()=>{const p=clone(pack),q=clone(qbase),l=clone(lock),c=contexts();mutate(p,q,l,c);await assert.rejects(computeFreeze(p,q,l,c,now));});
test('zero-shift total and grid corruption both rejected',async()=>{
 const a=await computeFreeze(pack,qbase,lock,contexts(),now); const g=a.games[0],q=qbase.games.find(x=>x.game_id===g.game_id);
 await assert.rejects(validateFrozenGame({...g,expected_total_final:g.expected_total_final+1},q));
 const bad=clone(g);bad.probability_grid[0].over-=0.001;bad.probability_grid[0].under+=0.001;
 await assert.rejects(validateFrozenGame(bad,q));
});
test('changed context changes input/output/freeze receipts',async()=>{
 const c=contexts(),a=await computeFreeze(pack,qbase,lock,c,now);c[0].fragility='HIGH';
 const b=await computeFreeze(pack,qbase,lock,c,now);
 for(const k of ['input_sha256','numerical_output_sha256','freeze_receipt_sha256']) assert.notEqual(a[k],b[k]);
});
test('Python canonical and numerical oracle including real 51 anchors, ties, negative zero',async()=>{
 const script=`import sys,json,math\nsys.path.insert(0,'ncaaf_totals_v1/model')\nfrom freeze_identity import qbase_anchor_sha256\nfrom score_slate import residual_cdf\nq=json.load(open('ncaaf_totals_v1/model/slates/2026/2026_01.json'))\nm=json.load(open('ncaaf_totals_v1/model/qbase_v0.1.0.json'))\nxs=[0.,-0.,20.,1.25,2.675,50.1234565]\nd=m['walk_forward']['residual_distribution']\nprint(json.dumps({'fixed':[[format(x,f'.{p}f') for p in [1,6,8]] for x in xs],'anchors':[qbase_anchor_sha256(g) for g in q['games']],'cdf':{k:[residual_cdf(x,v) for x in range(-80,81)] for k,v in d.items()}}))`;
 const oracle=JSON.parse(execFileSync('python',['-c',script],{cwd:new URL('../../',import.meta.url)}));
 assert.deepEqual([0,-0,20,1.25,2.675,50.1234565].map(x=>[1,6,8].map(p=>fixed(x,p))),oracle.fixed);
 assert.deepEqual(await Promise.all(qbase.games.map(anchorHash)),oracle.anchors);
 for(const [k,vals] of Object.entries(oracle.cdf)) vals.forEach((v,i)=>assert.ok(Math.abs(v-residualCDF(i-80,bundle.residuals[k]))<1e-12));
});
test('nonzero shift and changed-variance mixture execute full audited grids',async()=>{
 const c=contexts(),g=c[0];
 const evidence=g.research.home.qb_backup;
 g.ledger=[{id:'material',evidence,pathway:'Synthetic pathway',impact:'Synthetic shift/variance',quantified_basis:'Synthetic oracle test'}];
 g.contextual_shift=1;g.distribution_changed=true;
 g.scenarios=[{id:'a',weight:0.5,shift:-1,residual_scale:1,ledger_ids:['material']},{id:'b',weight:0.5,shift:3,residual_scale:1.2,ledger_ids:['material']}];
 const a=await computeFreeze(pack,qbase,lock,c,now);
 const f=a.games.find(x=>x.game_id===g.game_id);
 assert.equal(f.expected_total_final,f.expected_total_qbase+1);
 assert.notEqual(f.frozen_probability_grid_sha256,f.qbase_probability_grid_sha256);
 assert.equal(a.probability_audit,'PASS');
});
