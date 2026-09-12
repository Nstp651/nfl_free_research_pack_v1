/** Post-freeze NBL assists/rebounds market gateway.
 *
 * Two responsibilities only:
 * 1) evaluate user/public market observations against one immutable frozen run;
 * 2) after freeze verification, optionally fetch live Odds API NBL props and
 *    immediately evaluate them against that same frozen run.
 *
 * This Worker never owns, computes, or mutates P_model.
 */
const DEFAULT_RESEARCH_BASE='https://nbl-player-props-research-v1.nickarnott01.workers.dev';
const ODDS_HOST='https://api.the-odds-api.com';
const ODDS_SPORT='basketball_nbl';
const DEFAULT_ODDS_MARKETS=['player_assists','player_rebounds','player_assists_alternate','player_rebounds_alternate'];
const BASE_ODDS_MARKETS=['player_assists','player_rebounds'];
const ALLOWED_ODDS_MARKETS=new Set(DEFAULT_ODDS_MARKETS);
const ALLOWED_SOURCES=new Set(['odds_api','screenshot','public_web']);
const ALLOWED_STATS=new Set(['assists','rebounds']);
const ALLOWED_SIDES=new Set(['over','under']);
const CONF_RANK={A:0,B:1,C:2};
const FRAG_RANK={LOW:0,MEDIUM:1,HIGH:2};
const KICKOFF_TOLERANCE_MS=30*60*1000;
const MAX_UPSTREAM_CHARS=8_000_000;
const MAX_MARKETS=250;

const response=(body,status=200)=>new Response(JSON.stringify(body),{status,headers:{'content-type':'application/json','cache-control':'no-store','access-control-allow-origin':'*'}});
const need=(condition,message)=>{if(!condition)throw new Error(message);};
const normName=value=>String(value||'').normalize('NFKD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,'');
const hash64=value=>/^[0-9a-f]{64}$/.test(String(value||''));
const finite=value=>Number.isFinite(Number(value));
function canonicalValue(v){if(Array.isArray(v))return v.map(canonicalValue);if(v&&typeof v==='object')return Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonicalValue(v[k])]));return v;}
export async function sha256Json(value){const bytes=new TextEncoder().encode(JSON.stringify(canonicalValue(value)));const digest=await crypto.subtle.digest('SHA-256',bytes);return [...new Uint8Array(digest)].map(x=>x.toString(16).padStart(2,'0')).join('');}
function exactKeys(obj,allowed,label){need(obj&&typeof obj==='object'&&!Array.isArray(obj),`${label} must be an object`);for(const key of Object.keys(obj))need(allowed.includes(key),`${label} unexpected field ${key}`);}
function researchBase(env){const raw=String(env?.RESEARCH_BASE||DEFAULT_RESEARCH_BASE).replace(/\/+$/,'');need(/^https:\/\/[a-z0-9.-]+$/i.test(raw),'RESEARCH_BASE invalid');return raw;}
async function readJsonResponse(res,label){const text=await res.text();need(text.length<MAX_UPSTREAM_CHARS,`${label} response too large`);let body;try{body=JSON.parse(text);}catch{throw new Error(`${label} invalid JSON (${res.status})`);}return {body,text};}
async function getJson(url,env){const init={headers:{accept:'application/json','user-agent':'nbl-market-v1/1.2.1'},signal:AbortSignal.timeout(15_000)};const res=env?.RESEARCH&&typeof env.RESEARCH.fetch==='function'?await env.RESEARCH.fetch(new Request(url,init)):await fetch(url,init);const {body}=await readJsonResponse(res,'Research response');need(res.ok,`Research Worker ${res.status}: ${body?.error||'request failed'}`);return body;}

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
  for(const p of freeze.players||[]){const key=String(p.player_key||'');need(key,'Frozen player key missing');need(hash64(p.player_model_sha256),'Frozen player hash missing');const id=String(p.player_id||'').trim();if(id){need(!byId.has(id),`Duplicate frozen player_id ${id}`);byId.set(id,p);}const n=normName(p.player_name);need(n,'Frozen player name missing');if(!byName.has(n))byName.set(n,[]);byName.get(n).push(p);}
  return {byId,byName};
}
function resolvePlayer(index,row){
  if(row.player_id){const hit=index.byId.get(row.player_id);if(hit)return hit;}
  const matches=index.byName.get(normName(row.player_name))||[];need(matches.length===1,`Market player ${row.player_name} matched ${matches.length} frozen players`);return matches[0];
}
function dedupeResolved(rows){
  const best=new Map();
  for(const item of rows){
    const {row,summary}=item,key=[row.fixture_id,String(summary.player_key),row.stat_type,row.side,row.threshold].join('|'),old=best.get(key);
    if(!old||row.decimal_price>old.row.decimal_price||(row.decimal_price===old.row.decimal_price&&`${row.captured_at}\0${row.bookmaker.toLowerCase()}`>`${old.row.captured_at}\0${old.row.bookmaker.toLowerCase()}`))best.set(key,item);
  }
  return [...best.values()];
}
function dedupeRawRows(rows){
  const best=new Map();
  for(const row of rows){const key=[normName(row.player_name),row.stat_type,row.side,row.threshold].join('|'),old=best.get(key);if(!old||row.decimal_price>old.decimal_price||(row.decimal_price===old.decimal_price&&row.bookmaker.toLowerCase()<old.bookmaker.toLowerCase()))best.set(key,row);}
  return [...best.values()];
}
function findLine(grid,threshold){
  const integer=Math.abs(threshold-Math.round(threshold))<=1e-9;const rows=integer?grid?.integer_push_grid:grid?.half_point_grid;need(Array.isArray(rows),'Frozen probability grid missing');const found=rows.filter(r=>Math.abs(Number(r.line)-threshold)<=1e-9);need(found.length===1,`Exact frozen threshold ${threshold} unavailable`);return found[0];
}
function evaluateRow(row,frozenPlayer,freeze){
  const head=frozenPlayer?.heads?.[row.stat_type];need(head&&typeof head==='object',`Frozen ${row.stat_type} unavailable for ${row.player_name}`);const line=findLine(head.probability_grid,row.threshold);const pWin=Number(line[row.side]),pPush=Number(line.push||0),other=row.side==='over'?'under':'over',pLoss=Number(line[other]);need([pWin,pPush,pLoss].every(Number.isFinite)&&Math.min(pWin,pPush,pLoss)>=-1e-12,'Frozen probability partition invalid');need(Math.abs(pWin+pPush+pLoss-1)<=1e-8,'Frozen probability partition failed');const nonPush=pWin+pLoss,conditional=nonPush>0?pWin/nonPush:null,breakEven=1/row.decimal_price,fair=pWin>0?nonPush/pWin:null,ev=pWin*(row.decimal_price-1)-pLoss;
  return {...row,frozen_player_name:frozenPlayer.player_name,frozen_player_id:frozenPlayer.player_id??null,p_win:pWin,p_push:pPush,p_loss:pLoss,conditional_win_probability:conditional,market_break_even_probability:breakEven,probability_edge:conditional===null?null:conditional-breakEven,fair_decimal_price:fair,ev_per_unit:ev,positive_ev:ev>0,confidence:String(head.confidence||'C'),fragility:String(head.fragility||'HIGH'),freeze_receipt_sha256:freeze.freeze_receipt_sha256,frozen_at:freeze.frozen_at};
}
function ranking(a,b){return b.ev_per_unit-a.ev_per_unit||(CONF_RANK[a.confidence]??99)-(CONF_RANK[b.confidence]??99)||(FRAG_RANK[a.fragility]??99)-(FRAG_RANK[b.fragility]??99)||a.stat_type.localeCompare(b.stat_type)||a.player_name.localeCompare(b.player_name)||a.threshold-b.threshold||a.bookmaker.localeCompare(b.bookmaker);}

async function loadFrozenRun(input,env){
  const runId=String(input.run_id||'');need(/^[a-f0-9]{64}$/.test(runId),'run_id invalid');const expected=String(input.expected_freeze_receipt_sha256||'');need(hash64(expected),'expected_freeze_receipt_sha256 required');
  const base=researchBase(env),run=await getJson(`${base}/v1/match-runs/${runId}`,env);need(run.status==='FROZEN'&&run.freeze?.status==='FROZEN','P_MODEL_STATUS must be FROZEN before market evaluation');const freeze=run.freeze;need(hash64(freeze.freeze_receipt_sha256)&&freeze.freeze_receipt_sha256===expected,'Freeze receipt mismatch');const frozenAtMs=Date.parse(String(freeze.frozen_at||''));need(Number.isFinite(frozenAtMs),'Frozen timestamp invalid');return {runId,expected,base,run,freeze,frozenAtMs};
}

export async function evaluate(input,env){
  exactKeys(input,['run_id','expected_freeze_receipt_sha256','markets'],'request');need(Array.isArray(input.markets)&&input.markets.length>0&&input.markets.length<=MAX_MARKETS,`markets must contain 1-${MAX_MARKETS} rows`);
  const state=await loadFrozenRun(input,env),{runId,expected,base,freeze,frozenAtMs}=state;
  const validated=input.markets.map(validateMarket);for(const row of validated){need(row.fixture_id===String(freeze.fixture_id),'Market fixture does not match frozen fixture');need(Date.parse(row.captured_at)>=frozenAtMs,'Market observation predates P_model freeze');}
  const pIndex=playerIndexes(freeze),resolved=dedupeResolved(validated.map(row=>({row,summary:resolvePlayer(pIndex,row)}))),cache=new Map(),evaluated=[];
  for(const {row,summary} of resolved){const key=String(summary.player_key);let full=cache.get(key);if(!full){const fetched=await getJson(`${base}/v1/match-runs/${runId}/players/${encodeURIComponent(key)}`,env);need(fetched.freeze_receipt_sha256===expected&&fetched.frozen_at===freeze.frozen_at,'Frozen player receipt/timestamp mismatch');need(fetched.player_model_sha256===summary.player_model_sha256,'Frozen player hash receipt mismatch');full=fetched.player;need(full&&typeof full==='object','Frozen player response missing');need(await sha256Json(full)===summary.player_model_sha256,'Frozen player payload hash mismatch');cache.set(key,full);}evaluated.push(evaluateRow(row,full,freeze));}
  evaluated.sort(ranking);const positives=evaluated.filter(x=>x.positive_ev);positives.forEach((row,i)=>row.positive_edge_rank=i+1);
  return {market_data:true,p_model_mutated:false,p_model_status:'FROZEN',run_id:runId,fixture_id:freeze.fixture_id,freeze_receipt_sha256:expected,frozen_at:freeze.frozen_at,market_records_received:input.markets.length,market_records_evaluated:evaluated.length,evaluated,positive_edges:positives,best_single:positives[0]||null,no_forced_bet:positives.length===0};
}

function oddsQuota(res){return {requests_remaining:res.headers.get('x-requests-remaining'),requests_used:res.headers.get('x-requests-used'),requests_last:res.headers.get('x-requests-last')};}
async function oddsFetch(url,label){const res=await fetch(url,{headers:{accept:'application/json','user-agent':'nbl-market-v1/1.2.1'},signal:AbortSignal.timeout(15_000),cf:{cacheTtl:label==='Odds events'?240:25,cacheEverything:true}});const {body}=await readJsonResponse(res,label);return {res,body,quota:oddsQuota(res)};}
function fixtureWindow(fixture){const tip=Date.parse(String(fixture?.start_time||''));need(Number.isFinite(tip),'Frozen fixture start_time invalid');return {from:new Date(tip-24*60*60*1000).toISOString(),to:new Date(tip+24*60*60*1000).toISOString()};}
async function fetchOddsEvents(env,fixture){
  need(env?.ODDS_API_KEY,'ODDS_API_KEY is not configured');const window=fixtureWindow(fixture);const q=new URLSearchParams({apiKey:env.ODDS_API_KEY,dateFormat:'iso',commenceTimeFrom:window.from,commenceTimeTo:window.to});const out=await oddsFetch(`${ODDS_HOST}/v4/sports/${ODDS_SPORT}/events?${q}`,'Odds events');need(out.res.ok,`Odds events unavailable (${out.res.status})`);need(Array.isArray(out.body),'Odds events returned invalid payload');return out;
}
async function fetchFeaturedOddsEvents(env,fixture){
  need(env?.ODDS_API_KEY,'ODDS_API_KEY is not configured');const window=fixtureWindow(fixture);const q=new URLSearchParams({apiKey:env.ODDS_API_KEY,regions:'au',markets:'h2h',oddsFormat:'decimal',dateFormat:'iso',commenceTimeFrom:window.from,commenceTimeTo:window.to});const out=await oddsFetch(`${ODDS_HOST}/v4/sports/${ODDS_SPORT}/odds?${q}`,'Odds featured fallback');need(out.res.ok,`Odds featured fallback unavailable (${out.res.status})`);need(Array.isArray(out.body),'Odds featured fallback returned invalid payload');return out;
}
function eventOrientation(event,fixture){const home=normName(fixture?.home_team?.name),away=normName(fixture?.away_team?.name),eventHome=normName(event?.home_team),eventAway=normName(event?.away_team);if(eventHome===home&&eventAway===away)return'exact';if(eventHome===away&&eventAway===home)return'swapped';return'none';}
export function resolveOddsEvent(events,fixture){
  const home=normName(fixture?.home_team?.name),away=normName(fixture?.away_team?.name),tip=Date.parse(String(fixture?.start_time||''));need(home&&away&&Number.isFinite(tip),'Frozen fixture identity incomplete');
  const matches=(Array.isArray(events)?events:[]).filter(e=>e&&eventOrientation(e,fixture)!=='none'&&Number.isFinite(Date.parse(e.commence_time))&&Math.abs(Date.parse(e.commence_time)-tip)<=KICKOFF_TOLERANCE_MS);
  need(matches.length===1,`Expected exactly one Odds API event for frozen fixture; found ${matches.length}`);need(String(matches[0].id||'').trim(),'Odds API event id missing');return matches[0];
}
function eventDiagnostics(events,fixture){
  const tip=Date.parse(String(fixture?.start_time||''));return (Array.isArray(events)?events:[]).map(e=>({event_id:String(e?.id||''),home_team:String(e?.home_team||''),away_team:String(e?.away_team||''),commence_time:String(e?.commence_time||''),team_orientation:eventOrientation(e,fixture),kickoff_delta_minutes:Number.isFinite(tip)&&Number.isFinite(Date.parse(String(e?.commence_time||'')))?Math.round((Date.parse(String(e.commence_time))-tip)/60000):null})).filter(x=>x.kickoff_delta_minutes!==null&&Math.abs(x.kickoff_delta_minutes)<=24*60).slice(0,12);
}
function requestedOddsMarkets(input){const raw=input.markets===undefined?DEFAULT_ODDS_MARKETS:input.markets;need(Array.isArray(raw)&&raw.length>0&&raw.length<=4,'Odds API markets must contain 1-4 supported keys');const out=[...new Set(raw.map(String))];for(const key of out)need(ALLOWED_ODDS_MARKETS.has(key),`Unsupported Odds API market ${key}`);return out;}
async function fetchEventOdds(env,event,markets){
  const q=new URLSearchParams({apiKey:env.ODDS_API_KEY,regions:'au',markets:markets.join(','),oddsFormat:'decimal',dateFormat:'iso'});return oddsFetch(`${ODDS_HOST}/v4/sports/${ODDS_SPORT}/events/${encodeURIComponent(event.id)}/odds?${q}`,'Odds props');
}
function oddsErrorCode(body){return String(body?.error_code||body?.code||'').toUpperCase();}
function marketStat(key){if(key==='player_assists'||key==='player_assists_alternate')return'assists';if(key==='player_rebounds'||key==='player_rebounds_alternate')return'rebounds';return null;}
export function normalizeOddsRows(raw,event,fixtureId,capturedAt){
  need(raw&&String(raw.id||'')===String(event.id),'Odds event response identity mismatch');need(normName(raw.home_team)===normName(event.home_team)&&normName(raw.away_team)===normName(event.away_team),'Odds event teams mismatch');need(Number.isFinite(Date.parse(raw.commence_time))&&Math.abs(Date.parse(raw.commence_time)-Date.parse(event.commence_time))<=KICKOFF_TOLERANCE_MS,'Odds event tipoff mismatch');
  const rows=[];for(const book of Array.isArray(raw.bookmakers)?raw.bookmakers:[]){for(const market of Array.isArray(book.markets)?book.markets:[]){const stat=marketStat(String(market?.key||''));if(!stat)continue;for(const o of Array.isArray(market.outcomes)?market.outcomes:[]){const side=String(o?.name||'').toLowerCase();if(!ALLOWED_SIDES.has(side)||typeof o?.description!=='string'||!finite(o?.price)||Number(o.price)<=1||!finite(o?.point))continue;const threshold=Number(o.point);if(threshold<0||threshold>40||Math.abs(threshold*2-Math.round(threshold*2))>1e-9)continue;rows.push({fixture_id:String(fixtureId),player_id:null,player_name:String(o.description).trim(),stat_type:stat,side,threshold,decimal_price:Number(o.price),bookmaker:String(book.title||book.key||'Unknown'),captured_at:capturedAt,source_type:'odds_api'});}}}
  return dedupeRawRows(rows);
}

export async function fetchAndEvaluateOddsApi(input,env){
  exactKeys(input,['run_id','expected_freeze_receipt_sha256','markets'],'request');
  const state=await loadFrozenRun(input,env);
  if(!env?.ODDS_API_KEY)return {market_data:true,p_model_mutated:false,p_model_status:'FROZEN',run_id:state.runId,fixture_id:state.freeze.fixture_id,freeze_receipt_sha256:state.expected,frozen_at:state.freeze.frozen_at,odds_api_support:'NOT_CONFIGURED',message:'ODDS_API_KEY is not configured on the Market Worker',market_records_received:0,evaluation:null};

  const requested=requestedOddsMarkets(input),fixture=state.run.lock?.fixture||state.freeze.fixture,events=await fetchOddsEvents(env,fixture);let event,eventResolutionSource='events_endpoint',featured=null;const quota=[events.quota];
  try{event=resolveOddsEvent(events.body,fixture);}catch(primaryError){
    featured=await fetchFeaturedOddsEvents(env,fixture);quota.push(featured.quota);
    try{event=resolveOddsEvent(featured.body,fixture);eventResolutionSource='featured_h2h_odds_fallback';}
    catch(fallbackError){return {market_data:true,p_model_mutated:false,p_model_status:'FROZEN',run_id:state.runId,fixture_id:state.freeze.fixture_id,freeze_receipt_sha256:state.expected,frozen_at:state.freeze.frozen_at,odds_api_support:'EVENT_NOT_FOUND',message:`${primaryError.message}; featured-odds fallback: ${fallbackError.message}`,event_resolution_source:'none',event_resolution_diagnostics:{events_endpoint_count:events.body.length,featured_odds_count:featured.body.length,nearby_events:eventDiagnostics(events.body,fixture),nearby_featured_events:eventDiagnostics(featured.body,fixture)},quota,market_records_received:0,evaluation:null};}
  }

  const capturedAt=new Date().toISOString();need(Date.parse(capturedAt)>=state.frozenAtMs,'Odds API capture unexpectedly predates freeze');
  const first=await fetchEventOdds(env,event,requested);quota.push(first.quota);let rows=[],marketsUsed=[],marketsUnsupported=[],fallbackProbed=false;
  if(first.res.ok){rows=normalizeOddsRows(first.body,event,state.freeze.fixture_id,capturedAt);marketsUsed=[...requested];}
  else if(oddsErrorCode(first.body)==='INVALID_MARKET'){
    fallbackProbed=true;
    for(const key of requested){
      const one=await fetchEventOdds(env,event,[key]);quota.push(one.quota);
      if(one.res.ok){marketsUsed.push(key);rows.push(...normalizeOddsRows(one.body,event,state.freeze.fixture_id,capturedAt));}
      else if(oddsErrorCode(one.body)==='INVALID_MARKET')marketsUnsupported.push(key);
      else throw new Error(`Odds props ${key} unavailable (${one.res.status}): ${String(one.body?.message||one.body?.error||'request failed')}`);
    }
    rows=dedupeRawRows(rows);
  }else throw new Error(`Odds props unavailable (${first.res.status}): ${String(first.body?.message||first.body?.error||'request failed')}`);

  const eventMeta={event_id:event.id,home_team:event.home_team,away_team:event.away_team,commence_time:event.commence_time,team_orientation:eventOrientation(event,fixture)};
  if(marketsUsed.length===0)return {market_data:true,p_model_mutated:false,p_model_status:'FROZEN',run_id:state.runId,fixture_id:state.freeze.fixture_id,freeze_receipt_sha256:state.expected,frozen_at:state.freeze.frozen_at,odds_api_support:'UNSUPPORTED_MARKET',message:'The Odds API rejected every requested NBL assists/rebounds market key',event:eventMeta,event_resolution_source:eventResolutionSource,markets_requested:requested,markets_used:[],markets_unsupported:marketsUnsupported,fallback_probed_individually:fallbackProbed,quota,market_records_received:0,evaluation:null};
  if(rows.length===0)return {market_data:true,p_model_mutated:false,p_model_status:'FROZEN',run_id:state.runId,fixture_id:state.freeze.fixture_id,freeze_receipt_sha256:state.expected,frozen_at:state.freeze.frozen_at,odds_api_support:'SUPPORTED_EMPTY',event:eventMeta,event_resolution_source:eventResolutionSource,markets_requested:requested,markets_used:marketsUsed,markets_unsupported:marketsUnsupported,fallback_probed_individually:fallbackProbed,quota,market_records_received:0,evaluation:null};

  need(rows.length<=MAX_MARKETS,`Odds API normalized market rows exceed ${MAX_MARKETS}; narrow market request`);
  const evaluation=await evaluate({run_id:state.runId,expected_freeze_receipt_sha256:state.expected,markets:rows},env);
  return {market_data:true,p_model_mutated:false,p_model_status:'FROZEN',run_id:state.runId,fixture_id:state.freeze.fixture_id,freeze_receipt_sha256:state.expected,frozen_at:state.freeze.frozen_at,odds_api_support:'SUPPORTED_WITH_ROWS',event:eventMeta,event_resolution_source:eventResolutionSource,markets_requested:requested,markets_used:marketsUsed,markets_unsupported:marketsUnsupported,fallback_probed_individually:fallbackProbed,quota,market_records_received:rows.length,evaluation};
}

export default {async fetch(request,env){try{if(request.method==='OPTIONS')return new Response(null,{status:204,headers:{'access-control-allow-origin':'*','access-control-allow-methods':'GET,POST,OPTIONS','access-control-allow-headers':'content-type'}});const url=new URL(request.url);if(request.method==='GET'&&url.pathname==='/health')return response({ok:true,service:'nbl-player-props-market-v1',version:'1.2.1',market_data:true,research_base:researchBase(env),supported_stats:['assists','rebounds'],supported_sources:['odds_api','screenshot','public_web'],odds_api_sport:ODDS_SPORT,odds_api_fetch_configured:Boolean(env?.ODDS_API_KEY),odds_api_markets:DEFAULT_ODDS_MARKETS});if(request.method==='POST'&&url.pathname==='/v1/evaluate'){const raw=await request.text();need(raw.length<=300_000,'Request too large');return response(await evaluate(JSON.parse(raw),env));}if(request.method==='POST'&&url.pathname==='/v1/fetch-odds-api'){const raw=await request.text();need(raw.length<=50_000,'Request too large');return response(await fetchAndEvaluateOddsApi(JSON.parse(raw),env));}return response({error:'Not found'},404);}catch(error){return response({market_data:true,p_model_mutated:false,error:error.message},422);}}};

export {normName,dedupeRawRows,eventOrientation};