/** Current non-market roster identity source for early-season role research. */
import { marketKeyHits } from './research_contract.js';
const need=(ok,msg)=>{if(!ok) throw new Error(msg);};
const ROOT='https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams';

export function sanitizeRoster(payload,{teamId,expectedSeason=null}={}){
  const id=String(teamId||'');need(/^\d{1,3}$/.test(id),'team_id invalid');need(payload&&typeof payload==='object','roster payload invalid');
  const season=Number(payload?.season?.year);need(Number.isInteger(season)&&season>=2020&&season<=2100,'roster season invalid');if(expectedSeason!==null)need(season===Number(expectedSeason),'roster season mismatch');
  const raw=payload.athletes;need(Array.isArray(raw),'roster athletes missing');const athletes=[];
  for(const p of raw){const playerId=String(p?.id||'').trim(),name=String(p?.displayName||p?.fullName||'').trim();if(!/^\d+$/.test(playerId)||!name)continue;const injuries=Array.isArray(p.injuries)?p.injuries.map(x=>({status:String(x?.status||''),type:String(x?.type?.description||x?.type||''),detail:String(x?.details?.detail||x?.detail||''),date:x?.date?String(x.date):null})).filter(x=>x.status||x.type||x.detail):[];
    athletes.push({player_id:playerId,player_name:name,team_id:id,jersey:p?.jersey?String(p.jersey):null,position:String(p?.position?.abbreviation||p?.position?.name||'')||null,experience_years:Number.isFinite(Number(p?.experience?.years))?Number(p.experience.years):null,roster_status:String(p?.status?.type||p?.status?.name||'')||null,injuries});}
  athletes.sort((a,b)=>a.player_name.localeCompare(b.player_name)||a.player_id.localeCompare(b.player_id));need(athletes.length>=5,'sanitized roster unexpectedly small');need(new Set(athletes.map(x=>x.player_id)).size===athletes.length,'duplicate roster player id');need(marketKeyHits(athletes).length===0,'roster market boundary failed');return {market_data:false,team_id:id,season,athletes};
}

export async function fetchRoster(teamId,{expectedSeason=null,fetchImpl=fetch,nowMs=Date.now()}={}){
  const id=String(teamId||'');need(/^\d{1,3}$/.test(id),'team_id invalid');const url=`${ROOT}/${id}/roster`;const res=await fetchImpl(url,{headers:{accept:'application/json','user-agent':'nba-player-props-research-v1/1.0'},signal:AbortSignal.timeout(15000)});need(res.ok,`ESPN roster source unavailable ${res.status}`);const raw=await res.text();need(raw.length<=2_000_000,'ESPN roster payload too large');const roster=sanitizeRoster(JSON.parse(raw),{teamId:id,expectedSeason});return {...roster,source:{provider:'ESPN',url,checked_at:new Date(nowMs).toISOString()}};
}
