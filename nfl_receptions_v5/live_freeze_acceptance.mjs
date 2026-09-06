import assert from 'node:assert/strict';

const CONTROL='https://nfl-receptions-platform-v5.nickarnott01.workers.dev';
const MARKET='https://nfl-receptions-market-v5.nickarnott01.workers.dev';
const sleep=ms=>new Promise(r=>setTimeout(r,ms));

async function jsonFetch(url,options={}){
  const res=await fetch(url,options); const text=await res.text(); let data;
  try{data=JSON.parse(text);}catch{throw new Error(`Non-JSON ${res.status} from ${url}: ${text.slice(0,300)}`);}
  return {res,data};
}
async function waitHealth(){
  let last;
  for(let i=0;i<30;i++){
    try{
      const c=await jsonFetch(`${CONTROL}/health`); const m=await jsonFetch(`${MARKET}/health`); last={c:c.data,m:m.data};
      if(c.res.ok&&m.res.ok&&c.data.version==='1.2.0'&&c.data.source_lock==='CONTENT_SHA256'&&c.data.fixture_binding==='SERVER_LOCKED'&&m.data.control_transport==='SERVICE_BINDING'&&m.data.configured===true)return last;
    }catch(e){last=String(e);}
    await sleep(5000);
  }
  throw new Error(`Required deployed architecture not ready: ${JSON.stringify(last)}`);
}

const health=await waitHealth();
const init={season:2026,week:1,game_id:'2026_01_NE_SEA',fixture_date_sydney:'2026-09-10',validated_kickoff_utc:'2026-09-10T03:20:00Z'};
const create=await jsonFetch(`${CONTROL}/v1/runs`,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(init)});
assert.equal(create.res.status,200,`Run create failed: ${JSON.stringify(create.data)}`);
assert.equal(create.data.status,'RESEARCH_IN_PROGRESS');
assert.equal(create.data.p_model_status,'NOT FROZEN');
const runId=create.data.run_id; assert.match(runId,/^[a-f0-9]{64}$/);
const lock=create.data.lock;
assert.match(lock.source_anchor_sha256,/^[a-f0-9]{64}$/); assert.match(lock.pack_revision,/^[a-f0-9]{16}$/);

// Retrieve the complete locked pack exactly as a GPT Action run must.
const players=[]; let offset=0; let lastPage;
do{
  const page=await jsonFetch(`${CONTROL}/v1/runs/${runId}/research?offset=${offset}&limit=20`);
  assert.equal(page.res.status,200,`Research retrieval failed: ${JSON.stringify(page.data)}`);
  assert.equal(page.data.lock.source_anchor_sha256,lock.source_anchor_sha256);
  players.push(...page.data.players); lastPage=page.data;
  offset=page.data.pagination.next_offset;
}while(offset!==null);
assert.equal(players.length,create.data.research.player_count);
assert.equal(lastPage.retrieval.complete,true);
assert.equal(lastPage.retrieval.served_player_count,players.length);

const teams=[lock.away_team,lock.home_team];
const chosen=teams.map(team=>{
  const p=players.find(x=>x.team===team&&typeof x.player_id==='string'&&/^[A-Z0-9_-]{3,64}$/.test(x.player_id)&&typeof x.player_name==='string'&&x.player_name.length>=2);
  assert.ok(p,`No contract-valid pack player for ${team}`); return p;
});
const now=new Date().toISOString();
const evidence=[];
for(const team of teams){
  evidence.push({evidence_id:`ACC_${team}_ROLE`,source:'Platform acceptance fixture',source_url:null,source_date:null,checked_at:now,subject:`${team} synthetic role`,finding:'Synthetic contract evidence used only to validate production infrastructure.',model_pathway:'ROLE',availability:'VERIFIED'});
  evidence.push({evidence_id:`ACC_${team}_DEF`,source:'Platform acceptance fixture',source_url:null,source_date:null,checked_at:now,subject:`${team} synthetic defense`,finding:'Synthetic defensive evidence used only to validate checkpoint structure.',model_pathway:'DEFENSE',availability:'VERIFIED'});
}
const part=(id,label)=>({status:'VERIFIED',summary:`Synthetic ${label} acceptance evidence only.`,evidence_ids:[id]});
const context={
  game_id:init.game_id,
  completed_at:now,
  pack_receipt:{source_anchor_sha256:lock.source_anchor_sha256,pack_revision:lock.pack_revision,retrieved_player_count:players.length},
  current_information_state:{acceptance_mode:'SYNTHETIC_INFRASTRUCTURE_ONLY',pre_market:true},
  research_quality_permission:'YES',
  evidence,
  team_contexts:teams.map(team=>({team,summary:'Synthetic infrastructure acceptance team context; not football research.',evidence_ids:[`ACC_${team}_ROLE`]})),
  defensive_profiles:teams.map(team=>({team,passing_opportunities_faced:part(`ACC_${team}_DEF`,'passing opportunity'),position_depth_concessions:part(`ACC_${team}_DEF`,'depth concession'),pressure_protection:part(`ACC_${team}_DEF`,'pressure/protection'),current_personnel:part(`ACC_${team}_DEF`,'personnel'),limitations:['Acceptance-only synthetic evidence; never use for betting.']})),
  players:chosen.map(p=>({player_id:p.player_id,player_name:p.player_name,team:p.team,research_status:'INCLUDE',evidence_ids:[`ACC_${p.team}_ROLE`],handoff_summary:'Synthetic infrastructure acceptance player; not a football projection.'})),
  material_unknowns:['All football evidence is intentionally synthetic because this run validates infrastructure only.'],
  research_summary:'Infrastructure-only synthetic Layer 1 receipt used to validate complete-pack checkpointing, exact identity binding, deterministic freeze and immutability. Never use this run for betting.'
};
const checkpoint=await jsonFetch(`${CONTROL}/v1/runs/${runId}/research`,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({context})});
assert.equal(checkpoint.res.status,200,`Checkpoint failed: ${JSON.stringify(checkpoint.data)}`);
assert.equal(checkpoint.data.status,'RESEARCH_COMPLETE'); assert.match(checkpoint.data.research_receipt_sha256,/^[a-f0-9]{64}$/);

const modelInput={
  game_id:init.game_id,
  engine_version:'NFL_RECEPTIONS_V5_EXACT_HBB_1.0.0',
  threshold_max:10,
  teams:teams.map(team=>{
    const p=chosen.find(x=>x.team===team);
    return {team,players:[{player_id:p.player_id,player_name:p.player_name,confidence:'LOW',fragility:'HIGH',key_assumptions:['Synthetic infrastructure acceptance only; not a betting projection.']}],scenarios:[{scenario_id:'BASE',weight:1,targetable_passes:[{value:30,probability:1}],other_share:0.8,player_params:[{player_id:p.player_id,target_method:'A',target_rate:{mean:0.2,strength:20},catch_rate:{mean:0.65,strength:20},route_counts:null}],football_rationale:'Synthetic infrastructure acceptance scenario only; no football judgement.'}]};
  }),
  source_to_parameter_ledger:teams.map(team=>({parameter_path:`teams.${team}.scenarios.BASE`,evidence_ids:[`ACC_${team}_ROLE`],rationale:'Synthetic evidence binding for infrastructure acceptance only.'}))
};
const compute=await jsonFetch(`${CONTROL}/v1/runs/${runId}/compute`,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({model_input:modelInput})});
assert.equal(compute.res.status,200,`Compute failed: ${JSON.stringify(compute.data)}`);
assert.equal(compute.data.complete_model_integrity_confirmed,true); assert.equal(compute.data.p_model_status,'FROZEN');
const freeze=compute.data.freeze;
assert.match(freeze.freeze_receipt_sha256,/^[a-f0-9]{64}$/); assert.match(freeze.frozen_probability_sha256,/^[a-f0-9]{64}$/); assert.match(freeze.model_input_sha256,/^[a-f0-9]{64}$/);
assert.equal(freeze.research_receipt_sha256,checkpoint.data.research_receipt_sha256); assert.equal(freeze.players.length,2);
for(const audit of freeze.team_allocation_audits){assert.ok(Math.abs(audit.combined_total_share-1)<=1e-8);}
for(const p of freeze.players){let prior=1;for(let k=1;k<=10;k++){const value=p.ladder[String(k)];assert.ok(value<=prior+1e-10);prior=value;}}

// The immutable artifact and status must agree exactly.
const status=await jsonFetch(`${CONTROL}/v1/runs/${runId}`); assert.equal(status.res.status,200); assert.equal(status.data.status,'FROZEN'); assert.equal(status.data.p_model_status,'FROZEN'); assert.equal(status.data.freeze.freeze_receipt_sha256,freeze.freeze_receipt_sha256);
const artifact=await jsonFetch(`${CONTROL}/v1/runs/${runId}/freeze`); assert.equal(artifact.res.status,200); assert.equal(artifact.data.freeze.freeze_receipt_sha256,freeze.freeze_receipt_sha256); assert.equal(artifact.data.freeze.frozen_probability_sha256,freeze.frozen_probability_sha256);
const recompute=await jsonFetch(`${CONTROL}/v1/runs/${runId}/compute`,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({model_input:modelInput})}); assert.equal(recompute.res.status,200); assert.equal(recompute.data.p_model_status,'FROZEN'); assert.equal(recompute.data.freeze.freeze_receipt_sha256,freeze.freeze_receipt_sha256);
const researchAfter=await jsonFetch(`${CONTROL}/v1/runs/${runId}/research?offset=0&limit=1`); assert.equal(researchAfter.res.status,422); assert.match(String(researchAfter.data.error||''),/immutable/i);
const playerReceipt=await jsonFetch(`${CONTROL}/v1/runs/${runId}/players/${freeze.players[0].player_id}`); assert.equal(playerReceipt.res.status,200); assert.equal(playerReceipt.data.freeze_receipt_sha256,freeze.freeze_receipt_sha256);

console.log(JSON.stringify({acceptance:'PASS',purpose:'SYNTHETIC_INFRASTRUCTURE_ONLY',run_id:runId,game_id:init.game_id,player_count_retrieved:players.length,modelled_players:freeze.players.map(p=>({player_id:p.player_id,player_name:p.player_name,team:p.team})),source_anchor_sha256:lock.source_anchor_sha256,pack_revision:lock.pack_revision,research_receipt_sha256:checkpoint.data.research_receipt_sha256,model_input_sha256:freeze.model_input_sha256,frozen_probability_sha256:freeze.frozen_probability_sha256,freeze_receipt_sha256:freeze.freeze_receipt_sha256,p_model_status:status.data.p_model_status,market_calls:0,health},null,2));
