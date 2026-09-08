/** Non-market NBA fixture discovery. Raw ESPN payload is sanitized before leaving this module. */
import { marketKeyHits } from './research_contract.js';
const need=(ok,msg)=>{if(!ok) throw new Error(msg);};
const ENDPOINT='https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard';
export function etLeagueDate(iso){const d=new Date(String(iso||''));need(Number.isFinite(d.getTime()),'fixture date invalid');const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(d);const x=Object.fromEntries(parts.map(p=>[p.type,p.value]));return `${x.year}-${x.month}-${x.day}`;}
const dayParam=date=>String(date).replaceAll('-','');
function team(c,label){const id=String(c?.team?.id||'').trim(),name=String(c?.team?.displayName||c?.team?.name||'').trim();need(/^\d{1,3}$/.test(id),`${label} ESPN team id invalid`);need(name,`${label} team name missing`);return {id,name,abbreviation:String(c?.team?.abbreviation||'')||null};}

export function sanitizeScoreboard(payload,{slateDateEt,nowMs=Date.now(),includeStarted=false}={}){
  need(/^\d{4}-\d{2}-\d{2}$/.test(String(slateDateEt||'')),'slate_date_et invalid');need(payload&&Array.isArray(payload.events),'ESPN scoreboard events missing');const fixtures=[];
  for(const event of payload.events){
    const gameId=String(event?.id||'');if(!/^\d{10}$/.test(gameId))continue;const start=String(event?.date||''),startMs=Date.parse(start);if(!Number.isFinite(startMs)||etLeagueDate(start)!==slateDateEt)continue;
    const competition=Array.isArray(event.competitions)?event.competitions[0]:null,competitors=competition?.competitors;if(!Array.isArray(competitors)||competitors.length!==2)continue;
    const homeRow=competitors.find(x=>x.homeAway==='home'),awayRow=competitors.find(x=>x.homeAway==='away');if(!homeRow||!awayRow)continue;
    const completed=Boolean(event?.status?.type?.completed),state=String(event?.status?.type?.state||'pre').toLowerCase();const started=startMs<=nowMs||state==='in';
    if(completed||(!includeStarted&&started))continue;
    const season=Number(event?.season?.year||competition?.season?.year);need(Number.isInteger(season)&&season>=2020&&season<=2100,`fixture ${gameId} season invalid`);
    fixtures.push({game_id:gameId,slate_date_et:slateDateEt,season,start_time_utc:new Date(startMs).toISOString(),home_team:team(homeRow,'home'),away_team:team(awayRow,'away'),status:started?'STARTED':'SCHEDULED',source:'ESPN_SCOREBOARD_NON_MARKET'});
  }
  fixtures.sort((a,b)=>Date.parse(a.start_time_utc)-Date.parse(b.start_time_utc)||a.game_id.localeCompare(b.game_id));need(marketKeyHits(fixtures).length===0,'sanitized fixture market boundary failed');return fixtures;
}

export async function listFixturesForEtDate(slateDateEt,{nowMs=Date.now(),fetchImpl=fetch}={}){
  need(/^\d{4}-\d{2}-\d{2}$/.test(String(slateDateEt||'')),'slate_date_et invalid');const url=`${ENDPOINT}?dates=${dayParam(slateDateEt)}&limit=100`;const res=await fetchImpl(url,{headers:{accept:'application/json','user-agent':'nba-player-props-research-v1/1.0'},signal:AbortSignal.timeout(15000)});need(res.ok,`ESPN fixture source unavailable ${res.status}`);const raw=await res.text();need(raw.length<=2_000_000,'ESPN fixture payload too large');const payload=JSON.parse(raw);return {market_data:false,source:{provider:'ESPN',url,checked_at:new Date(nowMs).toISOString()},fixtures:sanitizeScoreboard(payload,{slateDateEt,nowMs})};
}
