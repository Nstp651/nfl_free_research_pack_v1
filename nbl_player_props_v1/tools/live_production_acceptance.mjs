#!/usr/bin/env node
import {createHash} from 'node:crypto';
import {writeFile} from 'node:fs/promises';

const RESEARCH='https://nbl-player-props-research-v1.nickarnott01.workers.dev';
const MARKET='https://nbl-player-props-market-v1.nickarnott01.workers.dev';
const SEASON_START=2026;
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const need=(condition,message)=>{if(!condition)throw new Error(message);};
const finite=x=>Number.isFinite(Number(x));
const canonical=v=>Array.isArray(v)?v.map(canonical):(v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])])):v);
const sha256Json=v=>createHash('sha256').update(JSON.stringify(canonical(v))).digest('hex');

async function json(url,options={}){
  const res=await fetch(url,{...options,headers:{accept:'application/json','content-type':'application/json','user-agent':'nbl-production-acceptance/1.0',...(options.headers||{})},signal:AbortSignal.timeout(30_000)});
  const text=await res.text();
  let body;try{body=JSON.parse(text);}catch{throw new Error(`${url} returned non-JSON ${res.status}: ${text.slice(0,300)}`);}
  return {status:res.status,ok:res.ok,body};
}
async function waitHealth(base,label,check){
  let last;
  for(let attempt=1;attempt<=24;attempt++){
    try{last=await json(`${base}/health`);if(last.ok&&check(last.body)){console.log(`${label}_HEALTH=PASS attempt=${attempt}`);return last.body;}}catch(e){last={error:e.message};}
    console.log(`${label}_HEALTH_WAIT attempt=${attempt}`);await sleep(15_000);
  }
  throw new Error(`${label} production health did not converge: ${JSON.stringify(last)}`);
}
function isoAfter(iso,deltaMs){return new Date(Date.parse(iso)+deltaMs).toISOString();}

await waitHealth(RESEARCH,'NBL_RESEARCH',b=>b?.ok===true&&b?.market_data===false&&b?.freeze_storage===true&&Array.isArray(b?.heads)&&b.heads.includes('assists')&&b.heads.includes('rebounds'));
await waitHealth(MARKET,'NBL_MARKET',b=>b?.ok===true&&b?.market_data===true&&Array.isArray(b?.supported_stats)&&b.supported_stats.includes('assists')&&b.supported_stats.includes('rebounds'));

const fixturesRes=await json(`${RESEARCH}/v1/fixtures?season_start=${SEASON_START}`);
need(fixturesRes.ok,`fixture list failed ${fixturesRes.status}: ${JSON.stringify(fixturesRes.body)}`);
const fixtures=(fixturesRes.body.fixtures||[]).filter(f=>Date.parse(f.start_time)>Date.now());
need(fixtures.length>0,'no future 2026 NBL fixture available for production acceptance');
const fixture=fixtures[0];
console.log(`NBL_ACCEPTANCE_FIXTURE=${fixture.away_team?.name} at ${fixture.home_team?.name} ${fixture.start_time} id=${fixture.id}`);

const startRes=await json(`${RESEARCH}/v1/match-runs`,{method:'POST',body:JSON.stringify({fixture_id:String(fixture.id),season_start:SEASON_START,run_mode:'BOTH'})});
need(startRes.ok,`run start failed ${startRes.status}: ${JSON.stringify(startRes.body)}`);
const runId=String(startRes.body.run_id||'');
need(/^[a-f0-9]{64}$/.test(runId),'invalid production run_id');
need(startRes.body.market_data===false,'run start crossed market boundary');
need(startRes.body.status==='RESEARCH_PENDING','unexpected initial run status');
const lock=startRes.body.lock;
need(lock?.fixture_id===String(fixture.id)&&lock?.run_mode==='BOTH','run lock mismatch');
need(/^[a-f0-9]{40}$/.test(String(lock.source_commit||'')),'source_commit invalid');
need(String(lock.asset_revision||'').length>=16,'asset_revision missing');
need(/^[a-f0-9]{64}$/.test(String(lock.qbase_revision?.assists||'')),'assists QBASE revision invalid');
need(/^[a-f0-9]{64}$/.test(String(lock.qbase_revision?.rebounds||'')),'rebounds QBASE revision invalid');

const seedRes=await json(`${RESEARCH}/v1/match-runs/${runId}/research`);
need(seedRes.ok,`research seed failed ${seedRes.status}: ${JSON.stringify(seedRes.body)}`);
need(seedRes.body.market_data===false,'research seed crossed market boundary');
const roster=[...(seedRes.body.home_roster||[]),...(seedRes.body.away_roster||[])];
const player=roster.find(p=>p?.qbase_baseline?.assists?.status==='SERVER_QBASE_RUNTIME_SCORE'&&p?.qbase_baseline?.rebounds?.status==='SERVER_QBASE_RUNTIME_SCORE'&&p?.prior_nbl&&finite(p.prior_nbl?.features?.player_minutes_mean_3));
need(player,'no returning player with both server QBASE heads and historical minutes found');
const minutes=Math.max(0,Math.min(45,Number(player.prior_nbl.features.player_minutes_mean_3)));
const checkedAt=new Date().toISOString();
const rosterUrl=`https://prod.rosetta.nbl.com.au/get/nbl/players/for/team/${player.team===fixture.home_team.name?fixture.home_team.id:fixture.away_team.id}/in/season/${SEASON_START}`;
const priorUrl=`https://raw.githubusercontent.com/Nstp651/nfl_free_research_pack_v1/${lock.source_commit}/nbl_player_props_v1/data/prior_snapshot.json`;
const scheduleUrl=`https://prod.rosetta.nbl.com.au/get/nbl/matches/in/season/${SEASON_START}/all?limit=-1`;
const technicalNote='Technical production acceptance only: verifies market-blind research binding and runtime persistence; it is not a betting recommendation or current-role claim.';
const research={
  schema_version:'nbl_fixture_research_v1',market_data:false,fixture_id:String(fixture.id),pack_revision:String(lock.pack_revision),run_mode:'BOTH',checked_at:checkedAt,
  sources:{
    official_fixture:{url:scheduleUrl,title:'Official NBL Rosetta schedule - production acceptance',checked_at:checkedAt},
    official_roster:{url:rosterUrl,title:'Official NBL Rosetta roster - production acceptance',checked_at:checkedAt},
    historical_prior:{url:priorUrl,title:'Pinned market-blind NBL historical prior - production acceptance',checked_at:checkedAt},
  },
  fixture_context:{status:String(fixture.status||'scheduled'),source_ids:['official_fixture'],notes:[technicalNote]},
  players:[{
    player_id:String(player.id||''),player_name:String(player.display_name),team:String(player.team),availability_status:'UNKNOWN',availability_source_ids:['official_roster'],
    projected_minutes:{low:Math.max(0,minutes-2),mean:minutes,high:Math.min(50,minutes+2),source_ids:['historical_prior','official_roster']},
    role:{state:'UNKNOWN',creation_role:'UNKNOWN',frontcourt_role:'UNKNOWN',source_ids:['official_roster','historical_prior'],notes:[technicalNote]},
    stat_context:{
      assists:{source_ids:['official_roster','historical_prior'],notes:[technicalNote]},
      rebounds:{source_ids:['official_roster','historical_prior'],notes:[technicalNote]},
    },
  }],
};
const checkpoint=await json(`${RESEARCH}/v1/match-runs/${runId}/research`,{method:'POST',body:JSON.stringify(research)});
need(checkpoint.ok,`research checkpoint failed ${checkpoint.status}: ${JSON.stringify(checkpoint.body)}`);
need(checkpoint.body.status==='RESEARCH_COMPLETE'&&/^[a-f0-9]{64}$/.test(String(checkpoint.body.research_context_sha256||'')),'research checkpoint receipt invalid');
need(checkpoint.body.research_context_sha256===sha256Json(research),'research checkpoint hash mismatch');

const scenario=(stat)=>({id:`technical_${stat}_baseline`,weight:1,method:'QBASE_RUNTIME_SCORE',evidence_source_ids:['official_roster','historical_prior'],assumptions:[technicalNote]});
const projections=[{player_id:String(player.id||''),player_name:String(player.display_name),team:String(player.team),heads:{
  assists:{confidence:'C',fragility:'HIGH',scenarios:[scenario('assists')]},
  rebounds:{confidence:'C',fragility:'HIGH',scenarios:[scenario('rebounds')]},
}}];
const freezeRes=await json(`${RESEARCH}/v1/match-runs/${runId}/compute`,{method:'POST',body:JSON.stringify({projections})});
need(freezeRes.ok,`freeze failed ${freezeRes.status}: ${JSON.stringify(freezeRes.body)}`);
const freeze=freezeRes.body;
need(freeze.status==='FROZEN'&&freeze.market_data===false,'P_MODEL_STATUS not FROZEN/market-blind');
need(/^[a-f0-9]{64}$/.test(String(freeze.freeze_receipt_sha256||'')),'freeze receipt invalid');
for(const key of ['market_boundary','research_binding','server_qbase_authority','scenario_weighting','probability_grid','atomic_requested_heads'])need(freeze.audits?.[key]==='PASS',`freeze audit ${key} failed`);
need(Array.isArray(freeze.players)&&freeze.players.length===1,'technical freeze player count mismatch');
need(/^[a-f0-9]{64}$/.test(String(freeze.players[0].player_model_sha256||'')),'player model hash missing');

const immutable=await json(`${RESEARCH}/v1/match-runs/${runId}/compute`,{method:'POST',body:JSON.stringify({projections:[]})});
need(immutable.ok,'immutable retry failed');
need(immutable.body.freeze_receipt_sha256===freeze.freeze_receipt_sha256&&immutable.body.frozen_at===freeze.frozen_at,'immutable retry changed freeze identity');

const playerKey=freeze.players[0].player_key;
const fullRes=await json(`${RESEARCH}/v1/match-runs/${runId}/players/${encodeURIComponent(playerKey)}`);
need(fullRes.ok,`frozen player retrieval failed ${fullRes.status}: ${JSON.stringify(fullRes.body)}`);
need(fullRes.body.freeze_receipt_sha256===freeze.freeze_receipt_sha256&&fullRes.body.frozen_at===freeze.frozen_at,'frozen player receipt mismatch');
need(fullRes.body.player_model_sha256===freeze.players[0].player_model_sha256,'frozen player hash binding mismatch');
need(sha256Json(fullRes.body.player)===fullRes.body.player_model_sha256,'frozen player payload hash mismatch');
const grid=fullRes.body.player?.heads?.assists?.probability_grid?.half_point_grid;
need(Array.isArray(grid)&&grid.length>0,'assists half-point grid unavailable');
const target=grid.reduce((best,row)=>Math.abs(Number(row.line)-Number(fullRes.body.player.heads.assists.final_mean))<Math.abs(Number(best.line)-Number(fullRes.body.player.heads.assists.final_mean))?row:best,grid[0]);
const capturedAt=isoAfter(freeze.frozen_at,1000);
const synthetic={fixture_id:String(fixture.id),player_id:String(player.id||''),player_name:String(player.display_name),stat_type:'assists',side:'over',threshold:Number(target.line),decimal_price:2.0,bookmaker:'NBL_ACCEPTANCE_TEST_ONLY',captured_at:capturedAt,source_type:'public_web'};
const marketRes=await json(`${MARKET}/v1/evaluate`,{method:'POST',body:JSON.stringify({run_id:runId,expected_freeze_receipt_sha256:freeze.freeze_receipt_sha256,markets:[synthetic]})});
need(marketRes.ok,`post-freeze market binding failed ${marketRes.status}: ${JSON.stringify(marketRes.body)}`);
need(marketRes.body.p_model_status==='FROZEN'&&marketRes.body.p_model_mutated===false&&marketRes.body.freeze_receipt_sha256===freeze.freeze_receipt_sha256,'market evaluation mutated or lost freeze binding');
need(marketRes.body.market_records_evaluated===1,'market acceptance row not evaluated');
const preFreeze={...synthetic,captured_at:isoAfter(freeze.frozen_at,-1000)};
const rejectRes=await json(`${MARKET}/v1/evaluate`,{method:'POST',body:JSON.stringify({run_id:runId,expected_freeze_receipt_sha256:freeze.freeze_receipt_sha256,markets:[preFreeze]})});
need(rejectRes.status===422&&/predates P_model freeze/i.test(String(rejectRes.body?.error||'')),'pre-freeze market timestamp was not rejected');
const badReceipt='0'.repeat(64)===freeze.freeze_receipt_sha256?'1'.repeat(64):'0'.repeat(64);
const badReceiptRes=await json(`${MARKET}/v1/evaluate`,{method:'POST',body:JSON.stringify({run_id:runId,expected_freeze_receipt_sha256:badReceipt,markets:[synthetic]})});
need(badReceiptRes.status===422&&/Freeze receipt mismatch/i.test(String(badReceiptRes.body?.error||'')),'wrong freeze receipt was not rejected');

const receipt={
  schema_version:'nbl_production_live_acceptance_v1',accepted_at:new Date().toISOString(),season_start:SEASON_START,
  research_health:'PASS',market_health:'PASS',fixture_id:String(fixture.id),fixture:`${fixture.away_team?.name} at ${fixture.home_team?.name}`,fixture_start_time:fixture.start_time,
  run_id:runId,source_commit:lock.source_commit,asset_revision:lock.asset_revision,snapshot_revision:lock.snapshot_revision,qbase_revision:lock.qbase_revision,
  research_context_sha256:checkpoint.body.research_context_sha256,frozen_at:freeze.frozen_at,freeze_receipt_sha256:freeze.freeze_receipt_sha256,
  player_key:playerKey,player_model_sha256:fullRes.body.player_model_sha256,player_name:player.display_name,
  audits:freeze.audits,immutable_retry:'PASS',player_hash_binding:'PASS',post_freeze_market_binding:'PASS',pre_freeze_market_rejection:'PASS',wrong_freeze_receipt_rejection:'PASS',
  market_test_note:'Synthetic post-freeze transport row used only to prove Market Worker binding/integrity; not a sportsbook observation or betting recommendation.'
};
console.log('NBL_PRODUCTION_LIVE_ACCEPTANCE=PASS');
console.log(JSON.stringify(receipt,null,2));
if(process.env.NBL_ACCEPTANCE_OUTPUT)await writeFile(process.env.NBL_ACCEPTANCE_OUTPUT,JSON.stringify(receipt,null,2)+'\n');
