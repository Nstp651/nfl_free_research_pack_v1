/** Live read-only source acceptance. Synthetic numerical receipts NEVER claim a
 * live football freeze and are not submitted to production checkpoint storage. */
import {writeFileSync} from 'node:fs';
import {verifySources,computeFreeze,TEAM_CHECKS,GAME_CHECKS} from '../worker/freeze_core.js';
const base='https://ncaaf-totals-research-pack-v1.nickarnott01.workers.dev';
const calls=[];
async function get(path){calls.push(path);const r=await fetch(base+path,{signal:AbortSignal.timeout(20000)});if(!r.ok)throw Error('Live source '+r.status);return r.json();}
async function pages(path,key){let off=0,revision,meta,games=[],count=0;do{const p=await get(path+'?limit=20&offset='+off+(revision?'&revision='+revision:''));revision??=p[key];if(p[key]!==revision || p.market_data!==false)throw Error('Revision/boundary');const {games:batch,pagination,...rest}=p;games.push(...batch);meta=rest;off=pagination.next_offset;count++;if(off===null && games.length!==pagination.total_games)throw Error('Incomplete pages');}while(off!==null);return {value:{...meta,games},pages:count};}
const health=await get('/health');if(!health.ok)throw Error('Research health');
const research=await pages('/v1/slates/2026_01','pack_revision');
const qbase=await pages('/v1/qbase/2026_01','qbase_revision');
const now=Date.now(), pack=research.value,q=qbase.value;
const eligible_game_ids=pack.games.filter(g=>g.fixture.fbs_game && !g.fixture.completed && Date.parse(g.fixture.start_utc)>now && g.fixture.sydney_date>='2026-09-05' && g.fixture.sydney_date<='2026-09-07').map(g=>g.game_id).sort();
const lock={season:2026,week:1,slate_id:'2026_01',pack_revision:pack.pack_revision,qbase_revision:q.qbase_revision,eligible_game_ids};
const verified=await verifySources(pack,q,lock);
const contexts=eligible_game_ids.map(id=>{const fx=verified.rmap.get(id).fixture;const e=()=>({finding:'SYNTHETIC ACCEPTANCE ONLY; NOT LIVE FOOTBALL RESEARCH',checked_at:new Date(now).toISOString(),sources:['https://example.org/synthetic-contract-test'],unresolved:true});return {game_id:id,contextual_shift:0,distribution_changed:false,confidence:'C',fragility:'HIGH',frozen_thesis:'Synthetic numerical acceptance only',scenarios:[{id:'base',weight:1,shift:0,residual_scale:1,ledger_ids:[]}],ledger:[],research:{market_data:false,home_team:fx.home_team,away_team:fx.away_team,home:Object.fromEntries(TEAM_CHECKS.map(k=>[k,e()])),away:Object.fromEntries(TEAM_CHECKS.map(k=>[k,e()])),game:Object.fromEntries(GAME_CHECKS.map(k=>[k,e()])),deep_triggers:[],deep_evidence:[]}};});
let output=null;const start=performance.now();
if(contexts.length) output=await computeFreeze(pack,q,lock,contexts,now);
const report={mode:'LIVE_SOURCES_LOCAL_CALCULATOR_SYNTHETIC_RESEARCH',production_live:false,market_board_calls:0,market_data:false,research_pages:research.pages,qbase_pages:qbase.pages,published_anchor_count:verified.receipts.length,eligible_game_count:eligible_game_ids.length,lock,cutoff:verified.cutoff,calculation_ms:Math.round(performance.now()-start),identity_receipt_sha256:output?.identity_receipt_sha256,synthetic_numerical_receipt_sha256:output?.numerical_output_sha256,probability_audit:output?.probability_audit,zero_shift_audit:output?.zero_shift_audit,source_calls:calls};
if(process.argv[2])writeFileSync(process.argv[2],JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report,null,2));
