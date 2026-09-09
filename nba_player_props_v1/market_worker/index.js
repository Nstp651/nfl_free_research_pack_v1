import { fetchOddsApiSlate } from './odds_api_client.js';
import { createMarketRun, reconcileMarketGrant, marketRefreshReplay, applyApiSnapshot, applyManualSnapshot, rankCurrentMarket, marketStateSummary } from './market_run_core.js';

const need=(ok,msg)=>{if(!ok) throw new Error(msg);};
const cors={'access-control-allow-origin':'*','access-control-allow-methods':'GET,POST,OPTIONS','access-control-allow-headers':'content-type,authorization'};
function response(value,status=200){const h=new Headers({'content-type':'application/json'});for(const[k,v]of Object.entries(cors))h.set(k,v);return new Response(JSON.stringify(value),{status,headers:h});}
function authorize(request,env){if(!env.ACTION_TOKEN)return;need(request.headers.get('authorization')===`Bearer ${env.ACTION_TOKEN}`,'Unauthorized');}
async function body(request){const text=await request.text();return text?JSON.parse(text):{};}
function exactKeys(value,allowed,label){need(value&&typeof value==='object'&&!Array.isArray(value),`${label} body required`);for(const k of Object.keys(value))need(allowed.includes(k),`${label} unsupported field ${k}`);}
function runStub(env,runId){need(env.MARKET_RUNS,'MARKET_RUNS Durable Object binding missing');return env.MARKET_RUNS.get(env.MARKET_RUNS.idFromName(String(runId)));}
function researchHeaders(env){const h=new Headers({accept:'application/json'});if(env.RESEARCH_ACTION_TOKEN)h.set('authorization',`Bearer ${env.RESEARCH_ACTION_TOKEN}`);return h;}
function apiRefreshSummary(snapshot,replayed){return {refresh_request_id:snapshot.refresh_request_id,replayed,captured_at:snapshot.captured_at,quote_count:snapshot.quotes.length,issue_count:(snapshot.issues||[]).length,event_resolution:snapshot.event_resolution||{},quota:snapshot.quota||[]};}
function manualRefreshSummary(snapshot,replayed){return {refresh_request_id:snapshot.refresh_request_id,replayed,captured_at:snapshot.captured_at,snapshot_sha256:snapshot.snapshot_sha256,quote_count:snapshot.quotes.length,evidence_id:snapshot.evidence_id};}

async function researchJson(env,path){
  need(env.RESEARCH_SERVICE,'RESEARCH_SERVICE binding missing');const res=await env.RESEARCH_SERVICE.fetch(new Request(`https://nba-research${path}`,{headers:researchHeaders(env)}));const text=await res.text();let value;try{value=JSON.parse(text);}catch{throw new Error(`research service returned non-JSON ${res.status}`);}need(res.ok,`research service ${res.status}: ${value?.error||text.slice(0,160)}`);return value;
}
async function researchContext(env,runId){const grant=await researchJson(env,`/v1/runs/${encodeURIComponent(runId)}/market-access`);const frozen=await researchJson(env,`/v1/runs/${encodeURIComponent(runId)}/freeze`);need(frozen?.freeze,'research service freeze missing');return {grant,freeze:frozen.freeze,run_status:frozen.status,invalidations:frozen.invalidations||[]};}

export class NbaMarketRun {
  constructor(state,env){this.storage=state.storage;this.env=env;}
  async _context(runId){return researchContext(this.env,runId);}
  async _state(runId,context){let state=await this.storage.get('state');if(!state){state=await createMarketRun({runId,freeze:context.freeze,grant:context.grant});}else state=reconcileMarketGrant(state,context.freeze,context.grant);return state;}
  async fetch(request){
    try{
      const url=new URL(request.url),runId=url.searchParams.get('run_id');need(String(runId||'').trim(),'run_id required');const path=url.pathname,context=await this._context(runId);let state=await this._state(runId,context);
      if(request.method==='POST'&&path==='/refresh'){
        const b=await body(request);exactKeys(b,['regions','refresh_request_id'],'market refresh');const replay=marketRefreshReplay(state,'api',b.refresh_request_id);if(replay){await this.storage.put('state',state);return response({run_id:runId,layer:'3-4',freeze_receipt_sha256:context.freeze.freeze_receipt_sha256,refresh:apiRefreshSummary(replay.snapshot,true),rankings:rankCurrentMarket(state,context.freeze)});}
        const regions=String(b.regions||this.env.ODDS_API_REGIONS||'au');const snapshot=await fetchOddsApiSlate({apiKey:this.env.ODDS_API_KEY,freeze:context.freeze,grant:context.grant,regions,capturedAt:new Date().toISOString()});state=await applyApiSnapshot(state,snapshot,{refreshRequestId:b.refresh_request_id});await this.storage.put('state',state);const rankings=rankCurrentMarket(state,context.freeze);return response({run_id:runId,layer:'3-4',freeze_receipt_sha256:context.freeze.freeze_receipt_sha256,refresh:apiRefreshSummary(state.current_api_snapshot,false),rankings});
      }
      if(request.method==='POST'&&path==='/manual-quotes'){
        const b=await body(request);exactKeys(b,['refresh_request_id','source_type','captured_at','evidence_id','freeze_receipt_sha256','quotes'],'manual market refresh');const replay=marketRefreshReplay(state,'manual',b.refresh_request_id);if(replay){await this.storage.put('state',state);return response({run_id:runId,layer:'3-4',freeze_receipt_sha256:context.freeze.freeze_receipt_sha256,manual_snapshot:manualRefreshSummary(replay.snapshot,true),rankings:rankCurrentMarket(state,context.freeze)});}
        state=await applyManualSnapshot(state,context.freeze,b);await this.storage.put('state',state);return response({run_id:runId,layer:'3-4',freeze_receipt_sha256:context.freeze.freeze_receipt_sha256,manual_snapshot:manualRefreshSummary(state.current_manual_snapshot,false),rankings:rankCurrentMarket(state,context.freeze)});
      }
      if(request.method==='GET'&&path==='/rankings'){await this.storage.put('state',state);return response(rankCurrentMarket(state,context.freeze));}
      if(request.method==='GET'&&path==='/state'){await this.storage.put('state',state);return response({...marketStateSummary(state),research_run_status:context.run_status,invalidations:context.invalidations});}
      return response({error:'Not found'},404);
    }catch(e){return response({error:e.message},e.message==='Unauthorized'?401:422);}
  }
}

async function route(request,env,url){const m=url.pathname.match(/^\/v1\/runs\/([^/]+)\/(refresh|manual-quotes|rankings|state)$/);if(!m)return null;const runId=decodeURIComponent(m[1]),op=m[2];if((op==='refresh'||op==='manual-quotes')&&request.method!=='POST')return response({error:'Method not allowed'},405);if((op==='rankings'||op==='state')&&request.method!=='GET')return response({error:'Method not allowed'},405);const stub=runStub(env,runId);return stub.fetch(new Request(`https://nba-market/${op}?run_id=${encodeURIComponent(runId)}`,{method:request.method,headers:request.headers,body:['GET','HEAD'].includes(request.method)?undefined:request.body,duplex:'half'}));}

export default {
  async fetch(request,env){
    try{
      if(request.method==='OPTIONS')return new Response(null,{status:204,headers:cors});authorize(request,env);const url=new URL(request.url);if(request.method==='GET'&&url.pathname==='/health')return response({ok:true,service:'nba-player-props-market',version:'1.0.0',post_freeze_only:true,markets:['player_assists','player_assists_alternate','player_rebounds','player_rebounds_alternate'],default_regions:String(env.ODDS_API_REGIONS||'au'),research_service_binding:Boolean(env.RESEARCH_SERVICE),durable_object_binding:Boolean(env.MARKET_RUNS),odds_api_key_configured:Boolean(env.ODDS_API_KEY)});const routed=await route(request,env,url);if(routed)return routed;return response({error:'Not found'},404);
    }catch(e){return response({error:e.message},e.message==='Unauthorized'?401:422);}
  }
};
