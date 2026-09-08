import {assertMarketBlind,buildFrozenFixture,requireThat,sha256Json,validateResearchContext} from './freeze_core.js';
import {DEPLOY_SOURCE_COMMIT} from './source_commit.generated.js';

const HASH40=/^[0-9a-f]{40}$/;
const VALID_RUN_MODES=new Set(['ALL','SHOOTING_ONLY','SAVES_ONLY']);

export function response(body,status=200,headers={}){return new Response(JSON.stringify(body),{status,headers:{'content-type':'application/json; charset=utf-8','cache-control':'no-store',...headers}});}
async function bodyObject(request){const value=await request.json();requireThat(value&&typeof value==='object'&&!Array.isArray(value),'JSON object body required');return value;}
function onlyKeys(value,allowed,label){const extra=Object.keys(value).filter(k=>!allowed.has(k));requireThat(extra.length===0,`${label} unexpected fields: ${extra.join(', ')}`);}
function sourceCommit(env){const override=String(env?.SOURCE_COMMIT_OVERRIDE||'').trim().toLowerCase(),built=String(DEPLOY_SOURCE_COMMIT||'').trim().toLowerCase(),value=override||built;requireThat(HASH40.test(value)&&!/^[0]+$/.test(value),'exact deployment source commit unavailable');return value;}
function cleanRevision(value,label){const x=String(value||'').trim();requireThat(x.length>=1&&x.length<=200,`${label} required`);return x;}

export async function createRun(request,env){
  requireThat(env?.MATCH_RUNS,'MATCH_RUNS Durable Object binding missing');const input=await bodyObject(request);onlyKeys(input,new Set(['fixture_id','run_mode','pack_revision','qbase_revision','advanced_revision']), 'create run');
  const fixtureId=String(input.fixture_id||'').trim(),runMode=String(input.run_mode||'').toUpperCase();requireThat(fixtureId,'fixture_id required');requireThat(VALID_RUN_MODES.has(runMode),'run_mode must be ALL, SHOOTING_ONLY or SAVES_ONLY');
  const id=env.MATCH_RUNS.newUniqueId(),runId=id.toString(),lock={run_id:runId,fixture_id:fixtureId,run_mode:runMode,source_commit:sourceCommit(env),pack_revision:cleanRevision(input.pack_revision,'pack_revision'),qbase_revision:cleanRevision(input.qbase_revision,'qbase_revision'),advanced_revision:cleanRevision(input.advanced_revision,'advanced_revision'),created_at:new Date().toISOString()};
  const stub=env.MATCH_RUNS.get(id),init=await stub.fetch(new Request('https://run.local/init',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({lock})}));const payload=await init.json();return response(payload,init.status);
}

export async function routeRuns(request,env){
  const url=new URL(request.url),match=url.pathname.match(/^\/v1\/runs\/([0-9a-f]{64})(\/.*)?$/);if(!match)return null;requireThat(env?.MATCH_RUNS,'MATCH_RUNS Durable Object binding missing');let id;try{id=env.MATCH_RUNS.idFromString(match[1]);}catch{throw new Error('Invalid run_id');}const stub=env.MATCH_RUNS.get(id),tail=match[2]||'/';const forwarded=new Request(`https://run.local${tail}${url.search}`,request);return stub.fetch(forwarded);
}

async function canonicalizeFreeze(raw,expectedResearchHash){
  requireThat(raw&&typeof raw==='object','raw freeze artifact missing');requireThat(raw.schema_version==='aleague_player_volume_freeze_v1','raw freeze schema mismatch');requireThat(raw.market_data===false,'raw freeze market boundary failure');requireThat(raw.research_context_sha256===expectedResearchHash,'research hash changed before freeze');
  const frozen={...raw,model_version:'ALEAGUE_PLAYER_VOLUME_V1_0.3.0',research_hash:expectedResearchHash};delete frozen.research_context_sha256;delete frozen.freeze_hash;assertMarketBlind(frozen);frozen.freeze_receipt_sha256=await sha256Json(frozen);return frozen;
}

export class AleaguePlayerVolumeRun {
  constructor(state,env){this.state=state;this.storage=state.storage;this.env=env;}
  async fetch(request){try{return await this.handle(request);}catch(error){return response({market_data:false,error:String(error?.message||error)},422);}}
  async handle(request){
    const url=new URL(request.url),path=url.pathname;
    if(request.method==='POST'&&path==='/init'){
      const existing=await this.storage.get('meta');requireThat(!existing,'Run already initialized');const input=await bodyObject(request);onlyKeys(input,new Set(['lock']),'init');const lock=input.lock;requireThat(lock&&typeof lock==='object','lock required');requireThat(HASH40.test(String(lock.source_commit||'')),'source_commit invalid');requireThat(VALID_RUN_MODES.has(String(lock.run_mode||'')),'run_mode invalid');requireThat(String(lock.run_id||'').length===64,'run_id invalid');const meta={schema_version:'aleague_player_volume_run_v1',market_data:false,status:'NEW',research_revision:0,lock};assertMarketBlind(meta);await this.storage.put('meta',meta);return response(meta,201);
    }
    const meta=await this.storage.get('meta');requireThat(meta,'Unknown run');
    if(request.method==='GET'&&path==='/')return response(meta);
    if(request.method==='GET'&&path==='/research'){
      const research=await this.storage.get('research');requireThat(research,'Research context not checkpointed');return response({market_data:false,status:meta.status,lock:meta.lock,research_hash:meta.research_hash,research});
    }
    if(request.method==='POST'&&path==='/research'){
      requireThat(meta.status!=='FROZEN','Run already frozen');const input=await bodyObject(request);onlyKeys(input,new Set(['research']),'research checkpoint');const research=input.research;validateResearchContext(research);requireThat(research.fixture_id===meta.lock.fixture_id,'research fixture_id does not match run lock');requireThat(String(research.run_mode).toUpperCase()===meta.lock.run_mode,'research run_mode does not match run lock');requireThat(String(research.pack_revision)===meta.lock.pack_revision,'research pack_revision does not match run lock');const hash=await sha256Json(research),next={...meta,status:'RESEARCH_COMPLETE',research_revision:Number(meta.research_revision||0)+1,research_hash:hash,research_checkpointed_at:new Date().toISOString()};await this.storage.put({research,meta:next});return response({market_data:false,status:next.status,lock:next.lock,research_revision:next.research_revision,research_hash:hash});
    }
    if(request.method==='POST'&&path==='/freeze'){
      requireThat(meta.status==='RESEARCH_COMPLETE','Research must be complete before freeze');requireThat(!(await this.storage.get('frozen')),'Frozen artifact already exists');const research=await this.storage.get('research');requireThat(research,'Research context missing');const input=await bodyObject(request);onlyKeys(input,new Set(['team_models','outfield_models','goalkeeper_models']),'freeze');requireThat(Array.isArray(input.team_models),'team_models required');requireThat(Array.isArray(input.outfield_models),'outfield_models required');requireThat(Array.isArray(input.goalkeeper_models),'goalkeeper_models required');assertMarketBlind(input);const raw=await buildFrozenFixture(research,input.team_models,input.outfield_models,input.goalkeeper_models,{frozenAt:new Date().toISOString()}),frozen=await canonicalizeFreeze(raw,meta.research_hash);const next={...meta,status:'FROZEN',frozen_at:frozen.frozen_at,freeze_receipt_sha256:frozen.freeze_receipt_sha256};await this.storage.put({frozen,meta:next});return response({market_data:false,status:'FROZEN',lock:next.lock,freeze_receipt_sha256:frozen.freeze_receipt_sha256,frozen_at:frozen.frozen_at,frozen});
    }
    if(request.method==='GET'&&path==='/frozen'){
      requireThat(meta.status==='FROZEN','Run is not frozen');const frozen=await this.storage.get('frozen');requireThat(frozen,'Frozen artifact missing');return response({market_data:false,status:'FROZEN',lock:meta.lock,freeze_receipt_sha256:meta.freeze_receipt_sha256,frozen});
    }
    return response({market_data:false,error:'Not found'},404);
  }
}
