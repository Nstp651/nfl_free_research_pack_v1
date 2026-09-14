/** Non-market NBA fixture discovery. Raw ESPN payloads are sanitized before leaving this module. */
import { marketKeyHits, NBA_GAME_ID } from './research_contract.js';

const need=(ok,msg)=>{if(!ok) throw new Error(msg);};
const SCOREBOARD_ENDPOINT='https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard';
const CORE_ENDPOINT='https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba/events';
const CORE_HOST='sports.core.api.espn.com';
const MAX_BODY_BYTES=2_000_000;
// A full NBA slate has at most 15 games. Including the failed primary request,
// the fallback is bounded to 47 external subrequests (1 + 1 + 15 + 30).
const CORE_EVENT_CAP=15;
const REQUEST_HEADERS={accept:'application/json','user-agent':'nba-player-props-research-v1/1.0'};

export function etLeagueDate(iso){
  const d=new Date(String(iso||''));
  need(Number.isFinite(d.getTime()),'fixture date invalid');
  const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(d);
  const x=Object.fromEntries(parts.map(p=>[p.type,p.value]));
  return `${x.year}-${x.month}-${x.day}`;
}

const dayParam=date=>String(date).replaceAll('-','');

function team(c,label){
  const id=String(c?.team?.id||'').trim(),name=String(c?.team?.displayName||c?.team?.name||'').trim();
  need(/^\d{1,3}$/.test(id),`${label} ESPN team id invalid`);
  need(name,`${label} team name missing`);
  return {id,name,abbreviation:String(c?.team?.abbreviation||'')||null};
}

async function readJsonCapped(res,label){
  const declared=Number(res.headers?.get?.('content-length'));
  need(!Number.isFinite(declared)||declared<=MAX_BODY_BYTES,`${label} payload too large`);
  need(res.body&&typeof res.body.getReader==='function',`${label} response body missing`);
  const reader=res.body.getReader(),decoder=new TextDecoder();
  let bytes=0,raw='';
  while(true){
    const {done,value}=await reader.read();
    if(done)break;
    bytes+=value.byteLength;
    if(bytes>MAX_BODY_BYTES){await reader.cancel();throw new Error(`${label} payload too large`);}
    raw+=decoder.decode(value,{stream:true});
  }
  raw+=decoder.decode();
  try{return JSON.parse(raw);}catch{throw new Error(`${label} JSON invalid`);}
}

async function fetchJson(url,fetchImpl,label){
  const res=await fetchImpl(url,{headers:REQUEST_HEADERS,signal:AbortSignal.timeout(15000)});
  need(res.ok,`${label} unavailable ${res.status}`);
  return readJsonCapped(res,label);
}

function safeCoreRef(value,kind,pathnamePattern){
  let url;
  try{url=new URL(String(value?.$ref||value||''));}catch{throw new Error(`${kind} ESPN core ref invalid`);}
  need((url.protocol==='http:'||url.protocol==='https:')&&url.hostname===CORE_HOST&&pathnamePattern.test(url.pathname),`${kind} ESPN core ref invalid`);
  url.protocol='https:';
  return url.toString();
}

function coreSeason(event,gameId){
  const direct=Number(event?.season?.year);
  if(Number.isInteger(direct))return direct;
  let ref;
  try{ref=new URL(String(event?.season?.$ref||''));}catch{throw new Error(`fixture ${gameId} season invalid`);}
  need((ref.protocol==='http:'||ref.protocol==='https:')&&ref.hostname===CORE_HOST,'fixture season ESPN core ref invalid');
  const match=ref.pathname.match(/\/seasons\/(\d{4})(?:\/|$)/);
  const season=Number(match?.[1]);
  need(Number.isInteger(season),`fixture ${gameId} season invalid`);
  return season;
}

export function sanitizeScoreboard(payload,{slateDateEt,nowMs=Date.now(),includeStarted=false,source='ESPN_SCOREBOARD_NON_MARKET'}={}){
  need(/^\d{4}-\d{2}-\d{2}$/.test(String(slateDateEt||'')),'slate_date_et invalid');
  need(payload&&Array.isArray(payload.events),'ESPN scoreboard events missing');
  const fixtures=[];
  for(const event of payload.events){
    const gameId=String(event?.id||'');
    if(!NBA_GAME_ID.test(gameId))continue;
    const start=String(event?.date||''),startMs=Date.parse(start);
    if(!Number.isFinite(startMs)||etLeagueDate(start)!==slateDateEt)continue;
    const competition=Array.isArray(event.competitions)?event.competitions[0]:null,competitors=competition?.competitors;
    if(!Array.isArray(competitors)||competitors.length!==2)continue;
    const homeRow=competitors.find(x=>x.homeAway==='home'),awayRow=competitors.find(x=>x.homeAway==='away');
    if(!homeRow||!awayRow)continue;
    const completed=Boolean(event?.status?.type?.completed),state=String(event?.status?.type?.state||'pre').toLowerCase();
    const started=startMs<=nowMs||state==='in';
    if(completed||(!includeStarted&&started))continue;
    const season=Number(event?.season?.year||competition?.season?.year);
    need(Number.isInteger(season)&&season>=2020&&season<=2100,`fixture ${gameId} season invalid`);
    fixtures.push({game_id:gameId,slate_date_et:slateDateEt,season,start_time_utc:new Date(startMs).toISOString(),home_team:team(homeRow,'home'),away_team:team(awayRow,'away'),status:started?'STARTED':'SCHEDULED',source});
  }
  fixtures.sort((a,b)=>Date.parse(a.start_time_utc)-Date.parse(b.start_time_utc)||a.game_id.localeCompare(b.game_id));
  need(marketKeyHits(fixtures).length===0,'sanitized fixture market boundary failed');
  return fixtures;
}

async function listCoreFixtures(slateDateEt,{nowMs,fetchImpl}){
  const url=`${CORE_ENDPOINT}?dates=${dayParam(slateDateEt)}&limit=100`;
  const page=await fetchJson(url,fetchImpl,'ESPN core fixture list');
  need(Array.isArray(page?.items),'ESPN core fixture items missing');
  need(page.items.length<=CORE_EVENT_CAP,'ESPN core fixture list exceeds safe subrequest budget');
  const eventUrls=page.items.map(item=>safeCoreRef(item,'fixture event',/^\/v2\/sports\/basketball\/leagues\/nba\/events\/\d{9,10}$/));
  need(new Set(eventUrls).size===eventUrls.length,'ESPN core fixture refs duplicate');
  const events=await Promise.all(eventUrls.map(eventUrl=>fetchJson(eventUrl,fetchImpl,'ESPN core fixture event')));
  const teamUrls=[];
  for(const event of events){
    const rows=event?.competitions?.[0]?.competitors;
    need(Array.isArray(rows)&&rows.length===2,`fixture ${String(event?.id||'unknown')} competitors invalid`);
    for(const row of rows)teamUrls.push(safeCoreRef(row?.team,'fixture team',/^\/v2\/sports\/basketball\/leagues\/nba\/seasons\/\d{4}\/teams\/\d{1,3}$/));
  }
  const uniqueTeamUrls=[...new Set(teamUrls)];
  need(eventUrls.length+uniqueTeamUrls.length<=45,'ESPN core fallback subrequest budget exceeded');
  const teamDetails=await Promise.all(uniqueTeamUrls.map(teamUrl=>fetchJson(teamUrl,fetchImpl,'ESPN core fixture team')));
  const teams=new Map();
  uniqueTeamUrls.forEach((teamUrl,i)=>{
    const row=teamDetails[i],id=String(row?.id||'').trim(),displayName=String(row?.displayName||row?.name||'').trim();
    need(/^\d{1,3}$/.test(id)&&displayName,'ESPN core fixture team invalid');
    teams.set(teamUrl,{id,displayName,abbreviation:String(row?.abbreviation||'')||null});
  });
  const normalized={events:events.map(event=>{
    const gameId=String(event?.id||'');
    need(NBA_GAME_ID.test(gameId),'ESPN core fixture game_id invalid');
    const competition=event.competitions[0];
    return {id:gameId,date:String(event?.date||competition?.date||''),season:{year:coreSeason(event,gameId)},status:{type:{completed:false,state:'pre'}},competitions:[{competitors:competition.competitors.map(row=>({homeAway:row.homeAway,team:teams.get(safeCoreRef(row?.team,'fixture team',/^\/v2\/sports\/basketball\/leagues\/nba\/seasons\/\d{4}\/teams\/\d{1,3}$/))}))}]};
  })};
  return {market_data:false,source:{provider:'ESPN',url,checked_at:new Date(nowMs).toISOString(),fallback:'CORE_API'},fixtures:sanitizeScoreboard(normalized,{slateDateEt,nowMs,source:'ESPN_CORE_NON_MARKET'})};
}

export async function listFixturesForEtDate(slateDateEt,{nowMs=Date.now(),fetchImpl=fetch}={}){
  need(/^\d{4}-\d{2}-\d{2}$/.test(String(slateDateEt||'')),'slate_date_et invalid');
  const url=`${SCOREBOARD_ENDPOINT}?dates=${dayParam(slateDateEt)}&limit=100`;
  const res=await fetchImpl(url,{headers:REQUEST_HEADERS,signal:AbortSignal.timeout(15000)});
  if(!res.ok)return listCoreFixtures(slateDateEt,{nowMs,fetchImpl});
  const payload=await readJsonCapped(res,'ESPN fixture source');
  return {market_data:false,source:{provider:'ESPN',url,checked_at:new Date(nowMs).toISOString()},fixtures:sanitizeScoreboard(payload,{slateDateEt,nowMs})};
}
