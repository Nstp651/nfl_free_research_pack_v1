/** Persistent market-blind NBL matchup run and atomic P_model freeze. */
import {computeFreeze,marketKeyHits,requireThat,sha256Json,validateResearchContext} from './freeze_core.js';

const GH_API='https://api.github.com/repos/Nstp651/nfl_free_research_pack_v1/commits/main';
const GH_RAW='https://raw.githubusercontent.com/Nstp651/nfl_free_research_pack_v1/';
const ROSETTA='https://prod.rosetta.nbl.com.au';
const MAX_AGE_MS=48*3600_000;
export const response=(x,status=200)=>new Response(JSON.stringify(x),{status,headers:{'content-type':'application/json','cache-control':'no-store'}});
const exactKeys=(obj,allowed)=>{requireThat(obj&&typeof obj==='object'&&!Array.isArray(obj),'JSON object required');for(const k of Object.keys(obj))requireThat(allowed.includes(k),`Unexpected field ${k}`);};
const norm=x=>String(x||'').toLowerCase().replace(/[^a-z0-9]+/g,'');
const playerStorageKey=p=>String(p.player_id||'').trim()?`id:${String(p.player_id).trim()}`:`name:${norm(p.player_name)}`;

function rawUrl(commit,path){return `${GH_RAW}${commit}/nbl_player_props_v1/data/${path}`;}
function allowedUrl(url){
  return url===GH_API ||
    /^https:\/\/raw\.githubusercontent\.com\/Nstp651\/nfl_free_research_pack_v1\/[a-f0-9]{40}\/nbl_player_props_v1\/data\/[A-Za-z0-9_./-]+\.json$/.test(url) ||
    /^https:\/\/prod\.rosetta\.nbl\.com\.au\/get\/nbl\/matches\/in\/season\/\d{4}\/all$/.test(url) ||
    /^https:\/\/prod\.rosetta\.nbl\.com\.au\/get\/nbl\/players\/for\/team\/[A-Za-z0-9-]+\/in\/season\/\d{4}$/.test(url);
}
async function readJson(url,{maxBytes=4_000_000}={}){
  requireThat(allowedUrl(url),'Source URL not allowed');
  const rosetta=url.startsWith(ROSETTA);
  const headers=rosetta?{'accept':'application/json','origin':'https://nbl.com.au','referer':'https://nbl.com.au/','user-agent':'nbl-props-freeze/1.0'}:{'accept':'application/json','user-agent':'nbl-props-freeze/1.0'};
  const res=await fetch(url,{headers,signal:AbortSignal.timeout(15_000)});requireThat(res.ok,`Source unavailable ${res.status}`);
  const raw=await res.text();requireThat(raw.length<=maxBytes,'Source response too large');
  const payload=JSON.parse(raw);return payload;
}
function envelopeData(payload,label){requireThat(payload&&typeof payload==='object'&&Array.isArray(payload.data),`${label} malformed`);return payload.data;}
function teamSafe(t){if(!t||typeof t!=='object')return null;return {id:String(t.id||t.external_id||''),name:String(t.name||''),short_name:String(t.short_name||t.team_code||'')};}
function fixtureSafe(row){
  requireThat(row&&typeof row==='object','fixture row malformed');
  return {id:String(row.id||row.external_id||''),start_time:String(row.start_time_datetime||row.start_time||''),round:row.round??row.override_round??null,status:String(row.match_status||row.status||''),home_team:teamSafe(row.home_team),away_team:teamSafe(row.away_team),venue:row.venue&&typeof row.venue==='object'?{id:String(row.venue.id||''),name:String(row.venue.name||''),city:String(row.venue.city||'')}:null};
}
function playerSafe(row){
  const p=row?.player&&typeof row.player==='object'?row.player:row;
  return {id:String(p?.id||p?.external_id||row?.id||''),first_name:String(p?.first_name||p?.firstName||''),family_name:String(p?.family_name||p?.last_name||p?.surname||''),display_name:String(p?.name||p?.display_name||p?.scoreboard_name||'').trim(),position:String(p?.position||p?.playing_position||'')};
}
function playerName(p){return p.display_name||`${p.first_name} ${p.family_name}`.trim();}
export async function listFixtures(seasonStart){
  requireThat(Number.isInteger(seasonStart)&&seasonStart>=2010&&seasonStart<=2100,'season_start invalid');
  const rows=envelopeData(await readJson(`${ROSETTA}/get/nbl/matches/in/season/${seasonStart}/all`),'schedule');
  const fixtures=rows.map(fixtureSafe).filter(f=>f.id&&f.home_team?.name&&f.away_team?.name&&Number.isFinite(Date.parse(f.start_time)));
  requireThat(marketKeyHits(fixtures).length===0,'Sanitized fixture market-boundary failure');return fixtures;
}
async function loadAssets(){
  const head=await readJson(GH_API,{maxBytes:100_000});requireThat(/^[a-f0-9]{40}$/.test(String(head.sha||'')),'Invalid GitHub source commit');
  const commit=head.sha,manifest=await readJson(rawUrl(commit,'manifest.json'),{maxBytes:200_000});
  requireThat(manifest?.schema_version==='nbl_runtime_assets_v1'&&manifest.market_data===false,'NBL asset manifest invalid');
  requireThat(marketKeyHits(manifest).length===0,'Asset manifest market-boundary failure');
  requireThat(/^[a-f0-9]{16,64}$/.test(String(manifest.asset_revision||'')),'asset_revision invalid');
  const entries=manifest.qbase||{},priorMeta=manifest.prior_snapshot||{};
  for(const stat of ['assists','rebounds']) requireThat(entries[stat]?.path&&/^[a-f0-9]{64}$/.test(String(entries[stat].canonical_sha256||'')),`manifest ${stat} QBASE invalid`);
  requireThat(priorMeta.path&&/^[a-f0-9]{64}$/.test(String(priorMeta.canonical_sha256||'')),'manifest prior snapshot invalid');
  const [assists,rebounds,prior]=await Promise.all([
    readJson(rawUrl(commit,entries.assists.path)),readJson(rawUrl(commit,entries.rebounds.path)),readJson(rawUrl(commit,priorMeta.path),{maxBytes:4_000_000})
  ]);
  requireThat(await sha256Json(assists)===entries.assists.canonical_sha256,'assists QBASE hash mismatch');
  requireThat(await sha256Json(rebounds)===entries.rebounds.canonical_sha256,'rebounds QBASE hash mismatch');
  requireThat(await sha256Json(prior)===priorMeta.canonical_sha256,'prior snapshot hash mismatch');
  requireThat(prior.market_data===false&&String(prior.snapshot_revision)===String(priorMeta.snapshot_revision),'prior snapshot identity mismatch');
  return {source_commit:commit,manifest,qbase:{assists,rebounds},prior};
}
async function roster(teamId,seasonStart){
  requireThat(teamId,'team id missing');const rows=envelopeData(await readJson(`${ROSETTA}/get/nbl/players/for/team/${teamId}/in/season/${seasonStart}`),'roster');
  const out=rows.map(playerSafe).map(p=>({...p,display_name:playerName(p)})).filter(p=>p.id||p.display_name);requireThat(marketKeyHits(out).length===0,'Sanitized roster market-boundary failure');return out;
}
function compactPrior(prior,playerNameValue){const p=prior.players?.[norm(playerNameValue)];return p?{player_key:p.player_key,last_team:p.last_team,last_season:p.last_season,last_match_time:p.last_match_time,features:p.features}:null;}
async function researchSeed(meta){
  const {fixture,season_start,source_commit,manifest}=meta.lock;
  const prior=await readJson(rawUrl(source_commit,manifest.prior_snapshot.path),{maxBytes:4_000_000});
  requireThat(await sha256Json(prior)===manifest.prior_snapshot.canonical_sha256,'Pinned prior hash mismatch');
  const [home,away]=await Promise.all([roster(fixture.home_team.id,season_start),roster(fixture.away_team.id,season_start)]);
  const decorate=(rows,team)=>rows.map(p=>({...p,team,prior_nbl:compactPrior(prior,p.display_name),nbl_history_status:compactPrior(prior,p.display_name)?'NBL_HISTORY_AVAILABLE':'PRIOR_COMP_TRANSLATION_REQUIRED'}));
  return {market_data:false,lock:meta.lock,fixture,home_roster:decorate(home,fixture.home_team.name),away_roster:decorate(away,fixture.away_team.name),snapshot_revision:prior.snapshot_revision,research_note:'Structured data is a prior only. Current availability, projected minutes, role, lineup, imports, coaching and late news still require current pre-market research.'};
}
function compactFrozen(frozen){
  return {market_data:false,status:'FROZEN',fixture_id:frozen.fixture_id,run_mode:frozen.run_mode,requested_heads:frozen.requested_heads,pack_revision:frozen.pack_revision,research_context_sha256:frozen.research_context_sha256,qbase_sha256:frozen.qbase_sha256,frozen_at:frozen.frozen_at,freeze_receipt_sha256:frozen.freeze_receipt_sha256,audits:frozen.audits,players:frozen.players.map(p=>({player_key:playerStorageKey(p),player_id:p.player_id,player_name:p.player_name,team:p.team,availability_status:p.availability_status,projected_minutes:p.projected_minutes,heads:Object.fromEntries(Object.entries(p.heads).map(([s,h])=>[s,{final_mean:h.final_mean,dispersion_alpha:h.dispersion_alpha,dispersion_source:h.dispersion_source,confidence:h.confidence,fragility:h.fragility}]))}))};
}

export class NblMatchRun{
  constructor(state,env){this.state=state;this.storage=state.storage;this.env=env;}
  async fetch(request){return this.state.blockConcurrencyWhile(async()=>{try{return await this.handle(request);}catch(e){const m=await this.storage.get('meta');return response({market_data:false,p_model_status:m?.status==='FROZEN'?'FROZEN':'NOT FROZEN',error:e.message},422);}});}
  async handle(request){
    const url=new URL(request.url),parts=url.pathname.split('/').filter(Boolean),tail=parts.slice(3);let meta=await this.storage.get('meta');
    if(request.method==='POST'&&tail.length===0){
      requireThat(!meta,'Run already initialized');const input=await request.json();exactKeys(input,['fixture_id','season_start','run_mode']);
      const season=Number(input.season_start);requireThat(Number.isInteger(season),'season_start invalid');const mode=String(input.run_mode||'').toUpperCase();requireThat(['BOTH','ASSISTS_ONLY','REBOUNDS_ONLY'].includes(mode),'run_mode invalid');
      const [fixtures,assets]=await Promise.all([listFixtures(season),loadAssets()]);const found=fixtures.filter(f=>f.id===String(input.fixture_id));requireThat(found.length===1,'Exact fixture_id not found');const fixture=found[0],start=Date.parse(fixture.start_time),now=Date.now();requireThat(Number.isFinite(start)&&start>now,'Fixture already started or invalid');
      const lock={fixture_id:fixture.id,fixture,season_start:season,run_mode:mode,source_commit:assets.source_commit,asset_revision:assets.manifest.asset_revision,pack_revision:assets.manifest.asset_revision,snapshot_revision:assets.manifest.prior_snapshot.snapshot_revision,qbase_revision:{assists:assets.manifest.qbase.assists.canonical_sha256,rebounds:assets.manifest.qbase.rebounds.canonical_sha256},eligibility_at:new Date(now).toISOString()};
      await this.storage.transaction(async tx=>{await tx.put('q:assists',assets.qbase.assists);await tx.put('q:rebounds',assets.qbase.rebounds);await tx.put('meta',{status:'RESEARCH_PENDING',created_at:now,lock});});meta=await this.storage.get('meta');
    }
    requireThat(meta,'Unknown run');
    if(request.method==='GET'&&tail[0]==='research'&&tail.length===1){requireThat(meta.status!=='FROZEN','Run already frozen');return response(await researchSeed(meta));}
    if(request.method==='POST'&&tail[0]==='research'&&tail.length===1){requireThat(meta.status!=='FROZEN','Frozen run immutable');const c=await request.json();validateResearchContext(c);requireThat(c.fixture_id===meta.lock.fixture_id&&c.pack_revision===meta.lock.pack_revision&&String(c.run_mode).toUpperCase()===meta.lock.run_mode,'Research context identity mismatch');const teams=new Set([meta.lock.fixture.home_team.name,meta.lock.fixture.away_team.name]);for(const p of c.players)requireThat(teams.has(p.team),`Research player team outside locked fixture: ${p.team}`);requireThat(JSON.stringify(c).length<180_000,'Research context too large');await this.storage.put('research',c);await this.storage.put('meta',{...meta,status:'RESEARCH_COMPLETE'});return response({market_data:false,status:'RESEARCH_COMPLETE',fixture_id:meta.lock.fixture_id,research_context_sha256:await sha256Json(c)});}
    if(request.method==='POST'&&tail[0]==='compute'&&tail.length===1){
      if(meta.status==='FROZEN')return response(meta.receipt);requireThat(Date.now()-meta.created_at<=MAX_AGE_MS,'Run expired; start a new run');const research=await this.storage.get('research');requireThat(research,'Research context incomplete');const body=await request.json();exactKeys(body,['projections']);
      const frozen=await computeFreeze(research,{assists:await this.storage.get('q:assists'),rebounds:await this.storage.get('q:rebounds')},body.projections,new Date().toISOString());const receipt=compactFrozen(frozen);
      await this.storage.transaction(async tx=>{for(const p of frozen.players)await tx.put('f:'+playerStorageKey(p),p);await tx.put('meta',{...meta,status:'FROZEN',receipt});});return response(receipt);
    }
    if(request.method==='GET'&&tail[0]==='players'&&tail.length>=2){requireThat(meta.status==='FROZEN','Run not frozen');const key=decodeURIComponent(tail.slice(1).join('/')),p=await this.storage.get('f:'+key);requireThat(p,'Frozen player not found');return response({market_data:false,freeze_receipt_sha256:meta.receipt.freeze_receipt_sha256,frozen_at:meta.receipt.frozen_at,player:p});}
    if(request.method==='GET'&&tail.length===0)return response({market_data:false,status:meta.status,lock:meta.lock,research_complete:Boolean(await this.storage.get('research')),freeze:meta.receipt||null});
    throw new Error('Unknown run operation');
  }
}

export async function routeMatchRuns(request,env){
  const url=new URL(request.url);if(!url.pathname.startsWith('/v1/match-runs'))return null;if(!env.MATCH_RUNS)return response({market_data:false,error:'MATCH_RUNS binding unavailable'},503);
  const match=url.pathname.match(/^\/v1\/match-runs(?:\/([a-f0-9]{64})(?:\/(research|compute|players)(?:\/(.+))?)?)?$/);if(!match)return response({market_data:false,error:'Not found'},404);
  if(!match[1]&&request.method!=='POST')return response({market_data:false,error:'POST required'},405);
  const id=match[1]?env.MATCH_RUNS.idFromString(match[1]):env.MATCH_RUNS.newUniqueId();if(!match[1])url.pathname+='/'+id.toString();const raw=await request.text();if(raw.length>400_000)return response({market_data:false,error:'Request too large'},413);
  const forwarded=new Request(url,{method:request.method,headers:request.headers,...(request.method==='GET'?{}:{body:raw})});const res=await env.MATCH_RUNS.get(id).fetch(forwarded);const data=await res.json();return response({run_id:id.toString(),...data},res.status);
}
