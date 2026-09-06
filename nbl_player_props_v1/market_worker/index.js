/** Post-freeze NBL assists/rebounds market evaluator.
 *
 * This Worker never owns or computes P_model. It accepts market observations only
 * after the research Worker reports an immutable FROZEN run, fetches exact frozen
 * probability grids from that run, verifies the freeze receipt, and computes EV.
 */
const DEFAULT_RESEARCH_BASE='https://nbl-player-props-research-v1.nickarnott01.workers.dev';
const ALLOWED_SOURCES=new Set(['odds_api','screenshot','public_web']);
const ALLOWED_STATS=new Set(['assists','rebounds']);
const ALLOWED_SIDES=new Set(['over','under']);
const CONF_RANK={A:0,B:1,C:2};
const FRAG_RANK={LOW:0,MEDIUM:1,HIGH:2};

const response=(body,status=200)=>new Response(JSON.stringify(body),{status,headers:{'content-type':'application/json','cache-control':'no-store','access-control-allow-origin':'*'}});
const need=(condition,message)=>{if(!condition)throw new Error(message);};
const normName=value=>String(value||'').normalize('NFKD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,'');
const hash64=value=>/^[0-9a-f]{64}$/.test(String(value||''));
const finite=value=>Number.isFinite(Number(value));
function exactKeys(obj,allowed,label){need(obj&&typeof obj==='object'&&!Array.isArray(obj),`${label} must be an object`);for(const key of Object.keys(obj))need(allowed.includes(key),`${label} unexpected field ${key}`);}
function researchBase(env){const raw=String(env?.RESEARCH_BASE||DEFAULT_RESEARCH_BASE).replace(/\/+$/,'');need(/^https:\/\/[a-z0-9.-]+$/i.test(raw),'RESEARCH_BASE invalid');return raw;}
async function getJson(url){const res=await fetch(url,{headers:{accept:'application/json','user-agent':'nbl-market-eval/1.0'},signal:AbortSignal.timeout(15_000)});const text=await res.text();need(text.length<4_000_000,'Research response too large');let body;try{body=JSON.parse(text);}catch{throw new Error('Research response invalid JSON');}need(res.ok,`Research Worker ${res.status}: ${body?.error||'request failed'}`);return body;}

function validateMarket(row,index){
  exactKeys(row,['fixture_id','player_id','player_name','stat_type','side','threshold','decimal_price','bookmaker','captured_at','source_type'],`markets[${index}]`);
  need(String(row.fixture_id||'').trim(),`markets[${index}].fixture_id required`);
  need(String(row.player_name||'').trim(),`markets[${index}].player_name required`);
  const stat=String(row.stat_type||'').toLowerCase(),side=String(row.side||'').toLowerCase(),source=String(row.source_type||'').toLowerCase();
  need(ALLOWED_STATS.has(stat),`markets[${index}].stat_type unsupported`);need(ALLOWED_SIDES.has(side),`markets[${index}].side unsupported`);need(ALLOWED_SOURCES.has(source),`markets[${index}].source_type unsupported`);
  const threshold=Number(row.threshold),price=Number(row.decimal_price);need(finite(threshold)&&threshold>=0&&threshold<=40,`markets[${index}].threshold invalid`);need(Math.abs(threshold*2-Math.round(threshold*2))<=1e-9,`markets[${index}].threshold must be integer/half-point`);need(finite(price)&&price>1&&price<=1000,`markets[${index}].decimal_price invalid`);need(String(row.bookmaker||'').trim(),`markets[${index}].bookmaker required`);need(Number.isFinite(Date.parse(String(row.captured_at||''))),`markets[${index}].captured_at invalid`);
  return {...row,fixture_id:String(row.fixture_id),player_id:row.player_id?String(row.player_id):null,player_name:String(row.player_name).trim(),stat_type:stat,side,source_type:source,threshold,decimal_price:price,bookmaker:String(row.bookmaker).trim(),captured_at:String(row.captured_at)};
}
function playerIndexes(freeze){
  const byId=new Map(),byName=new Map();
  for(const p of freeze.players||[]){const key=String(p.player_key||'');need(key,'Frozen player key missing');const id=String(p.player_id||'').trim();if(id){need(!byId.has(id),`Duplicate frozen player_id ${id}`);byId.set(id,p);}const n=normName(p.player_name);need(n,'Frozen player name missing');if(!byName.has(n))byName.set(n,[]);byName.get(n).push(p);}
  return {byId,byName};
}
function resolvePlayer(index,row){
  if(row.player_id){const hit=index.byId.get(row.player_id);if(hit)return hit;}
  const matches=index.byName.get(normName(row.player_name))||[];need(matches.length===1,`Market player ${row.player_name} matched ${matches.length} frozen players`);return matches[0];
}
function findLine(grid,threshold){
  const integer=Math.abs(threshold-Math.round(threshold))<=1e-9;const rows=integer?grid?.integer_push_grid:grid?.half_point_grid;need(Array.isArray(rows),'Frozen probability grid missing');const found=rows.filter(r=>Math.abs(Number(r.line)-threshold)<=1e-9);need(found.length===1,`Exact frozen threshold ${threshold} unavailable`);return found[0];
}
function evaluateRow(row,frozenPlayer,freeze){
  const head=frozenPlayer?.heads?.[row.stat_type];need(head&&typeof head==='object',`Frozen ${row.stat_type} unavailable for ${row.player_name}`);const line=findLine(head.probability_grid,row.threshold);const pWin=Number(line[row.side]),pPush=Number(line.push||0),other=row.side==='over'?'under':'over',pLoss=Number(line[other]);need([pWin,pPush,pLoss].every(Number.isFinite)&&Math.min(pWin,pPush,pLoss)>=-1e-12,'Frozen probability partition invalid');need(Math.abs(pWin+pPush+pLoss-1)<=1e-8,'Frozen probability partition failed');const nonPush=pWin+pLoss,conditional=nonPush>0?pWin/nonPush:null,breakEven=1/row.decimal_price,fair=pWin>0?nonPush/pWin:null,ev=pWin*(row.decimal_price-1)-pLoss;
  return {...row,frozen_player_name:frozenPlayer.player_name,frozen_player_id:frozenPlayer.player_id??null,p_win:pWin,p_push:pPush,p_loss:pLoss,conditional_win_probability:conditional,market_break_even_probability:breakEven,probability_edge:conditional===null?null:conditional-breakEven,fair_decimal_price:fair,ev_per_unit:ev,positive_ev:ev>0,confidence:String(head.confidence||'C'),fragility:String(head.fragility||'HIGH'),freeze_receipt_sha256:freeze.freeze_receipt_sha256,frozen_at:freeze.frozen_at};
}
function bestPrices(rows){const best=new Map();for(const row of rows){const identity=row.player_id?`id:${row.player_id}`:`name:${normName(row.player_name)}`;const key=[row.fixture_id,identity,row.stat_type,row.side,row.threshold].join('|');const old=best.get(key);if(!old||row.decimal_price>old.decimal_price||(row.decimal_price===old.decimal_price&&`${row.captured_at}\0${row.bookmaker.toLowerCase()}`>`${old.captured_at}\0${old.bookmaker.toLowerCase()}`))best.set(key,row);}return [...best.values()];}
function ranking(a,b){return b.ev_per_unit-a.ev_per_unit||(CONF_RANK[a.confidence]??99)-(CONF_RANK[b.confidence]??99)||(FRAG_RANK[a.fragility]??99)-(FRAG_RANK[b.fragility]??99)||a.stat_type.localeCompare(b.stat_type)||a.player_name.localeCompare(b.player_name)||a.threshold-b.threshold||a.bookmaker.localeCompare(b.bookmaker);}

async function evaluate(input,env){
  exactKeys(input,['run_id','expected_freeze_receipt_sha256','markets'],'request');const runId=String(input.run_id||'');need(/^[a-f0-9]{64}$/.test(runId),'run_id invalid');const expected=String(input.expected_freeze_receipt_sha256||'');need(hash64(expected),'expected_freeze_receipt_sha256 required');need(Array.isArray(input.markets)&&input.markets.length>0&&input.markets.length<=250,'markets must contain 1-250 rows');
  const base=researchBase(env),run=await getJson(`${base}/v1/match-runs/${runId}`);need(run.status==='FROZEN'&&run.freeze?.status==='FROZEN','P_MODEL_STATUS must be FROZEN before market evaluation');const freeze=run.freeze;need(hash64(freeze.freeze_receipt_sha256)&&freeze.freeze_receipt_sha256===expected,'Freeze receipt mismatch');need(Number.isFinite(Date.parse(String(freeze.frozen_at||''))),'Frozen timestamp invalid');const marketRows=bestPrices(input.markets.map(validateMarket));for(const row of marketRows)need(row.fixture_id===String(freeze.fixture_id),'Market fixture does not match frozen fixture');
  const pIndex=playerIndexes(freeze),cache=new Map(),evaluated=[];
  for(const row of marketRows){const summary=resolvePlayer(pIndex,row),key=String(summary.player_key);let full=cache.get(key);if(!full){const fetched=await getJson(`${base}/v1/match-runs/${runId}/players/${encodeURIComponent(key)}`);need(fetched.freeze_receipt_sha256===expected&&fetched.frozen_at===freeze.frozen_at,'Frozen player receipt/timestamp mismatch');full=fetched.player;need(full&&typeof full==='object','Frozen player response missing');cache.set(key,full);}evaluated.push(evaluateRow(row,full,freeze));}
  evaluated.sort(ranking);const positives=evaluated.filter(x=>x.positive_ev);positives.forEach((row,i)=>row.positive_edge_rank=i+1);
  return {market_data:true,p_model_mutated:false,p_model_status:'FROZEN',run_id:runId,fixture_id:freeze.fixture_id,freeze_receipt_sha256:expected,frozen_at:freeze.frozen_at,market_records_received:input.markets.length,market_records_evaluated:evaluated.length,evaluated,positive_edges:positives,best_single:positives[0]||null,no_forced_bet:positives.length===0};
}

export default {async fetch(request,env){try{if(request.method==='OPTIONS')return new Response(null,{status:204,headers:{'access-control-allow-origin':'*','access-control-allow-methods':'GET,POST,OPTIONS','access-control-allow-headers':'content-type'}});const url=new URL(request.url);if(request.method==='GET'&&url.pathname==='/health')return response({ok:true,service:'nbl-player-props-market-v1',version:'1.0.0',market_data:true,research_base:researchBase(env),supported_stats:['assists','rebounds'],supported_sources:['odds_api','screenshot','public_web']});if(request.method==='POST'&&url.pathname==='/v1/evaluate'){const raw=await request.text();need(raw.length<=300_000,'Request too large');return response(await evaluate(JSON.parse(raw),env));}return response({error:'Not found'},404);}catch(error){return response({market_data:true,p_model_mutated:false,error:error.message},422);}}};

export {evaluate,normName};
