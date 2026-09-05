/** Persistent, resumable pre-market run. Only hard-coded GitHub research URLs
 * can be fetched; no market Worker, sportsbook credentials, or client URLs. */
import {requireThat,exactKeys,verifySources,validateContext,computeFreeze} from './freeze_core.js';
const ROOT='https://raw.githubusercontent.com/Nstp651/nfl_free_research_pack_v1/';
const API='https://api.github.com/repos/Nstp651/nfl_free_research_pack_v1/commits/main';
export const response=(x,status=200)=>new Response(JSON.stringify(x),{status,headers:{'content-type':'application/json','cache-control':'no-store'}});
async function readSource(url) {
  requireThat(url===API || /^https:\/\/raw\.githubusercontent\.com\/Nstp651\/nfl_free_research_pack_v1\/[a-f0-9]{40}\/ncaaf_totals_v1\/(data\/slates|model\/slates)\/\d{4}\/\d{4}_\d{2}\.json$/.test(url),'Source URL not allowed');
  const res=await fetch(url,{headers:{'user-agent':'ncaaf-freeze/1.1.3'},signal:AbortSignal.timeout(12000)});
  requireThat(res.ok,'Research source unavailable: '+res.status);
  const raw=await res.text(); requireThat(raw.length<8000000,'Source too large'); return JSON.parse(raw);
}
export async function loadSources(input) {
  exactKeys(input,['season','week','window_start','window_end','timing_mode']);
  requireThat(Number.isInteger(input.season) && input.season>=2000 && input.season<=2100 && Number.isInteger(input.week) && input.week>=0 && input.week<=30,'Invalid season/week');
  requireThat(['MATCHDAY','NIGHT-BEFORE'].includes(input.timing_mode),'Invalid timing mode');
  const start=Date.parse(input.window_start),end=Date.parse(input.window_end);
  requireThat(/(Z|[+-]\d\d:\d\d)$/.test(input.window_start) && /(Z|[+-]\d\d:\d\d)$/.test(input.window_end) && Number.isFinite(start) && Number.isFinite(end) && end>start && end-start<=7*86400000,'Invalid explicit timezone window');
  const head=await readSource(API); requireThat(/^[a-f0-9]{40}$/.test(head.sha),'Invalid source commit');
  const slate_id=`${input.season}_${String(input.week).padStart(2,'0')}`;
  const base=ROOT+head.sha+'/ncaaf_totals_v1/';
  const [pack,qbase]=await Promise.all([readSource(`${base}data/slates/${input.season}/${slate_id}.json`),readSource(`${base}model/slates/${input.season}/${slate_id}.json`)]);
  return {pack,qbase,source_commit:head.sha,slate_id};
}
export function compact(snapshot) {
  const {games,...receipt}=snapshot;
  return {...receipt,games:games.map(({probability_grid,context,...g})=>g),grid_retrieval:'GET /v1/freeze-runs/{run_id}/games/{game_id}; exact persisted grid only'};
}
export class NcaafFreezeRun {
  constructor(state,env) { this.state=state; this.storage=state.storage; }
  async fetch(request) {
    // Serialize checkpoint/compute/read transitions even across awaited hashes.
    return this.state.blockConcurrencyWhile(async()=>{
      try { return await this.handle(request); }
      catch(e) { const m=await this.storage.get('meta'); return response({market_data:false,p_model_status:m?.status==='FROZEN'?'FROZEN':'NOT FROZEN',error:e.message},422); }
    });
  }
  async handle(request) {
    const url=new URL(request.url), action=url.pathname.split('/').slice(4);
    let meta=await this.storage.get('meta');
    if(request.method==='POST' && action.length===0) {
      requireThat(!meta,'Run already initialized');
      const input=await request.json();
      const {pack,qbase,source_commit,slate_id}=await loadSources(input);
      const now=Date.now(),checked=Date.parse(pack.last_checked_at_utc || pack.generated_at_utc);
      requireThat(Number.isFinite(checked) && checked<=now+300000 && now-checked<=36*3600000,'Research pack stale/invalid');
      const eligible_game_ids=pack.games.filter(g=>g.fixture.fbs_game===true && g.fixture.completed===false && Date.parse(g.fixture.start_utc)>now && Date.parse(g.fixture.start_utc)>=Date.parse(input.window_start) && Date.parse(g.fixture.start_utc)<Date.parse(input.window_end)).map(g=>g.game_id).sort();
      requireThat(eligible_game_ids.length>0,'No eligible games');
      const lock={...input,source_commit,slate_id,pack_revision:pack.pack_revision,qbase_revision:qbase.qbase_revision,eligibility_at:new Date(now).toISOString(),eligible_game_ids};
      const verified=await verifySources(pack,qbase,lock);
      const {games:rg,...rp}=pack,{games:qg,...qp}=qbase;
      // Individual records stay below Durable Object per-value limits.
      await this.storage.transaction(async tx=>{
        await tx.put('pack',rp); await tx.put('qbase',qp);
        for(const g of rg) await tx.put('r:'+g.game_id,g);
        for(const g of qg) await tx.put('q:'+g.game_id,g);
        await tx.put('meta',{lock,cutoff_status:verified.cutoff,all_ids:rg.map(g=>g.game_id),created_at:now,status:'RESEARCH_IN_PROGRESS'});
      });
      meta=await this.storage.get('meta');
    }
    requireThat(meta,'Unknown run');
    if(request.method==='GET' && action[0]==='games' && action.length===2) {
      requireThat(meta.status==='FROZEN','Run not frozen');
      const g=await this.storage.get('f:'+action[1]); requireThat(g,'Game not in frozen slate');
      return response({market_data:false,freeze_receipt_sha256:meta.receipt.freeze_receipt_sha256,frozen_at:meta.receipt.frozen_at,game:g});
    }
    if(request.method==='GET' && action[0]==='research' && action.length===1) {
      const offset=Number(url.searchParams.get('offset') || 0);
      requireThat(Number.isInteger(offset) && offset>=0 && offset<meta.lock.eligible_game_ids.length,'Invalid offset');
      const ids=meta.lock.eligible_game_ids.slice(offset,offset+5),games=[];
      for(const id of ids) { const q=await this.storage.get('q:'+id); const {probability_grid,...anchor}=q; games.push({research:await this.storage.get('r:'+id),qbase:anchor,checkpoint:await this.storage.get('c:'+id) || null}); }
      return response({market_data:false,lock:meta.lock,games,next_offset:offset+5<meta.lock.eligible_game_ids.length?offset+5:null});
    }
    if(request.method==='POST' && action[0]==='research' && action.length===1) {
      requireThat(meta.status!=='FROZEN','Frozen run is immutable');
      const body=await request.json(); exactKeys(body,['contexts']);
      requireThat(Array.isArray(body.contexts) && body.contexts.length>=1 && body.contexts.length<=5,'Submit 1–5 complete game receipts');
      const seen=new Set();
      for(const c of body.contexts) {
        requireThat(meta.lock.eligible_game_ids.includes(c.game_id) && !seen.has(c.game_id),'Unknown/duplicate context game'); seen.add(c.game_id);
        const r=await this.storage.get('r:'+c.game_id); validateContext(c,r.fixture,Date.now());
        requireThat(JSON.stringify(c).length<60000,'Research receipt too large');
      }
      await this.storage.transaction(async tx=>{ for(const c of body.contexts) await tx.put('c:'+c.game_id,c); });
    }
    if(request.method==='POST' && action[0]==='compute' && action.length===1) {
      exactKeys(await request.json(),[]);
      if(meta.status==='FROZEN') return response(meta.receipt);
      const now=Date.now(); requireThat(now-meta.created_at<=36*3600000,'Run expired; new research run required');
      const source=await this.storage.get('pack');
      requireThat(now-Date.parse(source.last_checked_at_utc || source.generated_at_utc)<=36*3600000,'Research source expired; new run required');
      const rg=[],qg=[],contexts=[];
      for(const id of meta.all_ids) { rg.push(await this.storage.get('r:'+id)); qg.push(await this.storage.get('q:'+id)); }
      for(const id of meta.lock.eligible_game_ids) { const c=await this.storage.get('c:'+id); requireThat(c,'Incomplete research: '+id); contexts.push(c); }
      const frozen=await computeFreeze({...await this.storage.get('pack'),games:rg},{...await this.storage.get('qbase'),games:qg},meta.lock,contexts,now);
      const receipt=compact(frozen);
      // Atomic publication: no game can be read as frozen until ALL have passed.
      await this.storage.transaction(async tx=>{
        for(const g of frozen.games) await tx.put('f:'+g.game_id,g);
        await tx.put('meta',{...meta,status:'FROZEN',receipt});
      });
      return response(receipt);
    }
    requireThat(action.length===0 || action[0]==='research','Unknown run operation');
    requireThat(['GET','POST'].includes(request.method),'Method not allowed');
    const completed=[]; for(const id of meta.lock.eligible_game_ids) if(await this.storage.get('c:'+id)) completed.push(id);
    return response({market_data:false,status:meta.status,lock:meta.lock,cutoff_status:meta.cutoff_status,completed_game_ids:completed,pending_game_ids:meta.lock.eligible_game_ids.filter(x=>!completed.includes(x)),freeze:meta.receipt || null});
  }
}
export async function routeFreeze(request,env) {
  const url=new URL(request.url);
  if(!url.pathname.startsWith('/v1/freeze-runs')) return null;
  if(!env.FREEZE_RUNS) return response({error:'Freeze storage binding unavailable',market_data:false},503);
  const match=url.pathname.match(/^\/v1\/freeze-runs(?:\/([a-f0-9]{64})(?:\/(research|compute|games)(?:\/([0-9]+))?)?)?$/);
  if(!match) return response({error:'Not found',market_data:false},404);
  if(!match[1] && request.method!=='POST') return response({error:'POST required',market_data:false},405);
  const id=match[1]?env.FREEZE_RUNS.idFromString(match[1]):env.FREEZE_RUNS.newUniqueId();
  if(!match[1]) url.pathname+='/'+id.toString();
  const raw=await request.text();
  if(raw.length>320000) return response({error:'Request too large',market_data:false},413);
  const res=await env.FREEZE_RUNS.get(id).fetch(new Request(url,{method:request.method,headers:request.headers,...(request.method==='GET'?{}:{body:raw})}));
  const data=await res.json();
  return response({run_id:id.toString(),...data},res.status);
}
