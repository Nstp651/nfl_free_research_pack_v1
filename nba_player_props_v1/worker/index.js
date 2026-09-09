import { SOURCE_COMMIT } from './source_commit.generated.js';
import { listFixturesForEtDate } from './fixture_source.js';
import { loadRuntimeAssets } from './runtime_assets.js';
import { buildResearchSeed } from './research_seed.js';
import { buildPriorSnapshotsForResearch } from './runtime_prior.js';
import { createSlateRun, getResearchBatch, checkpointResearch, freezeSlateRun, invalidateFrozenScope, marketAccessGrant } from './slate_run_core.js';
import { sha256Json } from './runtime_score.js';

const need=(ok,msg)=>{if(!ok) throw new Error(msg);};
const START_KEY=/^[A-Za-z0-9._:-]{8,128}$/;
const cors={'access-control-allow-origin':'*','access-control-allow-methods':'GET,POST,OPTIONS','access-control-allow-headers':'content-type,authorization'};
export function response(value,status=200){const h=new Headers({'content-type':'application/json'});for(const[k,v]of Object.entries(cors))h.set(k,v);return new Response(JSON.stringify(value),{status,headers:h});}
function exactKeys(body,allowed,label){need(body&&typeof body==='object'&&!Array.isArray(body),`${label} body required`);for(const k of Object.keys(body))need(allowed.includes(k),`${label} unsupported field ${k}`);}
async function jsonBody(request){const text=await request.text();return text?JSON.parse(text):{};}
function authorize(request,env){if(!env.ACTION_TOKEN)return;need(request.headers.get('authorization')===`Bearer ${env.ACTION_TOKEN}`,'Unauthorized');}
function runStub(env,runId){need(env.SLATE_RUNS,'SLATE_RUNS Durable Object binding missing');need(String(runId||'').trim(),'run_id required');return env.SLATE_RUNS.get(env.SLATE_RUNS.idFromName(String(runId)));}
async function qbaseHeadLock(assets,runMode){const heads=runMode==='BOTH'?['assists','rebounds']:(runMode==='ASSISTS_ONLY'?['assists']:(runMode==='REBOUNDS_ONLY'?['rebounds']:(()=>{throw new Error('invalid run_mode')})()));const out={};for(const head of heads){const a=assets.qbase_artifacts[head];out[head]={model_version:a.model_version,promotion_receipt_sha256:a.promotion_receipt_sha256,artifact_sha256:await sha256Json(a)};}return out;}
function checkpointReceipts(state){return Object.fromEntries(state.completed_game_ids.map(id=>[id,state.research_checkpoints[id]?.research_receipt_sha256]).filter(([,v])=>v));}
function statusSummary(state,extra={}){return {market_data:false,run_id:state.run_id,start_request_id:state.start_request_id,slate_date_et:state.slate_date_et,run_mode:state.run_mode,status:state.status,source_commit:state.source_commit,qbase_heads:state.qbase_heads,eligible_game_ids:state.eligible_game_ids,completed_game_ids:state.completed_game_ids,research_receipts:checkpointReceipts(state),pending_count:state.eligible_game_ids.length-state.completed_game_ids.length,frozen_at:state.freeze?.frozen_at||null,freeze_receipt_sha256:state.freeze?.freeze_receipt_sha256||null,invalidations:state.invalidations,...extra};}
function initSummary(state,extra={}){return {market_data:false,run_id:state.run_id,start_request_id:state.start_request_id,slate_date_et:state.slate_date_et,run_mode:state.run_mode,status:state.status,eligible_game_ids:state.eligible_game_ids,qbase_heads:state.qbase_heads,source_commit:state.source_commit,...extra};}
function freezeSummary(state){const freeze=state.freeze;need(freeze,'P_model not frozen');return {market_data:false,run_id:state.run_id,status:state.status,frozen_at:freeze.frozen_at,freeze_receipt_sha256:freeze.freeze_receipt_sha256,qbase_heads:state.qbase_heads,game_count:freeze.games.length,player_count:freeze.games.reduce((n,g)=>n+g.players.length,0),exclusion_count:freeze.games.reduce((n,g)=>n+g.exclusions.length,0)};}
export async function deriveSlateRunId({requestId,slateDateEt,runMode}){need(START_KEY.test(String(requestId||'')),'request_id invalid');const hash=await sha256Json({schema_version:'nba_start_request_v1',request_id:String(requestId),slate_date_et:String(slateDateEt),run_mode:String(runMode).toUpperCase()});return `nba-${hash.slice(0,40)}`;}

export class NbaSlateRun {
  constructor(state,env){this.storage=state.storage;this.env=env;}
  async fetch(request){
    try{
      const url=new URL(request.url),path=url.pathname;
      if(request.method==='POST'&&path==='/init'){
        const body=await jsonBody(request);exactKeys(body,['state','fixture_source'],'init');need(body.state?.schema_version==='nba_slate_run_state_v1','invalid run state');const existing=await this.storage.get('state');if(existing){need(existing.start_request_id===body.state.start_request_id,'start request id collision');need(existing.slate_date_et===body.state.slate_date_et&&existing.run_mode===body.state.run_mode,'start request payload changed');return response(initSummary(existing,{idempotent_replay:true}));}await this.storage.put('state',body.state);await this.storage.put('fixture_source',body.fixture_source||null);return response(initSummary(body.state,{idempotent_replay:false}));
      }
      let state=await this.storage.get('state');need(state,'Unknown run');
      if(request.method==='GET'&&path==='/status')return response(statusSummary(state));
      if(request.method==='GET'&&path==='/research/next'){
        const batch=getResearchBatch(state,2),ids=batch.batch_game_ids,assets=await loadRuntimeAssets(state.source_commit);const seeds=[];for(const id of ids)seeds.push(await buildResearchSeed(state.fixture_locks[id],assets));return response({market_data:false,run_id:state.run_id,status:state.status,batch_game_ids:ids,pending_count:batch.pending_game_ids.length,next_batch_after_checkpoint:batch.next_batch_after_checkpoint,research_seeds:seeds});
      }
      if(request.method==='POST'&&path==='/research/checkpoint'){
        const body=await jsonBody(request);exactKeys(body,['checkpoints'],'research checkpoint');state=await checkpointResearch(state,body.checkpoints,Date.now());await this.storage.put('state',state);return response(statusSummary(state));
      }
      if(request.method==='POST'&&path==='/freeze'){
        const body=await jsonBody(request);exactKeys(body,[],'freeze');
        if(state.freeze&&['FROZEN','FROZEN_BUT_INVALIDATED'].includes(state.status))return response(freezeSummary(state));
        need(state.status==='RESEARCH_COMPLETE','whole slate cannot freeze before RESEARCH_COMPLETE');const assets=await loadRuntimeAssets(state.source_commit),priorsByGame={};for(const id of state.eligible_game_ids){const research=state.research_checkpoints[id]?.payload;need(research,`research missing ${id}`);priorsByGame[id]=await buildPriorSnapshotsForResearch(assets.prior_pack,research,assets.qbase_artifacts);}state=await freezeSlateRun(state,{qbaseArtifacts:assets.qbase_artifacts,priorsByGame,frozenAt:new Date().toISOString()});await this.storage.put('state',state);return response(freezeSummary(state));
      }
      if(request.method==='GET'&&path==='/freeze'){need(state.freeze,'P_model not frozen');return response({market_data:false,run_id:state.run_id,status:state.status,freeze:state.freeze,invalidations:state.invalidations});}
      if(request.method==='POST'&&path==='/invalidate'){
        const body=await jsonBody(request);exactKeys(body,['game_ids','reason'],'invalidate');state=invalidateFrozenScope(state,{gameIds:body.game_ids,reason:body.reason,detectedAt:new Date().toISOString()});await this.storage.put('state',state);return response({market_data:false,run_id:state.run_id,status:state.status,freeze_receipt_sha256:state.freeze.freeze_receipt_sha256,invalidations:state.invalidations});
      }
      if(request.method==='GET'&&path==='/market-access')return response(await marketAccessGrant(state));
      return response({market_data:false,error:'Not found'},404);
    }catch(e){return response({market_data:false,error:e.message},e.message==='Unauthorized'?401:422);}
  }
}

async function routeRun(request,env,url){const match=url.pathname.match(/^\/v1\/runs\/([^/]+)(\/.*)?$/);if(!match)return null;const runId=decodeURIComponent(match[1]),tail=match[2]||'';const allowed=new Set(['','/research/next','/research/checkpoint','/freeze','/invalidate','/market-access']);need(allowed.has(tail),`Unknown run route ${tail}`);const path=tail||'/status',stub=runStub(env,runId);return stub.fetch(new Request(`https://nba-run${path}`,{method:request.method,headers:request.headers,body:['GET','HEAD'].includes(request.method)?undefined:request.body,duplex:'half'}));}

export default {
  async fetch(request,env){
    try{
      if(request.method==='OPTIONS')return new Response(null,{status:204,headers:cors});authorize(request,env);const url=new URL(request.url);const routed=await routeRun(request,env,url);if(routed)return routed;
      if(request.method==='GET'&&url.pathname==='/health')return response({ok:true,service:'nba-player-props-research-freeze',version:'1.0.0',market_data:false,source_commit:SOURCE_COMMIT,source_commit_ready:/^[0-9a-f]{40}$/.test(SOURCE_COMMIT),durable_object_binding:Boolean(env.SLATE_RUNS)});
      if(request.method==='GET'&&url.pathname==='/v1/fixtures'){const date=url.searchParams.get('date');return response(await listFixturesForEtDate(date));}
      if(request.method==='POST'&&url.pathname==='/v1/runs'){
        const body=await jsonBody(request);exactKeys(body,['request_id','slate_date_et','run_mode'],'new run');const requestId=String(body.request_id||''),runMode=String(body.run_mode||'BOTH').toUpperCase(),slateDateEt=String(body.slate_date_et||'');need(START_KEY.test(requestId),'request_id invalid');need(/^[0-9a-f]{40}$/.test(SOURCE_COMMIT),'deployment source commit not built');const runId=await deriveSlateRunId({requestId,slateDateEt,runMode}),stub=runStub(env,runId);
        const existing=await stub.fetch(new Request('https://nba-run/status'));if(existing.ok){const value=await existing.json();need(value.start_request_id===requestId&&value.slate_date_et===slateDateEt&&value.run_mode===runMode,'request_id reused with different start payload');return response({...value,idempotent_replay:true});}const err=await existing.json();need(existing.status===422&&err.error==='Unknown run',`unable to resolve start request: ${err.error||existing.status}`);
        const fixtureResult=await listFixturesForEtDate(slateDateEt);need(fixtureResult.fixtures.length>0,'no eligible future NBA fixtures for ET league date');const assets=await loadRuntimeAssets(SOURCE_COMMIT),qbaseHeads=await qbaseHeadLock(assets,runMode),ids=fixtureResult.fixtures.map(x=>x.game_id);const state=createSlateRun({runId,startRequestId:requestId,slateDateEt,runMode,eligibleGameIds:ids,fixtures:fixtureResult.fixtures,sourceCommit:SOURCE_COMMIT,qbaseHeads,createdAt:new Date().toISOString()});return stub.fetch(new Request('https://nba-run/init',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({state,fixture_source:fixtureResult.source})}));
      }
      return response({market_data:false,error:'Not found'},404);
    }catch(e){return response({market_data:false,error:e.message},e.message==='Unauthorized'?401:422);}
  }
};
