import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {NcaafFreezeRun} from './freeze_run.js';
import {pack,qbase,now,context} from './freeze_test_helpers.mjs';
class Storage {
 data=new Map();
 async get(k){return structuredClone(this.data.get(k));}
 async put(k,v){this.data.set(k,structuredClone(v));}
 async transaction(fn){const saved=structuredClone(this.data);try{return await fn(this);}catch(e){this.data=saved;throw e;}}
}
test('bounded queue, checkpoint restart, atomic failure, immutable idempotent freeze and Python market handoff',async()=>{
 const storage=new Storage(),state={storage,blockConcurrencyWhile:fn=>fn()};
 let run=new NcaafFreezeRun(state,{});
 const realFetch=globalThis.fetch,realNow=Date.now; let calls=[];
 Date.now=()=>now;
 globalThis.fetch=async url=>{
   calls.push(url); let x;
   if(url.endsWith('/commits/main')) x={sha:'a'.repeat(40)};
   else if(url.includes('/data/slates/')) x={...pack,last_checked_at_utc:new Date(now).toISOString()};
   else if(url.includes('/model/slates/')) x=qbase;
   else throw Error('Unexpected network access');
   return new Response(JSON.stringify(x));
 };
 const call=async(path,body)=>{
  const res=await run.fetch(new Request('https://test/v1/freeze-runs/'+'b'.repeat(64)+path,body===undefined?{}:{method:'POST',body:JSON.stringify(body)}));
  return {status:res.status,data:await res.json()};
 };
 try {
  let r=await call('',{season:2026,week:1,window_start:'2026-09-05T00:00:00+10:00',window_end:'2026-09-08T00:00:00+10:00',timing_mode:'MATCHDAY'});
  assert.equal(r.status,200); const ids=r.data.lock.eligible_game_ids;
  assert.ok(ids.length>30); assert.equal(calls.length,3);
  assert.equal((await call('/compute',{})).status,422);
  assert.equal((await call('/games/'+ids[0])).status,422);

  const page1=await call('/research');
  assert.equal(page1.status,200);
  assert.deepEqual(page1.data.batch_game_ids,ids.slice(0,2));
  assert.equal(page1.data.games.length,2);
  const page1Repeat=await call('/research');
  assert.deepEqual(page1Repeat.data.batch_game_ids,ids.slice(0,2),'read before checkpoint must return same queue head');
  assert.equal((await call('/research?offset=2')).status,422,'pagination cannot bypass checkpoint gate');
  assert.equal((await call('/research',{contexts:ids.slice(0,3).map(context)})).status,422,'more than two contexts rejected');
  assert.equal((await call('/research',{contexts:[context(ids[2])]})).status,422,'cannot skip queue head');

  const first=context(ids[0]); assert.equal((await call('/research',{contexts:[first]})).status,200);
  run=new NcaafFreezeRun(state,{}); // object eviction/restart must retain progress
  assert.deepEqual((await call('')).data.completed_game_ids,[ids[0]]);
  const resumedPage=await call('/research');
  assert.deepEqual(resumedPage.data.batch_game_ids,[ids[1],ids[2]],'resume continues from first pending IDs');

  for(let i=1;i<ids.length;i+=2) assert.equal((await call('/research',{contexts:ids.slice(i,i+2).map(context)})).status,200);
  assert.equal((await call('')).data.pending_game_ids.length,0);
  assert.equal((await call('/research')).data.games.length,0,'empty queue once all checkpoints persisted');

  r=await call('/compute',{}); assert.equal(r.status,200,JSON.stringify(r.data));
  const original=structuredClone(r.data);
  assert.equal(r.data.p_model_status,'FROZEN'); assert.ok(JSON.stringify(r.data).length<90000);
  assert.deepEqual((await call('/compute',{})).data,original);
  assert.equal((await call('/research',{contexts:[first]})).status,422);
  assert.equal(calls.length,3,'Compute and post-freeze reads have no network calls');
  const games=[];for(const id of ids) games.push((await call('/games/'+id)).data.game);
  const {grid_retrieval,...snapshot}=original;snapshot.games=games;
  const result=execFileSync('python',['-c',`import sys,json,copy\nsys.path.insert(0,'ncaaf_totals_v1/model')\nfrom integrate_market import integrate\nfrom freeze_receipt import validate_receipt\nf=json.load(sys.stdin);validate_receipt(f)\nb={'service':'NCAAF_TOTALS_MARKET_GATEWAY','sport_key':'americanfootball_ncaaf','region':'au','market_group':'ncaaf-totals','market_key':'totals','board_revision':'a'*16,'retrieved_at':f['frozen_at'],'games':[]}\ng=f['games'][0]; b['games']=[{'event_id':'test','home_team':g['home_team'],'away_team':g['away_team'],'commence_time':g['commence_time'],'bookmakers':[{'key':'synthetic','last_update':f['frozen_at'],'totals':[{'name':'Over','point':50.0,'price':2.0}]}]}]\nbefore=copy.deepcopy(f);r=integrate(f,b);assert f==before;assert r['matched_selection_count']==1\nb['retrieved_at']='2020-01-01T00:00:00Z'\ntry: integrate(f,b);raise AssertionError('accepted prefreeze board')\nexcept ValueError: pass\nf['games'][0]['confidence']='A'\ntry: validate_receipt(f);raise AssertionError('accepted mutation')\nexcept ValueError: pass\nprint('PERSISTED_JS_TO_PYTHON_MARKET_CONTRACT_PASS')`],{cwd:new URL('../../',import.meta.url),input:JSON.stringify(snapshot)});
  console.log(result.toString().trim());
 } finally {globalThis.fetch=realFetch;Date.now=realNow;}
});
