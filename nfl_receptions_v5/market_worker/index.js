/** NFL receptions market adapter — Betting Platform V1.
 * POST-FREEZE ONLY. It verifies the authoritative control-plane run through a
 * Cloudflare Service Binding before making any Odds API request. */
const SPORT = 'americanfootball_nfl';
const MARKETS = ['player_receptions', 'player_receptions_alternate'];
const ODDS_HOST = 'https://api.the-odds-api.com';
const CONTROL_INTERNAL_ORIGIN = 'https://nfl-receptions-control.internal';
const VERSION = '1.0.0';
const MAX_UPSTREAM_CHARS = 8_000_000;
const MAX_RESPONSE_CHARS = 90000;
const KICKOFF_TOLERANCE_MS = 5 * 60 * 1000;

const TEAM_NAMES = Object.freeze({
  ARI:'Arizona Cardinals',ATL:'Atlanta Falcons',BAL:'Baltimore Ravens',BUF:'Buffalo Bills',CAR:'Carolina Panthers',CHI:'Chicago Bears',CIN:'Cincinnati Bengals',CLE:'Cleveland Browns',DAL:'Dallas Cowboys',DEN:'Denver Broncos',DET:'Detroit Lions',GB:'Green Bay Packers',HOU:'Houston Texans',IND:'Indianapolis Colts',JAX:'Jacksonville Jaguars',KC:'Kansas City Chiefs',LV:'Las Vegas Raiders',LAC:'Los Angeles Chargers',LA:'Los Angeles Rams',MIA:'Miami Dolphins',MIN:'Minnesota Vikings',NE:'New England Patriots',NO:'New Orleans Saints',NYG:'New York Giants',NYJ:'New York Jets',PHI:'Philadelphia Eagles',PIT:'Pittsburgh Steelers',SEA:'Seattle Seahawks',SF:'San Francisco 49ers',TB:'Tampa Bay Buccaneers',TEN:'Tennessee Titans',WAS:'Washington Commanders'
});

function reply(value,status=200){return new Response(JSON.stringify(value),{status,headers:{'content-type':'application/json; charset=utf-8','cache-control':'no-store','access-control-allow-origin':'*'}});}
function fail(status,message,details={}){const e=new Error(message);e.status=status;Object.assign(e,details);throw e;}
function requireThat(x,m){if(!x) fail(422,m);}
function safeRunId(v){if(!/^[a-f0-9]{64}$/.test(v||'')) fail(400,'Invalid run_id');return v;}
async function readJson(res,label){const text=await res.text();if(text.length>MAX_UPSTREAM_CHARS) fail(502,`${label} response exceeds size limit`);let value;try{value=JSON.parse(text);}catch{fail(502,`${label} returned invalid JSON`);}return {value,text};}
function exactThreshold(point){if(typeof point!=='number'||!Number.isFinite(point)||point<0) return null;const k=Math.round(point+0.5);return Math.abs(point-(k-0.5))<=1e-9&&k>=1&&k<=20?k:null;}

async function controlFetch(env,path){
  if(!env.CONTROL_SERVICE||typeof env.CONTROL_SERVICE.fetch!=='function') fail(503,'CONTROL_SERVICE is not configured');
  return env.CONTROL_SERVICE.fetch(new Request(`${CONTROL_INTERNAL_ORIGIN}${path}`,{
    headers:{'user-agent':`nfl-receptions-market/${VERSION}`},
  }));
}

export async function verifyFrozenRun(env,runId){
  const res=await controlFetch(env,`/v1/runs/${runId}`);
  const {value}=await readJson(res,'Control plane');
  if(!res.ok) fail(res.status===422?422:503,`Control plane unavailable (${res.status})`);
  requireThat(value.run_id===runId,'Control-plane run identity mismatch');
  requireThat(value.status==='FROZEN'&&value.p_model_status==='FROZEN','Market access denied — P_model is not frozen');
  requireThat(value.freeze&&/^[a-f0-9]{64}$/.test(value.freeze.freeze_receipt_sha256||''),'Frozen run receipt missing');
  const lock=value.lock||{};
  requireThat(TEAM_NAMES[lock.away_team]&&TEAM_NAMES[lock.home_team],'Unsupported locked NFL team code');
  requireThat(Number.isFinite(Date.parse(lock.validated_kickoff_utc)),'Frozen run kickoff missing');
  return value;
}

async function fetchFrozenArtifact(env,runId,status){
  const res=await controlFetch(env,`/v1/runs/${runId}/freeze`);
  const {value}=await readJson(res,'Frozen artifact');
  if(!res.ok) fail(res.status===422?422:503,`Frozen artifact unavailable (${res.status})`);
  requireThat(value.run_id===runId&&value.p_model_status==='FROZEN','Frozen artifact identity/status mismatch');
  requireThat(value.freeze?.freeze_receipt_sha256===status.freeze.freeze_receipt_sha256,'Frozen artifact receipt does not match control-plane status');
  requireThat(Array.isArray(value.freeze?.players)&&value.freeze.players.length>0,'Frozen artifact has no players');
  return value.freeze;
}

async function fetchEvents(env){
  if(!env.ODDS_API_KEY) fail(503,'ODDS_API_KEY is not configured');
  const q=new URLSearchParams({apiKey:env.ODDS_API_KEY,dateFormat:'iso'});
  const res=await fetch(`${ODDS_HOST}/v4/sports/${SPORT}/events?${q}`,{headers:{'user-agent':`nfl-receptions-market/${VERSION}`},signal:AbortSignal.timeout(12000),cf:{cacheTtl:300,cacheEverything:true}});
  const {value}=await readJson(res,'Odds events');
  if(!res.ok) fail(res.status===429?429:502,`Odds events unavailable (${res.status})`);
  if(!Array.isArray(value)) fail(502,'Odds events returned invalid payload');
  return value;
}

export function resolveEvent(events,lock){
  const away=TEAM_NAMES[lock.away_team],home=TEAM_NAMES[lock.home_team],kick=Date.parse(lock.validated_kickoff_utc);
  const matches=events.filter(e=>e&&e.sport_key===SPORT&&e.away_team===away&&e.home_team===home&&Number.isFinite(Date.parse(e.commence_time))&&Math.abs(Date.parse(e.commence_time)-kick)<=KICKOFF_TOLERANCE_MS);
  requireThat(matches.length===1,`Expected exactly one Odds API event for locked fixture; found ${matches.length}`);
  requireThat(/^[a-f0-9]{32}$/.test(String(matches[0].id||'')),'Invalid Odds API event id');
  return matches[0];
}

function normalizeBookmakers(raw,event){
  requireThat(raw&&raw.sport_key===SPORT&&String(raw.id)===String(event.id),'Odds event response identity mismatch');
  requireThat(raw.home_team===event.home_team&&raw.away_team===event.away_team,'Odds event teams mismatch');
  requireThat(Math.abs(Date.parse(raw.commence_time)-Date.parse(event.commence_time))<=KICKOFF_TOLERANCE_MS,'Odds event kickoff mismatch');
  const selections=[];
  for(const book of Array.isArray(raw.bookmakers)?raw.bookmakers:[]){
    for(const market of Array.isArray(book.markets)?book.markets:[]){
      if(!MARKETS.includes(market?.key)) continue;
      for(const o of Array.isArray(market.outcomes)?market.outcomes:[]){
        if(o?.name!=='Over'||typeof o?.description!=='string'||typeof o?.price!=='number'||!Number.isFinite(o.price)||o.price<=1) continue;
        const threshold=exactThreshold(o.point); if(threshold===null) continue;
        selections.push({bookmaker_key:String(book.key||''),bookmaker:String(book.title||book.key||''),last_update:market.last_update||book.last_update||null,market_key:market.key,player_name:o.description,side:'Over',line:o.point,reception_threshold:threshold,price:o.price});
      }
    }
  }
  selections.sort((a,b)=>a.player_name.localeCompare(b.player_name)||a.reception_threshold-b.reception_threshold||b.price-a.price||a.bookmaker_key.localeCompare(b.bookmaker_key));
  return selections;
}

function canonicalPlayerName(value){return String(value||'').normalize('NFKD').toLowerCase().replace(/[^a-z0-9]+/g,'');}
function rankWeight(value,map){return map[value]??99;}
function integrateFrozenMarket(freeze,selections){
  const byName=new Map();
  for(const p of freeze.players){const key=canonicalPlayerName(p.player_name);if(!key) continue;const arr=byName.get(key)||[];arr.push(p);byName.set(key,arr);}
  const mapped=[];
  for(const s of selections){const candidates=byName.get(canonicalPlayerName(s.player_name))||[];if(candidates.length!==1) continue;const p=candidates[0];const probability=p.ladder?.[String(s.reception_threshold)];if(typeof probability!=='number'||!Number.isFinite(probability)||probability<=0||probability>1) continue;const implied=1/s.price;const roi=probability*s.price-1;mapped.push({...s,player_id:p.player_id,player_name:p.player_name,p_model:probability,implied_probability:implied,price_edge:probability-implied,fair_price:1/probability,expected_roi:roi,confidence:p.confidence,fragility:p.fragility});}
  const best=new Map();
  for(const row of mapped){const key=`${row.player_id}|${row.reception_threshold}`;const prev=best.get(key);if(!prev||row.price>prev.price||(row.price===prev.price&&String(row.last_update||'')>String(prev.last_update||''))||(row.price===prev.price&&String(row.last_update||'')===String(prev.last_update||'')&&row.bookmaker_key<prev.bookmaker_key)) best.set(key,row);}
  const all=[...best.values()].sort((a,b)=>a.player_name.localeCompare(b.player_name)||a.reception_threshold-b.reception_threshold);
  const positive=all.filter(x=>x.expected_roi>0).sort((a,b)=>b.expected_roi-a.expected_roi||b.price_edge-a.price_edge||rankWeight(a.fragility,{LOW:0,MODERATE:1,HIGH:2})-rankWeight(b.fragility,{LOW:0,MODERATE:1,HIGH:2})||rankWeight(a.confidence,{HIGH:0,MEDIUM:1,LOW:2})-rankWeight(b.confidence,{HIGH:0,MEDIUM:1,LOW:2})||a.player_name.localeCompare(b.player_name)||a.reception_threshold-b.reception_threshold);
  return {all_mapped:all,positive_edge_ranked:positive};
}

async function fetchProps(env,event){
  const q=new URLSearchParams({apiKey:env.ODDS_API_KEY,regions:'au',markets:MARKETS.join(','),oddsFormat:'decimal',dateFormat:'iso'});
  const res=await fetch(`${ODDS_HOST}/v4/sports/${SPORT}/events/${event.id}/odds?${q}`,{headers:{'user-agent':`nfl-receptions-market/${VERSION}`},signal:AbortSignal.timeout(12000),cf:{cacheTtl:35,cacheEverything:true}});
  const {value}=await readJson(res,'Odds props');
  if(!res.ok) fail(res.status===429?429:502,`Odds props unavailable (${res.status})`);
  return {raw:value,quota:{requests_remaining:res.headers.get('x-requests-remaining'),requests_used:res.headers.get('x-requests-used'),requests_last:res.headers.get('x-requests-last')}};
}

export default {async fetch(request,env={}){
  if(request.method!=='GET') return reply({error:'GET requests only'},405);
  try{
    const url=new URL(request.url);
    if(url.pathname==='/health') return reply({ok:Boolean(env.CONTROL_SERVICE&&env.ODDS_API_KEY),service:'NFL_RECEPTIONS_MARKET_GATEWAY',version:VERSION,market_group:'nfl-receptions',sport_key:SPORT,region:'au',markets:MARKETS,configured:Boolean(env.CONTROL_SERVICE&&env.ODDS_API_KEY),control_transport:'SERVICE_BINDING',note:'Health performs no control-plane market call and no Odds API request.'},env.CONTROL_SERVICE&&env.ODDS_API_KEY?200:503);
    if(url.pathname!=='/v1/receptions') return reply({error:'Not found'},404);
    const runId=safeRunId(url.searchParams.get('run_id'));
    // Critical ordering: authoritative freeze verification happens before ANY Odds API call.
    const run=await verifyFrozenRun(env,runId);
    const freeze=await fetchFrozenArtifact(env,runId,run);
    // Only after both status and immutable artifact receipts are verified may market data be touched.
    const events=await fetchEvents(env);
    const event=resolveEvent(events,run.lock);
    const props=await fetchProps(env,event);
    const selections=normalizeBookmakers(props.raw,event);
    const integrated=integrateFrozenMarket(freeze,selections);
    const result={service:'NFL_RECEPTIONS_MARKET_GATEWAY',version:VERSION,market_group:'nfl-receptions',region:'au',run_id:runId,freeze_receipt_sha256:run.freeze.freeze_receipt_sha256,frozen_at:run.freeze.frozen_at,event:{event_id:event.id,away_team:event.away_team,home_team:event.home_team,commence_time:event.commence_time},retrieved_at:new Date().toISOString(),quota:props.quota,raw_selection_count:selections.length,mapped_selection_count:integrated.all_mapped.length,positive_edge_count:integrated.positive_edge_ranked.length,best_prices:integrated.all_mapped,positive_edge_ranked:integrated.positive_edge_ranked};
    if(JSON.stringify(result).length>=MAX_RESPONSE_CHARS) fail(502,'Market response exceeds Action response limit');
    return reply(result);
  }catch(e){return reply({error:e.status?e.message:(e?.name==='TimeoutError'||e?.name==='AbortError'?'Upstream request timed out':'Market service temporarily unavailable')},e.status||502);}
}};
