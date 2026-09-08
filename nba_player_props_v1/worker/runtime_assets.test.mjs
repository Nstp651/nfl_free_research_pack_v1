import test from 'node:test';
import assert from 'node:assert/strict';
import { loadRuntimeAssets } from './runtime_assets.js';

const C='a'.repeat(40), H='b'.repeat(64), P='c'.repeat(64);
async function digest(s){const h=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(s));return [...new Uint8Array(h)].map(x=>x.toString(16).padStart(2,'0')).join('');}
function artifact(head){return {status:'PROMOTED_CORE_V1',market_data:false,family:'regularized_poisson_glm',head,features:['minutes_l5'],medians:[30.0],centers:[30.0],scales:[5.0],coefficients:[0.1],intercept:1.0,dispersion_alpha:0.2,model_version:`NBA_${head.toUpperCase()}_QBASE_V1.0.0`,promotion_receipt_sha256:P,holdout_use_rule:'PASS_FAIL_REVIEW_ONLY_NO_MODEL_FAMILY_RESELECTION'};}
async function fixture(){
  const assists=JSON.stringify(artifact('assists'))+'\n',rebounds=JSON.stringify(artifact('rebounds'))+'\n';
  const priorObj={schema_version:'nba_runtime_prior_pack_v1',market_data:false,history_sha256:H,pack_sha256:'d'.repeat(64),player_count:1,team_count:2,players:{},teams:{}};const prior=JSON.stringify(priorObj)+'\n';
  const manifestObj={schema_version:'nba_runtime_assets_v1',market_data:false,asset_revision:'NBA_PLAYER_PROPS_V1.0.0',history_sha256:H,source_acceptance_receipt_sha256:'e'.repeat(64),qbase_heads:{assists:{path:'promoted_assists_qbase.json',file_sha256:await digest(assists),model_version:artifact('assists').model_version,promotion_receipt_sha256:P},rebounds:{path:'promoted_rebounds_qbase.json',file_sha256:await digest(rebounds),model_version:artifact('rebounds').model_version,promotion_receipt_sha256:P}},runtime_prior:{path:'runtime_prior_pack.json',file_sha256:await digest(prior),pack_sha256:priorObj.pack_sha256,player_count:1,team_count:2},specialist_metrics:'BASE_V1_WITHOUT_SPECIALIST_METRICS',prior_competition_translation:'NO_ROUTE_PROMOTED_UNLESS_SEPARATELY_EVIDENCE_VALIDATED',holdout_rule:'PASS_FAIL_REVIEW_ONLY_NO_MODEL_FAMILY_RESELECTION',manifest_sha256:'f'.repeat(64)};
  const files={'manifest.json':JSON.stringify(manifestObj)+'\n','promoted_assists_qbase.json':assists,'promoted_rebounds_qbase.json':rebounds,'runtime_prior_pack.json':prior};
  const fetchImpl=async url=>{const name=String(url).split('/').at(-1);const body=files[name];return {ok:body!==undefined,status:body===undefined?404:200,text:async()=>body};};return {files,fetchImpl};
}

test('exact file hashes accept pinned promoted runtime assets',async()=>{const {fetchImpl}=await fixture();const out=await loadRuntimeAssets(C,{fetchImpl,force:true});assert.equal(out.source_commit,C);assert.equal(out.qbase_artifacts.assists.status,'PROMOTED_CORE_V1');assert.equal(out.prior_pack.history_sha256,H);});
test('tampered QBASE bytes are rejected even when JSON remains valid',async()=>{const {files}=await fixture();files['promoted_assists_qbase.json']=files['promoted_assists_qbase.json'].replace('0.2','0.3');const fetchImpl=async url=>{const body=files[String(url).split('/').at(-1)];return {ok:true,status:200,text:async()=>body};};await assert.rejects(()=>loadRuntimeAssets(C,{fetchImpl,force:true}),/file hash mismatch/);});
test('unbuilt deployment source commit is rejected before network access',async()=>{await assert.rejects(()=>loadRuntimeAssets('UNBUILT',{fetchImpl:async()=>{throw new Error('network should not run')},force:true}),/source commit invalid/);});
