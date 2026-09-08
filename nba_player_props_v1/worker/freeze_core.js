/** NBA V1 server-authoritative market-blind quantitative freeze core. */
import { scoreRuntime, sha256Json, validateQbaseArtifact } from './runtime_score.js';
import { buildTransformsFromResearch } from './research_to_transforms.js';
import { marketKeyHits, requestedHeads, validateResearchCheckpoint } from './research_contract.js';
const need=(ok,msg)=>{if(!ok) throw new Error(msg);};
const HASH64=/^[0-9a-f]{64}$/;

function poissonPmf(k,mu){if(k<0)return 0;let p=Math.exp(-mu);for(let i=1;i<=k;i++)p*=mu/i;return p;}
function nbPmfArray(mu,alpha,maxK){need(Number.isFinite(mu)&&mu>0,'mean invalid');need(Number.isFinite(alpha)&&alpha>=0,'alpha invalid');if(alpha<=1e-8)return Array.from({length:maxK+1},(_,k)=>poissonPmf(k,mu));const r=1/alpha,p=r/(r+mu),q=1-p;const out=[Math.pow(p,r)];for(let k=0;k<maxK;k++)out.push(out[k]*((k+r)/(k+1))*q);return out;}
export function probabilityGrid(mu,alpha,maxCount){
  need(Number.isInteger(maxCount)&&maxCount>=8&&maxCount<=60,'max_count invalid');const pmf=nbPmfArray(mu,alpha,maxCount);const cdf=[];let run=0;for(const x of pmf){run+=x;cdf.push(Math.min(1,Math.max(0,run)));}
  const atLeast=n=>n<=0?1:Math.max(0,Math.min(1,1-(cdf[n-1]??1)));
  const half=[];for(let k=0;k<maxCount;k++)half.push({line:k+.5,over:atLeast(k+1),push:0,under:cdf[k]});
  const integers=[];for(let n=1;n<=maxCount;n++){const under=cdf[n-1]??1,push=pmf[n]??0,over=Math.max(0,1-under-push);integers.push({line:n,over,push,under});}
  for(const row of [...half,...integers])need(Math.abs(row.over+row.push+row.under-1)<=1e-9,'probability partition failed');
  return {distribution:alpha<=1e-8?'poisson':'negative_binomial_nb2',mean:mu,alpha,max_count:maxCount,count_pmf:pmf.map((probability,count)=>({count,probability})),tail_above_max_count:Math.max(0,1-pmf.reduce((a,b)=>a+b,0)),at_least_ladder:Array.from({length:maxCount},(_,i)=>({threshold:i+1,at_least:atLeast(i+1)})),half_point_grid:half,integer_push_grid:integers};
}

export function validatePromotedArtifact(a,head){validateQbaseArtifact(a,head);need(a.status==='PROMOTED_CORE_V1',`${head} QBASE not promoted`);need(a.market_data===false,`${head} QBASE market boundary failed`);need(marketKeyHits(a).length===0,`${head} QBASE market leakage`);need(HASH64.test(String(a.promotion_receipt_sha256||'')),`${head} promotion receipt invalid`);need(a.holdout_use_rule==='PASS_FAIL_REVIEW_ONLY_NO_MODEL_FAMILY_RESELECTION',`${head} holdout rule invalid`);return a;}
function grade(researchPlayer){const width=Number(researchPlayer.projected_minutes.high)-Number(researchPlayer.projected_minutes.low);const role=researchPlayer.role_state,avail=researchPlayer.availability;let confidence='A',fragility='LOW';if(['QUESTIONABLE','DOUBTFUL','UNKNOWN'].includes(avail)||['ROOKIE','NEW_TO_NBA'].includes(role)){confidence='C';fragility='HIGH';}else if(['RETURNING_CHANGED','NEW_TO_TEAM','UNKNOWN'].includes(role)||width>6){confidence='B';fragility=width>10?'HIGH':'MEDIUM';}else if(width>8){confidence='B';fragility='MEDIUM';}return {confidence,fragility};}
function maxCount(head){return head==='assists'?30:40;}

export async function computeGameFreeze({research,qbaseArtifacts,priorSnapshots,frozenAt}){
  validateResearchCheckpoint(research);need(marketKeyHits(priorSnapshots).length===0,'prior snapshot market boundary failed');
  const heads=requestedHeads(research.run_mode);for(const head of heads)validatePromotedArtifact(qbaseArtifacts[head],head);
  const priorByPlayer=new Map((priorSnapshots||[]).map(p=>[String(p.player_id),p]));const modeled=[];const exclusions=[];
  for(const rp of research.players){
    if(rp.availability==='OUT'){exclusions.push({player_id:rp.player_id,player_name:rp.player_name,reason:'OUT'});continue;}
    const prior=priorByPlayer.get(String(rp.player_id));const outHeads={};const missing=[];
    for(const head of heads){
      const hp=prior?.heads?.[head];if(!hp){missing.push(head);continue;}
      need(HASH64.test(String(hp.prior_snapshot_sha256||'')),`${rp.player_id}.${head} prior snapshot receipt invalid`);need(hp.base_features&&typeof hp.base_features==='object',`${rp.player_id}.${head} base_features required`);
      const transforms=buildTransformsFromResearch(qbaseArtifacts[head],rp);const scored=await scoreRuntime(qbaseArtifacts[head],hp.base_features,transforms);const grid=probabilityGrid(scored.mean,scored.dispersion_alpha,maxCount(head));
      const headCore={qbase_model_version:qbaseArtifacts[head].model_version,promotion_receipt_sha256:qbaseArtifacts[head].promotion_receipt_sha256,prior_snapshot_sha256:hp.prior_snapshot_sha256,quant_input_receipt_sha256:scored.quant_input_receipt_sha256,transform_chain_sha256:scored.transform_chain_sha256,final_mean:scored.mean,dispersion_alpha:scored.dispersion_alpha,probability_grid:grid};
      headCore.head_model_sha256=await sha256Json(headCore);outHeads[head]=headCore;
    }
    if(Object.keys(outHeads).length===0){exclusions.push({player_id:rp.player_id,player_name:rp.player_name,reason:['ROOKIE','NEW_TO_NBA'].includes(rp.role_state)?'NO_PROMOTED_PRIOR_COMP_TRANSLATION':'NO_SERVER_QBASE_PRIOR',missing_heads:heads});continue;}
    const g=grade(rp);const playerCore={player_id:String(rp.player_id),player_name:String(rp.player_name),team_id:String(rp.team_id),team:String(rp.team),availability:rp.availability,role_state:rp.role_state,projected_minutes:rp.projected_minutes,confidence:g.confidence,fragility:g.fragility,missing_heads:missing,heads:outHeads};playerCore.player_model_sha256=await sha256Json(playerCore);modeled.push(playerCore);
  }
  modeled.sort((a,b)=>(a.team+'\0'+a.player_name).localeCompare(b.team+'\0'+b.player_name));
  const fixture={season:Number(research.fixture.season),home_team:structuredClone(research.fixture.home_team),away_team:structuredClone(research.fixture.away_team),start_time_utc:String(research.fixture.start_time_utc)};
  const core={schema_version:'nba_game_freeze_v1',market_data:false,status:'FROZEN',game_id:research.game_id,slate_date_et:research.slate_date_et,run_mode:research.run_mode,fixture,frozen_at:frozenAt||new Date().toISOString(),research_receipt_sha256:await sha256Json(research),players:modeled,exclusions};
  core.freeze_receipt_sha256=await sha256Json(core);return core;
}

export async function computeSlateFreeze({slateDateEt,runMode,eligibleGameIds,researchByGame,qbaseArtifacts,priorsByGame,frozenAt}){
  const ids=[...eligibleGameIds].map(String);need(ids.length>0&&new Set(ids).size===ids.length,'eligible game ids invalid');const heads=requestedHeads(runMode);for(const h of heads)validatePromotedArtifact(qbaseArtifacts[h],h);
  for(const id of ids)need(researchByGame[id],`research missing ${id}`);
  const games=[];for(const id of ids){const research=researchByGame[id];need(research.slate_date_et===slateDateEt,'slate date mismatch');need(research.run_mode===runMode,'run mode mismatch');games.push(await computeGameFreeze({research,qbaseArtifacts,priorSnapshots:priorsByGame[id]||[],frozenAt}));}
  const qbaseHeads={};for(const h of heads)qbaseHeads[h]={model_version:qbaseArtifacts[h].model_version,promotion_receipt_sha256:qbaseArtifacts[h].promotion_receipt_sha256,artifact_sha256:await sha256Json(qbaseArtifacts[h])};
  const integrityIndex=games.map(game=>({game_id:String(game.game_id),game_freeze_receipt_sha256:game.freeze_receipt_sha256,players:game.players.map(player=>({player_id:String(player.player_id),player_model_sha256:player.player_model_sha256,heads:Object.fromEntries(Object.entries(player.heads).map(([head,value])=>[head,value.head_model_sha256]))}))}));
  const core={schema_version:'nba_slate_freeze_v1',market_data:false,status:'FROZEN',slate_date_et:slateDateEt,run_mode:runMode,eligible_game_ids:ids,games,qbase_heads:qbaseHeads,integrity_index:integrityIndex,frozen_at:frozenAt||new Date().toISOString()};core.freeze_receipt_sha256=await sha256Json(core);return core;
}
