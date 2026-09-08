/** Load immutable NBA runtime assets from the exact deployment Git commit. */
import { sha256Json, validateQbaseArtifact } from './runtime_score.js';
import { marketKeyHits } from './research_contract.js';
const ROOT='https://raw.githubusercontent.com/Nstp651/nfl_free_research_pack_v1';
const need=(ok,msg)=>{if(!ok) throw new Error(msg);};
const HASH64=/^[0-9a-f]{64}$/;
let cache=null;

async function sha256Utf8(text){const bytes=new TextEncoder().encode(text),hash=await crypto.subtle.digest('SHA-256',bytes);return [...new Uint8Array(hash)].map(x=>x.toString(16).padStart(2,'0')).join('');}
function assetUrl(commit,path){need(/^[0-9a-f]{40}$/.test(String(commit||'')),'deployment source commit invalid');need(/^[A-Za-z0-9_.-]+\.json$/.test(String(path||'')),'runtime asset path invalid');return `${ROOT}/${commit}/nba_player_props_v1/data/${path}`;}
async function readJson(commit,path,{expectedFileSha=null,maxBytes=4_000_000,fetchImpl=fetch}={}){const url=assetUrl(commit,path);const res=await fetchImpl(url,{headers:{accept:'application/json','user-agent':'nba-player-props-research-v1/1.0'},signal:AbortSignal.timeout(15000)});need(res.ok,`runtime asset unavailable ${res.status}: ${path}`);const raw=await res.text();need(raw.length<=maxBytes,`runtime asset too large: ${path}`);if(expectedFileSha!==null){need(HASH64.test(String(expectedFileSha)),`runtime asset file hash invalid: ${path}`);need(await sha256Utf8(raw)===expectedFileSha,`runtime asset file hash mismatch: ${path}`);}return JSON.parse(raw);}
async function verifySelfHash(value,field,label){const claimed=String(value?.[field]||'');need(HASH64.test(claimed),`${label} self hash missing`);const copy=structuredClone(value);delete copy[field];need(await sha256Json(copy)===claimed,`${label} self hash mismatch`);}

export async function loadRuntimeAssets(sourceCommit,{fetchImpl=fetch,force=false}={}){
  if(!force&&cache?.source_commit===sourceCommit)return cache;
  const manifest=await readJson(sourceCommit,'manifest.json',{maxBytes:200_000,fetchImpl});need(manifest?.schema_version==='nba_runtime_assets_v1'&&manifest.market_data===false,'runtime manifest invalid');await verifySelfHash(manifest,'manifest_sha256','runtime manifest');need(manifest.holdout_rule==='PASS_FAIL_REVIEW_ONLY_NO_MODEL_FAMILY_RESELECTION','runtime manifest holdout rule invalid');
  const artifacts={};for(const head of ['assists','rebounds']){const meta=manifest.qbase_heads?.[head];need(meta&&meta.path,`${head} manifest entry missing`);const artifact=await readJson(sourceCommit,meta.path,{expectedFileSha:meta.file_sha256,maxBytes:1_000_000,fetchImpl});validateQbaseArtifact(artifact,head);need(artifact.status==='PROMOTED_CORE_V1'&&artifact.market_data===false,`${head} QBASE not promoted`);need(marketKeyHits(artifact).length===0,`${head} QBASE market leakage`);need(artifact.model_version===meta.model_version,`${head} model version drift`);need(artifact.promotion_receipt_sha256===meta.promotion_receipt_sha256,`${head} promotion receipt drift`);await verifySelfHash(artifact,'promotion_receipt_sha256',`${head} promotion`);artifacts[head]=artifact;}
  const priorMeta=manifest.runtime_prior;need(priorMeta?.path,'runtime prior manifest entry missing');const prior=await readJson(sourceCommit,priorMeta.path,{expectedFileSha:priorMeta.file_sha256,maxBytes:4_000_000,fetchImpl});need(prior?.schema_version==='nba_runtime_prior_pack_v1'&&prior.market_data===false,'runtime prior pack invalid');need(prior.history_sha256===manifest.history_sha256,'runtime prior history drift');need(prior.pack_sha256===priorMeta.pack_sha256,'runtime prior pack receipt drift');need(Number(prior.player_count)===Number(priorMeta.player_count)&&Number(prior.team_count)===Number(priorMeta.team_count),'runtime prior count drift');await verifySelfHash(prior,'pack_sha256','runtime prior pack');
  cache={source_commit:sourceCommit,manifest,qbase_artifacts:artifacts,prior_pack:prior};return cache;
}
