import {NblMatchRun as BaseNblMatchRun,listFixtures,response,routeMatchRuns} from './freeze_run.js';
import {marketKeyHits,requireThat,sha256Json} from './freeze_core.js';
import {projectedMinutesScore,returningPlayerBaseline} from './runtime_score.js';

const GH_RAW='https://raw.githubusercontent.com/Nstp651/nfl_free_research_pack_v1/';
const ROSETTA='https://prod.rosetta.nbl.com.au';
const norm=x=>String(x||'').normalize('NFKD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,'');
const rawUrl=(commit,path)=>`${GH_RAW}${commit}/nbl_player_props_v1/data/${path}`;
const headsFor=mode=>mode==='BOTH'?['assists','rebounds']:(mode==='ASSISTS_ONLY'?['assists']:(mode==='REBOUNDS_ONLY'?['rebounds']:(()=>{throw new Error('Unsupported run_mode');})()));
const finite=x=>Number.isFinite(Number(x));
const close=(a,b)=>Math.abs(Number(a)-Number(b))<=1e-6*Math.max(1,Math.abs(Number(b)));
const projectionKey=p=>String(p?.player_id||'').trim()?`id:${String(p.player_id).trim()}`:`name:${norm(p?.player_name)}:${norm(p?.team)}`;

async function readJson(url,maxBytes=4_000_000){
  const allowed=/^https:\/\/raw\.githubusercontent\.com\/Nstp651\/nfl_free_research_pack_v1\/[a-f0-9]{40}\/nbl_player_props_v1\/data\/[A-Za-z0-9_./-]+\.json$/.test(url)||/^https:\/\/prod\.rosetta\.nbl\.com\.au\/get\/nbl\/players\/for\/team\/[A-Za-z0-9-]+\/in\/season\/\d{4}$/.test(url);requireThat(allowed,'Entry research source URL not allowed');
  const rosetta=url.startsWith(ROSETTA),headers=rosetta?{'accept':'application/json','origin':'https://nbl.com.au','referer':'https://nbl.com.au/','user-agent':'nbl-props-freeze/1.0'}:{'accept':'application/json','user-agent':'nbl-props-freeze/1.0'};const res=await fetch(url,{headers,signal:AbortSignal.timeout(15_000)});requireThat(res.ok,`Entry research source unavailable ${res.status}`);const raw=await res.text();requireThat(raw.length<=maxBytes,'Entry research source too large');return JSON.parse(raw);
}
function envelopeData(payload,label){requireThat(payload&&typeof payload==='object'&&Array.isArray(payload.data),`${label} malformed`);return payload.data;}
function playerSafe(row){const p=row?.player&&typeof row.player==='object'?row.player:row,first=String(p?.first_name||p?.firstName||''),family=String(p?.family_name||p?.last_name||p?.surname||''),display=String(p?.name||p?.display_name||p?.scoreboard_name||'').trim()||`${first} ${family}`.trim();return {id:String(p?.id||p?.external_id||row?.id||''),first_name:first,family_name:family,display_name:display,position:String(p?.position||p?.playing_position||'')};}
async function safeRoster(teamId,season){const rows=envelopeData(await readJson(`${ROSETTA}/get/nbl/players/for/team/${teamId}/in/season/${season}`),'roster');const out=rows.map(playerSafe).filter(p=>p.id||p.display_name);requireThat(marketKeyHits(out).length===0,'Entry sanitized roster market-boundary failure');return out;}
function priorFor(prior,name,playerId=''){
  const values=Object.values(prior.players||{}).filter(v=>v&&typeof v==='object'),pid=String(playerId||'').trim();
  if(pid){const byId=values.filter(v=>Array.isArray(v.source_player_ids)&&v.source_player_ids.map(String).includes(pid));requireThat(byId.length<=1,`Historical player ID ${pid} maps to multiple priors`);if(byId.length===1)return byId[0];}
  return prior.players?.[norm(name)]||null;
}
function compactPrior(prior,name,playerId=''){const p=priorFor(prior,name,playerId);return p?{player_key:p.player_key,source_player_ids:p.source_player_ids||[],last_team:p.last_team,last_season:p.last_season,last_match_time:p.last_match_time,features:p.features}:null;}

async function pinnedPrior(meta){const commit=meta.lock.source_commit,manifest=await readJson(rawUrl(commit,'manifest.json'),200_000);requireThat(manifest?.schema_version==='nbl_runtime_assets_v1'&&manifest.market_data===false,'Pinned manifest invalid');requireThat(String(manifest.asset_revision)===String(meta.lock.asset_revision),'Pinned manifest revision drift');const priorMeta=manifest.prior_snapshot||{};requireThat(priorMeta.path&&/^[a-f0-9]{64}$/.test(String(priorMeta.canonical_sha256||'')),'Pinned prior metadata invalid');const prior=await readJson(rawUrl(commit,priorMeta.path));requireThat(await sha256Json(prior)===priorMeta.canonical_sha256,'Pinned prior hash mismatch');requireThat(prior.market_data===false&&String(prior.snapshot_revision)===String(meta.lock.snapshot_revision),'Pinned prior identity mismatch');return {manifest,prior};}

async function baselineHeads(storage,meta,prior,playerName,playerId,team){const out={};for(const stat of headsFor(meta.lock.run_mode)){const qbase=await storage.get('q:'+stat);requireThat(qbase,`Pinned ${stat} QBASE missing`);try{const b=await returningPlayerBaseline(qbase,prior,{playerName,playerId,team,fixture:meta.lock.fixture,targetSeasonStart:meta.lock.season_start});out[stat]={status:'SERVER_QBASE_RUNTIME_SCORE',mean:b.mean,quant_input_receipt_sha256:b.quant_input_receipt_sha256,missing_features:b.missing_features,player_prior_key:b.feature_context.player_prior_key};}catch(e){if(e?.code==='PRIOR_COMP_TRANSLATION_REQUIRED')out[stat]={status:'PRIOR_COMP_TRANSLATION_REQUIRED'};else throw e;}}return out;}

async function entryResearchSeed(meta,storage){
  const {prior}=await pinnedPrior(meta),f=meta.lock.fixture,season=meta.lock.season_start,[home,away]=await Promise.all([safeRoster(f.home_team.id,season),safeRoster(f.away_team.id,season)]);
  const decorate=async(rows,team)=>Promise.all(rows.map(async p=>{const priorNbl=compactPrior(prior,p.display_name,p.id);return {...p,team,prior_nbl:priorNbl,nbl_history_status:priorNbl?'NBL_HISTORY_AVAILABLE':'PRIOR_COMP_TRANSLATION_REQUIRED',qbase_baseline:await baselineHeads(storage,meta,prior,p.display_name,p.id,team)};}));
  return {market_data:false,lock:meta.lock,fixture:f,home_roster:await decorate(home,f.home_team.name),away_roster:await decorate(away,f.away_team.name),snapshot_revision:prior.snapshot_revision,research_note:'Structured data is a prior only. Current availability, projected minutes, role, lineup, imports, coaching and late news still require current pre-market research. Returning-player QBASE baseline means are computed server-side; new imports require explicit prior-competition translation.'};
}

async function serverizeHead(qbase,prior,meta,researchPlayer,head,stat){
  requireThat(head&&typeof head==='object',`${researchPlayer.player_name}.${stat} head required`);let baseline=null;try{baseline=await returningPlayerBaseline(qbase,prior,{playerName:researchPlayer.player_name,playerId:researchPlayer.player_id,team:researchPlayer.team,fixture:meta.lock.fixture,targetSeasonStart:meta.lock.season_start});}catch(e){if(e?.code!=='PRIOR_COMP_TRANSLATION_REQUIRED')throw e;}
  requireThat(Array.isArray(head.scenarios)&&head.scenarios.length>0,`${researchPlayer.player_name}.${stat} scenarios required`);const scenarios=[];
  if(baseline){
    if(head.qbase_mean!==undefined&&head.qbase_mean!==null)requireThat(finite(head.qbase_mean)&&close(head.qbase_mean,baseline.mean),`${researchPlayer.player_name}.${stat} client qbase_mean does not match server QBASE`);
    for(const original of head.scenarios){const s={...original},method=String(s.method||'').toUpperCase();if(method==='QBASE_RUNTIME_SCORE'){if(s.mean!==undefined&&s.mean!==null)requireThat(finite(s.mean)&&close(s.mean,baseline.mean),`${researchPlayer.player_name}.${stat}.${s.id} runtime mean mismatch`);s.mean=baseline.mean;s.quant_input_receipt_sha256=baseline.quant_input_receipt_sha256;}else if(method==='QBASE_MINUTES_RECOMPUTE'){requireThat(finite(s.projected_minutes),`${researchPlayer.player_name}.${stat}.${s.id} projected_minutes required for server recompute`);const moved=await projectedMinutesScore(qbase,baseline.resolved_features,Number(s.projected_minutes),{starterProbability:s.starter_probability??null});if(s.mean!==undefined&&s.mean!==null)requireThat(finite(s.mean)&&close(s.mean,moved.mean),`${researchPlayer.player_name}.${stat}.${s.id} minutes mean mismatch`);s.mean=moved.mean;s.quant_input_receipt_sha256=moved.quant_input_receipt_sha256;}else{requireThat(['EMPIRICAL_ROLE_SPLIT','PRIOR_COMP_TRANSLATION'].includes(method),`${researchPlayer.player_name}.${stat}.${s.id} unsupported scenario method`);requireThat(finite(s.mean),`${researchPlayer.player_name}.${stat}.${s.id} external scenario mean required`);requireThat(/^[0-9a-f]{64}$/.test(String(s.quant_input_receipt_sha256||'')),`${researchPlayer.player_name}.${stat}.${s.id} external quant receipt required`);}scenarios.push(s);}
    return {...head,qbase_mean:baseline.mean,server_qbase_source:'SERVER_QBASE_RUNTIME_SCORE',server_qbase_receipt_sha256:baseline.quant_input_receipt_sha256,server_player_prior_key:baseline.feature_context.player_prior_key,scenarios};
  }
  for(const original of head.scenarios){const s={...original},method=String(s.method||'').toUpperCase();requireThat(method==='PRIOR_COMP_TRANSLATION',`${researchPlayer.player_name}.${stat} has no NBL prior; all scenarios must use PRIOR_COMP_TRANSLATION`);requireThat(finite(s.mean),`${researchPlayer.player_name}.${stat}.${s.id} translated mean required`);requireThat(/^[0-9a-f]{64}$/.test(String(s.quant_input_receipt_sha256||'')),`${researchPlayer.player_name}.${stat}.${s.id} translation quant receipt required`);scenarios.push(s);}
  const weight=scenarios.reduce((a,s)=>a+Number(s.weight||0),0);requireThat(Math.abs(weight-1)<=1e-9,`${researchPlayer.player_name}.${stat} translation weights must sum to 1`);const translated=scenarios.reduce((a,s)=>a+Number(s.weight)*Number(s.mean),0);requireThat(head.dispersion_override&&finite(head.dispersion_override.alpha),`${researchPlayer.player_name}.${stat} prior-comp translation requires explicit dispersion override`);return {...head,qbase_mean:translated,server_qbase_source:'PRIOR_COMP_TRANSLATION',server_qbase_receipt_sha256:null,server_player_prior_key:null,scenarios};
}

async function serverizeProjections(meta,storage,research,projections){
  requireThat(Array.isArray(projections)&&projections.length>0,'projections required');const {prior}=await pinnedPrior(meta),qbase={};for(const stat of headsFor(meta.lock.run_mode)){qbase[stat]=await storage.get('q:'+stat);requireThat(qbase[stat],`Pinned ${stat} QBASE missing`);}const researchById=new Map(),researchByNameTeam=new Map();for(const p of research.players){if(String(p.player_id||'').trim())researchById.set(String(p.player_id).trim(),p);researchByNameTeam.set(`${norm(p.player_name)}:${norm(p.team)}`,p);}const out=[];
  for(const p of projections){const rp=String(p.player_id||'').trim()?researchById.get(String(p.player_id).trim()):researchByNameTeam.get(`${norm(p.player_name)}:${norm(p.team)}`);requireThat(rp,`Projection ${projectionKey(p)} missing locked research player`);const supplied=p.heads||{},heads={};for(const stat of headsFor(meta.lock.run_mode))heads[stat]=await serverizeHead(qbase[stat],prior,meta,rp,supplied[stat],stat);out.push({...p,player_id:rp.player_id??p.player_id,player_name:rp.player_name,team:rp.team,heads});}
  requireThat(marketKeyHits(out).length===0,'Serverized projections market-boundary failure');return out;
}

export class NblMatchRun extends BaseNblMatchRun {
  async handle(request) {
    const url=new URL(request.url),parts=url.pathname.split('/').filter(Boolean),tail=parts.slice(3);
    if(request.method==='GET'&&tail.length===1&&tail[0]==='research'){const meta=await this.storage.get('meta');requireThat(meta,'Unknown run');requireThat(meta.status!=='FROZEN','Run already frozen');return response(await entryResearchSeed(meta,this.storage));}
    if(request.method==='POST'&&tail.length===1&&tail[0]==='compute'){const meta=await this.storage.get('meta');requireThat(meta,'Unknown run');if(meta.status==='FROZEN')return super.handle(request);const research=await this.storage.get('research');requireThat(research,'Research context incomplete');const body=await request.json();requireThat(body&&typeof body==='object'&&Object.keys(body).every(k=>k==='projections'),'compute body accepts projections only');const projections=await serverizeProjections(meta,this.storage,research,body.projections);const forwarded=new Request(request.url,{method:'POST',headers:request.headers,body:JSON.stringify({projections})});return super.handle(forwarded);}
    try{return await super.handle(request);}catch(error){if(request.method==='POST'&&tail.length===0&&error?.message==='Unknown run operation'){const meta=await this.storage.get('meta');if(meta)return response({market_data:false,status:meta.status,lock:meta.lock});}throw error;}
  }
}
export {listFixtures,response,routeMatchRuns};
