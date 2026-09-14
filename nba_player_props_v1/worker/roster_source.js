/** Current non-market roster identity source for early-season role research. */
import { marketKeyHits } from './research_contract.js';
const need=(ok,msg)=>{if(!ok) throw new Error(msg);};
const SITE_ROOT='https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams';
const CORE_ROOT='https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba';
const CORE_HOST='sports.core.api.espn.com';
const MAX_BODY_BYTES=2_000_000;
const REQUEST_HEADERS={accept:'application/json','user-agent':'nba-player-props-research-v1/1.0'};

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

function safeCoreAthleteRef(value,{season}){
  let url;
  try{url=new URL(String(value?.$ref||value||''));}catch{throw new Error('ESPN core roster athlete ref invalid');}
  const pattern=new RegExp(`^/v2/sports/basketball/leagues/nba/seasons/${Number(season)}/athletes/\\d+$`);
  need((url.protocol==='http:'||url.protocol==='https:')&&url.hostname===CORE_HOST&&pattern.test(url.pathname),'ESPN core roster athlete ref invalid');
  url.protocol='https:';
  return url.toString();
}

function coreAthleteTeamId(player,{season}){
  let url;
  try{url=new URL(String(player?.team?.$ref||''));}catch{throw new Error('ESPN core roster athlete team ref invalid');}
  const match=url.pathname.match(new RegExp(`^/v2/sports/basketball/leagues/nba/seasons/${Number(season)}/teams/(\\d{1,3})$`));
  need((url.protocol==='http:'||url.protocol==='https:')&&url.hostname===CORE_HOST&&match,'ESPN core roster athlete team ref invalid');
  return match[1];
}

async function fetchCoreRoster(teamId,{expectedSeason,fetchImpl,nowMs}){
  need(Number.isInteger(Number(expectedSeason)),'roster season required for ESPN core fallback');
  const season=Number(expectedSeason),url=`${CORE_ROOT}/seasons/${season}/teams/${teamId}/athletes?limit=25&lang=en&region=us`;
  const indexRes=await fetchImpl(url,{headers:REQUEST_HEADERS,signal:AbortSignal.timeout(15000)});
  need(indexRes.ok,`ESPN core roster source unavailable ${indexRes.status}`);
  const index=await readJsonCapped(indexRes,'ESPN core roster index');
  need(Array.isArray(index?.items)&&index.items.length>=5&&index.items.length<=25,'ESPN core roster index invalid');
  need(Number(index.pageCount)===1,'ESPN core roster index unexpectedly paginated');
  const refs=index.items.map(item=>safeCoreAthleteRef(item,{season}));
  need(new Set(refs).size===refs.length,'ESPN core roster athlete refs duplicate');
  const athletes=[];
  for(let i=0;i<refs.length;i+=3){
    const rows=await Promise.all(refs.slice(i,i+3).map(async athleteUrl=>{
      const res=await fetchImpl(athleteUrl,{headers:REQUEST_HEADERS,signal:AbortSignal.timeout(15000)});
      need(res.ok,`ESPN core roster athlete unavailable ${res.status}`);
      return readJsonCapped(res,'ESPN core roster athlete');
    }));
    athletes.push(...rows);
  }
  for(const player of athletes)need(coreAthleteTeamId(player,{season})===String(teamId),'ESPN core roster athlete team mismatch');
  const roster=sanitizeRoster({season:{year:season},athletes},{teamId,expectedSeason:season});
  return {...roster,source:{provider:'ESPN',url,checked_at:new Date(nowMs).toISOString(),fallback:'CORE_API'}};
}

export function sanitizeRoster(payload,{teamId,expectedSeason=null}={}){
  const id=String(teamId||'');need(/^\d{1,3}$/.test(id),'team_id invalid');need(payload&&typeof payload==='object','roster payload invalid');
  const season=Number(payload?.season?.year);need(Number.isInteger(season)&&season>=2020&&season<=2100,'roster season invalid');if(expectedSeason!==null)need(season===Number(expectedSeason),'roster season mismatch');
  const raw=payload.athletes;need(Array.isArray(raw),'roster athletes missing');const athletes=[];
  for(const p of raw){const playerId=String(p?.id||'').trim(),name=String(p?.displayName||p?.fullName||'').trim();if(!/^\d+$/.test(playerId)||!name)continue;const injuries=Array.isArray(p.injuries)?p.injuries.map(x=>({status:String(x?.status||''),type:String(x?.type?.description||x?.type||''),detail:String(x?.details?.detail||x?.detail||''),date:x?.date?String(x.date):null})).filter(x=>x.status||x.type||x.detail):[];
    athletes.push({player_id:playerId,player_name:name,team_id:id,jersey:p?.jersey?String(p.jersey):null,position:String(p?.position?.abbreviation||p?.position?.name||'')||null,experience_years:Number.isFinite(Number(p?.experience?.years))?Number(p.experience.years):null,roster_status:String(p?.status?.type||p?.status?.name||'')||null,injuries});}
  athletes.sort((a,b)=>a.player_name.localeCompare(b.player_name)||a.player_id.localeCompare(b.player_id));need(athletes.length>=5,'sanitized roster unexpectedly small');need(new Set(athletes.map(x=>x.player_id)).size===athletes.length,'duplicate roster player id');need(marketKeyHits(athletes).length===0,'roster market boundary failed');return {market_data:false,team_id:id,season,athletes};
}

export async function fetchRoster(teamId,{expectedSeason=null,fetchImpl=fetch,nowMs=Date.now()}={}){
  const id=String(teamId||'');need(/^\d{1,3}$/.test(id),'team_id invalid');const url=`${SITE_ROOT}/${id}/roster`;const res=await fetchImpl(url,{headers:REQUEST_HEADERS,signal:AbortSignal.timeout(15000)});if(!res.ok){await res.body?.cancel();return fetchCoreRoster(id,{expectedSeason,fetchImpl,nowMs});}const payload=await readJsonCapped(res,'ESPN roster source');const roster=sanitizeRoster(payload,{teamId:id,expectedSeason});return {...roster,source:{provider:'ESPN',url,checked_at:new Date(nowMs).toISOString()}};
}
