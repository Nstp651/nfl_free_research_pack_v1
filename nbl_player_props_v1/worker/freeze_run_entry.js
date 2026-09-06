import {NblMatchRun as BaseNblMatchRun,listFixtures,response,routeMatchRuns} from './freeze_run.js';
import {marketKeyHits,requireThat,sha256Json} from './freeze_core.js';

const GH_RAW='https://raw.githubusercontent.com/Nstp651/nfl_free_research_pack_v1/';
const ROSETTA='https://prod.rosetta.nbl.com.au';
const norm=x=>String(x||'').toLowerCase().replace(/[^a-z0-9]+/g,'');
const rawUrl=(commit,path)=>`${GH_RAW}${commit}/nbl_player_props_v1/data/${path}`;

async function readJson(url,maxBytes=4_000_000){
  const allowed=/^https:\/\/raw\.githubusercontent\.com\/Nstp651\/nfl_free_research_pack_v1\/[a-f0-9]{40}\/nbl_player_props_v1\/data\/[A-Za-z0-9_./-]+\.json$/.test(url)||
    /^https:\/\/prod\.rosetta\.nbl\.com\.au\/get\/nbl\/players\/for\/team\/[A-Za-z0-9-]+\/in\/season\/\d{4}$/.test(url);
  requireThat(allowed,'Entry research source URL not allowed');
  const rosetta=url.startsWith(ROSETTA);
  const headers=rosetta?{'accept':'application/json','origin':'https://nbl.com.au','referer':'https://nbl.com.au/','user-agent':'nbl-props-freeze/1.0'}:{'accept':'application/json','user-agent':'nbl-props-freeze/1.0'};
  const res=await fetch(url,{headers,signal:AbortSignal.timeout(15_000)});requireThat(res.ok,`Entry research source unavailable ${res.status}`);
  const raw=await res.text();requireThat(raw.length<=maxBytes,'Entry research source too large');return JSON.parse(raw);
}
function envelopeData(payload,label){requireThat(payload&&typeof payload==='object'&&Array.isArray(payload.data),`${label} malformed`);return payload.data;}
function playerSafe(row){
  const p=row?.player&&typeof row.player==='object'?row.player:row;
  const first=String(p?.first_name||p?.firstName||''),family=String(p?.family_name||p?.last_name||p?.surname||'');
  const display=String(p?.name||p?.display_name||p?.scoreboard_name||'').trim()||`${first} ${family}`.trim();
  return {id:String(p?.id||p?.external_id||row?.id||''),first_name:first,family_name:family,display_name:display,position:String(p?.position||p?.playing_position||'')};
}
async function safeRoster(teamId,season){
  const rows=envelopeData(await readJson(`${ROSETTA}/get/nbl/players/for/team/${teamId}/in/season/${season}`),'roster');
  const out=rows.map(playerSafe).filter(p=>p.id||p.display_name);requireThat(marketKeyHits(out).length===0,'Entry sanitized roster market-boundary failure');return out;
}
function compactPrior(prior,name){const p=prior.players?.[norm(name)];return p?{player_key:p.player_key,last_team:p.last_team,last_season:p.last_season,last_match_time:p.last_match_time,features:p.features}:null;}
async function entryResearchSeed(meta){
  const commit=meta.lock.source_commit;
  const manifest=await readJson(rawUrl(commit,'manifest.json'),200_000);
  requireThat(manifest?.schema_version==='nbl_runtime_assets_v1'&&manifest.market_data===false,'Pinned manifest invalid');
  requireThat(String(manifest.asset_revision)===String(meta.lock.asset_revision),'Pinned manifest revision drift');
  const priorMeta=manifest.prior_snapshot||{};requireThat(priorMeta.path&&/^[a-f0-9]{64}$/.test(String(priorMeta.canonical_sha256||'')),'Pinned prior metadata invalid');
  const prior=await readJson(rawUrl(commit,priorMeta.path));requireThat(await sha256Json(prior)===priorMeta.canonical_sha256,'Pinned prior hash mismatch');
  requireThat(prior.market_data===false&&String(prior.snapshot_revision)===String(meta.lock.snapshot_revision),'Pinned prior identity mismatch');
  const f=meta.lock.fixture,season=meta.lock.season_start;
  const [home,away]=await Promise.all([safeRoster(f.home_team.id,season),safeRoster(f.away_team.id,season)]);
  const decorate=(rows,team)=>rows.map(p=>{const priorNbl=compactPrior(prior,p.display_name);return {...p,team,prior_nbl:priorNbl,nbl_history_status:priorNbl?'NBL_HISTORY_AVAILABLE':'PRIOR_COMP_TRANSLATION_REQUIRED'};});
  return {market_data:false,lock:meta.lock,fixture:f,home_roster:decorate(home,f.home_team.name),away_roster:decorate(away,f.away_team.name),snapshot_revision:prior.snapshot_revision,research_note:'Structured data is a prior only. Current availability, projected minutes, role, lineup, imports, coaching and late news still require current pre-market research.'};
}

/**
 * Stable Cloudflare entry class.
 *
 * The base run owns storage, source locking and atomic freeze. This wrapper fixes
 * two transport-only issues without changing the persisted run format: successful
 * collection POST initialization now returns 200, and GET /research reconstructs
 * its pinned manifest from the locked commit rather than expecting it inside meta.
 */
export class NblMatchRun extends BaseNblMatchRun {
  async handle(request) {
    const url=new URL(request.url);
    const parts=url.pathname.split('/').filter(Boolean);
    const tail=parts.slice(3);
    if(request.method==='GET'&&tail.length===1&&tail[0]==='research'){
      const meta=await this.storage.get('meta');requireThat(meta,'Unknown run');requireThat(meta.status!=='FROZEN','Run already frozen');
      return response(await entryResearchSeed(meta));
    }
    try {
      return await super.handle(request);
    } catch (error) {
      if(request.method==='POST'&&tail.length===0&&error?.message==='Unknown run operation'){
        const meta=await this.storage.get('meta');
        if(meta) return response({market_data:false,status:meta.status,lock:meta.lock});
      }
      throw error;
    }
  }
}
export {listFixtures,response,routeMatchRuns};
