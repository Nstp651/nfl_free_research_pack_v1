/** Pure state-machine core for the persistent NBA ET league-date slate run. */
import { nextResearchBatch, validateCheckpointOrder, researchStatus } from './slate_queue.js';
import { validateResearchCheckpoint, requestedHeads, marketKeyHits } from './research_contract.js';
import { computeSlateFreeze } from './freeze_core.js';
import { sha256Json } from './runtime_score.js';
const need=(ok,msg)=>{if(!ok) throw new Error(msg);};
const HASH64=/^[0-9a-f]{64}$/;
const clone=v=>structuredClone(v);

export function createSlateRun({runId,slateDateEt,runMode,eligibleGameIds,sourceCommit,qbaseHeads,createdAt}){
  need(String(runId||'').trim(),'run_id required');need(/^\d{4}-\d{2}-\d{2}$/.test(String(slateDateEt||'')),'slate_date_et invalid');const heads=requestedHeads(runMode);
  need(Array.isArray(eligibleGameIds)&&eligibleGameIds.length>0,'eligible_game_ids required');const ids=eligibleGameIds.map(String);need(new Set(ids).size===ids.length,'duplicate eligible game');need(ids.every(x=>/^\d{10}$/.test(x)),'eligible game id invalid');
  need(/^[0-9a-f]{7,40}$/.test(String(sourceCommit||'')),'source_commit invalid');need(qbaseHeads&&typeof qbaseHeads==='object','qbase heads required');
  for(const h of heads){const x=qbaseHeads[h];need(x&&String(x.model_version||''),`${h} qbase model_version required`);need(HASH64.test(String(x.promotion_receipt_sha256||'')),`${h} promotion receipt invalid`);need(HASH64.test(String(x.artifact_sha256||'')),`${h} artifact sha invalid`);}
  const state={schema_version:'nba_slate_run_state_v1',market_data:false,run_id:String(runId),slate_date_et:String(slateDateEt),run_mode:String(runMode),source_commit:String(sourceCommit),eligible_game_ids:ids,qbase_heads:clone(qbaseHeads),created_at:createdAt||new Date().toISOString(),status:'RESEARCH_IN_PROGRESS',completed_game_ids:[],research_checkpoints:{},freeze:null,invalidations:[]};
  need(marketKeyHits(state).length===0,'run initialization market leakage');return state;
}

export function getResearchBatch(state,batchSize=2){need(state&&['RESEARCH_IN_PROGRESS','RESEARCH_COMPLETE'].includes(state.status),'run is not research-active');return nextResearchBatch(state.eligible_game_ids,state.completed_game_ids,batchSize);}

export async function checkpointResearch(state,checkpoints,nowMs=Date.now()){
  need(state.status==='RESEARCH_IN_PROGRESS','research checkpoint not allowed in current state');need(Array.isArray(checkpoints)&&checkpoints.length>=1&&checkpoints.length<=2,'checkpoint must contain 1-2 games');const ids=checkpoints.map(x=>String(x.game_id));validateCheckpointOrder(state.eligible_game_ids,state.completed_game_ids,ids);
  const next=clone(state);
  for(const payload of checkpoints){validateResearchCheckpoint(payload,nowMs);need(payload.slate_date_et===state.slate_date_et,'checkpoint slate date mismatch');need(payload.run_mode===state.run_mode,'checkpoint run mode mismatch');need(!next.research_checkpoints[payload.game_id],'duplicate persisted checkpoint');const receipt=await sha256Json(payload);next.research_checkpoints[payload.game_id]={payload:clone(payload),research_receipt_sha256:receipt,checkpointed_at:new Date(nowMs).toISOString()};next.completed_game_ids.push(String(payload.game_id));}
  next.status=researchStatus(next.eligible_game_ids,next.completed_game_ids);return next;
}

export async function freezeSlateRun(state,{qbaseArtifacts,priorsByGame,frozenAt}){
  need(state.status==='RESEARCH_COMPLETE','whole slate cannot freeze before RESEARCH_COMPLETE');need(state.freeze===null,'freeze is immutable once created');const researchByGame={};for(const id of state.eligible_game_ids){const c=state.research_checkpoints[id];need(c?.payload,`persisted research checkpoint missing ${id}`);researchByGame[id]=c.payload;}
  const freeze=await computeSlateFreeze({slateDateEt:state.slate_date_et,runMode:state.run_mode,eligibleGameIds:state.eligible_game_ids,researchByGame,qbaseArtifacts,priorsByGame,frozenAt});
  for(const head of requestedHeads(state.run_mode)){need(freeze.qbase_heads[head].artifact_sha256===state.qbase_heads[head].artifact_sha256,`${head} qbase artifact changed after run initialization`);need(freeze.qbase_heads[head].promotion_receipt_sha256===state.qbase_heads[head].promotion_receipt_sha256,`${head} promotion receipt changed after run initialization`);}
  const next=clone(state);next.freeze=freeze;next.status='FROZEN';return next;
}

export function invalidateFrozenScope(state,{gameIds,reason,detectedAt}){
  need(['FROZEN','FROZEN_BUT_INVALIDATED'].includes(state.status),'only frozen runs can be invalidated');need(state.freeze&&HASH64.test(String(state.freeze.freeze_receipt_sha256||'')),'freeze receipt missing');need(Array.isArray(gameIds)&&gameIds.length>0,'invalidation game_ids required');const valid=new Set(state.eligible_game_ids);const ids=[...new Set(gameIds.map(String))];for(const id of ids)need(valid.has(id),`cannot invalidate non-slate game ${id}`);need(String(reason||'').trim(),'invalidation reason required');
  const next=clone(state);next.invalidations.push({game_ids:ids,reason:String(reason),detected_at:detectedAt||new Date().toISOString(),freeze_receipt_sha256:state.freeze.freeze_receipt_sha256});next.status='FROZEN_BUT_INVALIDATED';return next;
}

export async function marketAccessGrant(state){
  need(['FROZEN','FROZEN_BUT_INVALIDATED'].includes(state.status),'P_MODEL_STATUS must be frozen before market access');need(state.freeze&&HASH64.test(String(state.freeze.freeze_receipt_sha256||'')),'freeze receipt invalid');const excluded=[...new Set(state.invalidations.flatMap(x=>x.game_ids))];const allowed=state.eligible_game_ids.filter(id=>!excluded.includes(id));need(allowed.length>0,'all frozen games invalidated');const grant={schema_version:'nba_market_access_grant_v1',run_id:state.run_id,slate_date_et:state.slate_date_et,run_mode:state.run_mode,frozen_at:state.freeze.frozen_at,freeze_receipt_sha256:state.freeze.freeze_receipt_sha256,allowed_game_ids:allowed,invalidated_game_ids:excluded,qbase_heads:clone(state.qbase_heads)};grant.market_access_grant_sha256=await sha256Json(grant);return grant;
}
