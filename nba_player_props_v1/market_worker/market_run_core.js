/** Persistent post-freeze market state for NBA Assists + Rebounds V1. */
import { chooseBestExactPrices, evaluateExactMarket, rankPositiveEdges } from './market_core.js';
import { normalizeIdentity, validateGrantAgainstFreeze } from './odds_api_client.js';

const need=(ok,msg)=>{if(!ok) throw new Error(msg);};
const HASH64=/^[0-9a-f]{64}$/;
const REQUEST_ID=/^[A-Za-z0-9_.:-]{8,128}$/;
const clone=v=>structuredClone(v);

function canonical(v){if(Array.isArray(v))return v.map(canonical);if(v&&typeof v==='object')return Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])]));return v;}
async function sha256Json(v){const b=new TextEncoder().encode(JSON.stringify(canonical(v))),h=await crypto.subtle.digest('SHA-256',b);return [...new Uint8Array(h)].map(x=>x.toString(16).padStart(2,'0')).join('');}
function freezeIdentity(freeze){return {slate_date_et:freeze.slate_date_et,run_mode:freeze.run_mode,frozen_at:freeze.frozen_at,freeze_receipt_sha256:freeze.freeze_receipt_sha256};}
function sameFreeze(a,b){return a?.slate_date_et===b?.slate_date_et&&a?.run_mode===b?.run_mode&&a?.frozen_at===b?.frozen_at&&a?.freeze_receipt_sha256===b?.freeze_receipt_sha256;}
function refreshId(value,label='refresh_request_id'){const id=String(value||'').trim();need(REQUEST_ID.test(id),`${label} invalid`);return id;}
function withoutRequestId(body){const out=clone(body||{});delete out.refresh_request_id;return out;}

export async function createMarketRun({runId,freeze,grant,createdAt=new Date().toISOString()}){
  need(String(runId||'').trim(),'run_id required');validateGrantAgainstFreeze(grant,freeze);need(grant.run_id===runId,'grant run_id mismatch');
  const state={schema_version:'nba_market_run_state_v1',run_id:String(runId),freeze_identity:freezeIdentity(freeze),created_at:createdAt,current_grant:clone(grant),current_api_snapshot:null,current_manual_snapshot:null,api_refresh_history:[],manual_refresh_history:[]};
  state.state_receipt_sha256=await sha256Json({...state,state_receipt_sha256:undefined});return state;
}

export function reconcileMarketGrant(state,freeze,grant){
  validateGrantAgainstFreeze(grant,freeze);need(grant.run_id===state.run_id,'grant run_id drift');need(sameFreeze(state.freeze_identity,freezeIdentity(freeze)),'market run frozen identity drift');const next=clone(state);next.current_grant=clone(grant);return next;
}

export async function marketRefreshReplay(state,kind,requestId,requestPayload){
  need(['api','manual'].includes(kind),'refresh replay kind invalid');const id=refreshId(requestId),payloadSha=await sha256Json(requestPayload);const current=kind==='api'?state.current_api_snapshot:state.current_manual_snapshot;const history=kind==='api'?state.api_refresh_history:state.manual_refresh_history;
  if(current?.refresh_request_id===id){need(current.request_payload_sha256===payloadSha,`${kind} refresh_request_id payload mismatch`);return {replayed:true,snapshot:clone(current)};}
  const old=(history||[]).find(x=>x.refresh_request_id===id);if(old){need(old.request_payload_sha256===payloadSha,`${kind} refresh_request_id payload mismatch`);throw new Error(`${kind} refresh_request_id already belongs to a superseded snapshot`);}
  return null;
}

function allowedSet(state){return new Set((state.current_grant?.allowed_game_ids||[]).map(String));}
function validateSnapshotFreeze(state,snapshot){need(snapshot&&snapshot.freeze_receipt_sha256===state.freeze_identity.freeze_receipt_sha256,'market snapshot freeze receipt mismatch');const captured=Date.parse(String(snapshot.captured_at||'')),frozen=Date.parse(String(state.freeze_identity.frozen_at||''));need(Number.isFinite(captured),'market snapshot captured_at invalid');need(Number.isFinite(frozen)&&captured>=frozen,'market snapshot predates frozen P_model');}

export async function applyApiSnapshot(state,snapshot,{refreshRequestId,requestPayload}={}){
  const requestId=refreshId(refreshRequestId),payload=requestPayload||{regions:String(snapshot?.regions||'')};need(!(await marketRefreshReplay(state,'api',requestId,payload)),'api refresh request already persisted');
  validateSnapshotFreeze(state,snapshot);need(snapshot.schema_version==='nba_odds_api_refresh_v1'&&snapshot.source==='ODDS_API','Odds API snapshot invalid');need(Array.isArray(snapshot.quotes),'Odds API quotes required');const allowed=allowedSet(state);for(const q of snapshot.quotes)need(allowed.has(String(q.game_id)),`Odds API quote outside current market grant ${q.game_id}`);
  const copy=clone(snapshot);copy.refresh_request_id=requestId;copy.request_payload_sha256=await sha256Json(payload);copy.snapshot_sha256=await sha256Json(copy);const next=clone(state);if(next.current_api_snapshot)next.api_refresh_history.push({refresh_request_id:next.current_api_snapshot.refresh_request_id,request_payload_sha256:next.current_api_snapshot.request_payload_sha256,captured_at:next.current_api_snapshot.captured_at,snapshot_sha256:next.current_api_snapshot.snapshot_sha256,quote_count:next.current_api_snapshot.quotes.length,issue_count:(next.current_api_snapshot.issues||[]).length});next.current_api_snapshot=copy;next.state_receipt_sha256=await sha256Json({...next,state_receipt_sha256:undefined});return next;
}

function gamePlayerIndex(freeze,gameId){
  const game=freeze.games.find(g=>String(g.game_id)===String(gameId));need(game,`unknown frozen game ${gameId}`);const byId=new Map(),byName=new Map(),ambiguous=new Set();for(const p of game.players||[]){need(HASH64.test(String(p.player_model_sha256||'')),`frozen player hash missing ${p.player_id}`);byId.set(String(p.player_id),p);const key=normalizeIdentity(p.player_name);if(byName.has(key)){ambiguous.add(key);byName.delete(key);}else if(!ambiguous.has(key))byName.set(key,p);}return {game,byId,byName,ambiguous};
}

export function normalizeManualQuotes(freeze,state,{source_type,captured_at,evidence_id,quotes}){
  need(['BET365_SCREENSHOT','MANUAL_SPORTSBOOK_SCREENSHOT'].includes(String(source_type||'')),'manual source_type invalid');const captured=Date.parse(String(captured_at||'')),frozen=Date.parse(String(state.freeze_identity.frozen_at||''));need(Number.isFinite(captured),'manual captured_at invalid');need(Number.isFinite(frozen)&&captured>=frozen,'manual screenshot predates frozen P_model');need(String(evidence_id||'').trim(),'manual evidence_id required');need(Array.isArray(quotes)&&quotes.length>0,'manual quotes required');const allowed=allowedSet(state),out=[];
  for(const [i,raw] of quotes.entries()){
    const gameId=String(raw.game_id||'');need(allowed.has(gameId),`manual quotes[${i}] game not market-access eligible`);const {byId,byName,ambiguous}=gamePlayerIndex(freeze,gameId);let player=null;if(String(raw.player_id||'').trim())player=byId.get(String(raw.player_id));else{const key=normalizeIdentity(raw.player_name);need(key&&!ambiguous.has(key),`manual quotes[${i}] ambiguous player identity`);player=byName.get(key);}need(player,`manual quotes[${i}] player not frozen`);
    const head=String(raw.stat_type||'').toLowerCase();need(['assists','rebounds'].includes(head)&&player.heads?.[head],`manual quotes[${i}] head not frozen`);need(HASH64.test(String(player.heads[head].head_model_sha256||'')),`manual quotes[${i}] frozen head hash missing`);need(String(raw.side||'over').toLowerCase()==='over','NBA V1 manual markets are Overs only');const threshold=Number(raw.threshold),price=Number(raw.decimal_price);need(Number.isFinite(threshold)&&Math.abs(threshold*2-Math.round(threshold*2))<=1e-9,`manual quotes[${i}] threshold invalid`);need(Number.isFinite(price)&&price>1,`manual quotes[${i}] price invalid`);need(String(raw.bookmaker||'').trim(),`manual quotes[${i}] bookmaker required`);
    out.push({source:String(source_type),evidence_id:String(evidence_id),game_id:gameId,player_id:String(player.player_id),player_name:String(player.player_name),stat_type:head,side:'over',threshold,decimal_price:price,bookmaker:String(raw.bookmaker),captured_at:String(captured_at),player_model_sha256:String(player.player_model_sha256),head_model_sha256:String(player.heads[head].head_model_sha256)});
  }
  return out;
}

export async function applyManualSnapshot(state,freeze,body){
  const requestId=refreshId(body.refresh_request_id),payload=withoutRequestId(body);need(!(await marketRefreshReplay(state,'manual',requestId,payload)),'manual refresh request already persisted');need(body.freeze_receipt_sha256===state.freeze_identity.freeze_receipt_sha256,'manual refresh freeze receipt mismatch');const quotes=normalizeManualQuotes(freeze,state,body);const snapshot={schema_version:'nba_manual_market_refresh_v1',source_type:String(body.source_type),refresh_request_id:requestId,request_payload_sha256:await sha256Json(payload),captured_at:String(body.captured_at),evidence_id:String(body.evidence_id),freeze_receipt_sha256:String(body.freeze_receipt_sha256),quotes};validateSnapshotFreeze(state,snapshot);snapshot.snapshot_sha256=await sha256Json(snapshot);const next=clone(state);if(next.current_manual_snapshot)next.manual_refresh_history.push({refresh_request_id:next.current_manual_snapshot.refresh_request_id,request_payload_sha256:next.current_manual_snapshot.request_payload_sha256,captured_at:next.current_manual_snapshot.captured_at,snapshot_sha256:next.current_manual_snapshot.snapshot_sha256,quote_count:next.current_manual_snapshot.quotes.length,evidence_id:next.current_manual_snapshot.evidence_id});next.current_manual_snapshot=snapshot;next.state_receipt_sha256=await sha256Json({...next,state_receipt_sha256:undefined});return next;
}

function probabilityIndex(freeze){const out=new Map();for(const game of freeze.games||[])for(const p of game.players||[]){need(HASH64.test(String(p.player_model_sha256||'')),`ranking frozen player hash missing ${p.player_id}`);for(const [head,h] of Object.entries(p.heads||{})){need(HASH64.test(String(h.head_model_sha256||'')),`ranking frozen head hash missing ${p.player_id}.${head}`);out.set(`${game.game_id}|${p.player_id}|${head}`,{game,player:p,head:h});}}return out;}

export function rankCurrentMarket(state,freeze){
  need(sameFreeze(state.freeze_identity,freezeIdentity(freeze)),'ranking freeze identity drift');const allowed=allowedSet(state),combined=[...(state.current_api_snapshot?.quotes||[]),...(state.current_manual_snapshot?.quotes||[])].filter(q=>allowed.has(String(q.game_id)));const best=chooseBestExactPrices(combined),index=probabilityIndex(freeze),evaluated=[],issues=[];
  for(const quote of best){const row=index.get(`${quote.game_id}|${quote.player_id}|${quote.stat_type}`);if(!row){issues.push({type:'NO_FROZEN_HEAD',quote});continue;}try{if(quote.player_model_sha256!==undefined)need(quote.player_model_sha256===row.player.player_model_sha256,'market player hash mismatch');if(quote.head_model_sha256!==undefined)need(quote.head_model_sha256===row.head.head_model_sha256,'market head hash mismatch');const e=evaluateExactMarket(quote,row.head.probability_grid);evaluated.push({...e,team:row.player.team,confidence:row.player.confidence,fragility:row.player.fragility,model_mean:row.head.final_mean,player_model_sha256:row.player.player_model_sha256,head_model_sha256:row.head.head_model_sha256,freeze_receipt_sha256:freeze.freeze_receipt_sha256});}catch(error){issues.push({type:'MARKET_BINDING_OR_THRESHOLD_REJECTED',game_id:quote.game_id,player_id:quote.player_id,stat_type:quote.stat_type,threshold:quote.threshold,bookmaker:quote.bookmaker,error:error.message});}}
  const positives=rankPositiveEdges(evaluated),assists=positives.filter(x=>x.stat_type==='assists'),rebounds=positives.filter(x=>x.stat_type==='rebounds');return {schema_version:'nba_layer4_rankings_v1',run_id:state.run_id,slate_date_et:freeze.slate_date_et,run_mode:freeze.run_mode,frozen_at:freeze.frozen_at,freeze_receipt_sha256:freeze.freeze_receipt_sha256,market_snapshot:{api_snapshot_sha256:state.current_api_snapshot?.snapshot_sha256||null,manual_snapshot_sha256:state.current_manual_snapshot?.snapshot_sha256||null},decision:positives.length?'BEST_SINGLE':'NO_BET',best_single:positives[0]||null,top_10_combined:positives.slice(0,10),assists_positive:assists,rebounds_positive:rebounds,all_evaluated:evaluated,issues:[...(state.current_api_snapshot?.issues||[]),...issues]};
}

export function marketStateSummary(state){return {schema_version:state.schema_version,run_id:state.run_id,freeze_identity:state.freeze_identity,current_grant:{allowed_game_ids:state.current_grant?.allowed_game_ids||[],invalidated_game_ids:state.current_grant?.invalidated_game_ids||[]},current_api_snapshot:state.current_api_snapshot?{refresh_request_id:state.current_api_snapshot.refresh_request_id,request_payload_sha256:state.current_api_snapshot.request_payload_sha256,captured_at:state.current_api_snapshot.captured_at,snapshot_sha256:state.current_api_snapshot.snapshot_sha256,quote_count:state.current_api_snapshot.quotes.length}:null,current_manual_snapshot:state.current_manual_snapshot?{refresh_request_id:state.current_manual_snapshot.refresh_request_id,request_payload_sha256:state.current_manual_snapshot.request_payload_sha256,captured_at:state.current_manual_snapshot.captured_at,snapshot_sha256:state.current_manual_snapshot.snapshot_sha256,quote_count:state.current_manual_snapshot.quotes.length,evidence_id:state.current_manual_snapshot.evidence_id}:null,api_refresh_count:state.api_refresh_history.length+(state.current_api_snapshot?1:0),manual_refresh_count:state.manual_refresh_history.length+(state.current_manual_snapshot?1:0),state_receipt_sha256:state.state_receipt_sha256};}
