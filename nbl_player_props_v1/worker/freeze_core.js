/** Market-blind quantitative/freeze primitives for NBL player props V1. */
const MARKET_KEY=/(?:odds|sportsbook|bookmaker|moneyline|spread|betting|price|market_line|over_under|total_line)/i;
export const requireThat=(condition,message)=>{if(!condition) throw new Error(message);};

export function marketKeyHits(value,path='root',out=[]){
  if(Array.isArray(value)) value.forEach((v,i)=>marketKeyHits(v,`${path}[${i}]`,out));
  else if(value && typeof value==='object') for(const [k,v] of Object.entries(value)){
    if(MARKET_KEY.test(k)) out.push(`${path}.${k}`); marketKeyHits(v,`${path}.${k}`,out);
  }
  return out;
}
function canonicalValue(v){
  if(Array.isArray(v)) return v.map(canonicalValue);
  if(v && typeof v==='object') return Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonicalValue(v[k])]));
  return v;
}
export function canonicalJson(v){return JSON.stringify(canonicalValue(v));}
export async function sha256Json(v){
  const bytes=new TextEncoder().encode(canonicalJson(v));
  const hash=await crypto.subtle.digest('SHA-256',bytes);
  return [...new Uint8Array(hash)].map(x=>x.toString(16).padStart(2,'0')).join('');
}
export function requestedHeads(mode){
  if(mode==='BOTH') return ['assists','rebounds'];
  if(mode==='ASSISTS_ONLY') return ['assists'];
  if(mode==='REBOUNDS_ONLY') return ['rebounds'];
  throw new Error('Unsupported run_mode');
}

function poissonPmf(k,mu){
  if(k<0) return 0; let p=Math.exp(-mu); for(let i=1;i<=k;i++) p*=mu/i; return p;
}
function nbPmfArray(mu,alpha,maxK){
  requireThat(Number.isFinite(mu)&&mu>=0,'mu invalid');
  requireThat(Number.isFinite(alpha)&&alpha>0,'alpha invalid');
  const out=[];
  if(alpha<=1e-5){for(let k=0;k<=maxK;k++) out.push(poissonPmf(k,mu)); return out;}
  const r=1/alpha,p=r/(r+mu),q=1-p;
  let pk=Math.pow(p,r); out.push(pk);
  for(let k=0;k<maxK;k++){pk=pk*((k+r)/(k+1))*q;out.push(pk);} return out;
}
export function probabilityGrid(mu,alpha,maxCount){
  requireThat(Number.isInteger(maxCount)&&maxCount>=5&&maxCount<=60,'max_count invalid');
  const pmfs=nbPmfArray(mu,alpha,maxCount);
  const cdf=[]; let running=0; for(const p of pmfs){running+=p;cdf.push(Math.min(1,Math.max(0,running)));}
  const atLeast=t=>t<=0?1:Math.max(0,Math.min(1,1-(cdf[t-1]??1)));
  const count_pmf=pmfs.map((p,k)=>({count:k,probability:p}));
  const ladders=Array.from({length:maxCount},(_,i)=>({threshold:i+1,at_least:atLeast(i+1)}));
  const half=[]; for(let k=0;k<maxCount;k++){const under=cdf[k],over=1-under;half.push({line:k+0.5,over,push:0,under});}
  const integers=[]; for(let n=1;n<=maxCount;n++){
    const under=cdf[n-1]??1,push=pmfs[n]??0,over=Math.max(0,1-under-push);
    integers.push({line:n,over,push,under});
  }
  for(let i=0;i<ladders.length-1;i++) requireThat(ladders[i+1].at_least<=ladders[i].at_least+1e-12,'ladder non-monotonic');
  for(const row of [...half,...integers]){
    requireThat(Math.min(row.over,row.push,row.under)>=-1e-12,'negative probability');
    requireThat(Math.abs(row.over+row.push+row.under-1)<=1e-9,'probability partition failed');
  }
  return {distribution:alpha>1e-5?'negative_binomial_nb2':'poisson',mean:mu,alpha,max_count:maxCount,
    count_pmf,tail_above_max_count:Math.max(0,1-pmfs.reduce((a,b)=>a+b,0)),at_least_ladder:ladders,
    half_point_grid:half,integer_push_grid:integers};
}

const AVAIL=new Set(['ACTIVE','PROBABLE','QUESTIONABLE','DOUBTFUL','OUT','UNKNOWN']);
const CONF=new Set(['A','B','C']),FRAG=new Set(['LOW','MEDIUM','HIGH']);
const METHODS=new Set(['QBASE_RUNTIME_SCORE','QBASE_MINUTES_RECOMPUTE','EMPIRICAL_ROLE_SPLIT','PRIOR_COMP_TRANSLATION']);
const SERVER_QBASE_SOURCES=new Set(['SERVER_QBASE_RUNTIME_SCORE','PRIOR_COMP_TRANSLATION']);
const HASH64=/^[0-9a-f]{64}$/;
function sourceIds(value,known,label){
  requireThat(Array.isArray(value)&&value.length>0,`${label} evidence_source_ids required`);
  const ids=value.map(String).map(x=>x.trim()).filter(Boolean);requireThat(ids.length>0,`${label} evidence_source_ids required`);
  for(const id of ids) requireThat(known.has(id),`${label} unknown source id ${id}`); return ids;
}
function playerKey(row){const id=String(row.player_id||'').trim(); if(id) return `id:${id}`; const name=String(row.player_name||'').toLowerCase().replace(/[^a-z0-9]+/g,''); requireThat(name,'player identity required'); return `name:${name}`;}
export function validateResearchContext(c){
  requireThat(c&&typeof c==='object','research context required');
  requireThat(c.schema_version==='nbl_fixture_research_v1','research schema invalid');
  requireThat(c.market_data===false,'research must declare market_data=false');
  requireThat(marketKeyHits(c).length===0,'research market boundary failed');
  const requiredStats=new Set(requestedHeads(String(c.run_mode||'').toUpperCase()));
  requireThat(String(c.fixture_id||'')&&String(c.pack_revision||''),'fixture_id/pack_revision required');
  requireThat(c.sources&&typeof c.sources==='object'&&Object.keys(c.sources).length>0,'research sources required');
  const known=new Set(Object.keys(c.sources));
  for(const [id,s] of Object.entries(c.sources)){
    requireThat(/^https:\/\//.test(String(s.url||'')),`source ${id} requires https url`);
    requireThat(String(s.title||'')&&Number.isFinite(Date.parse(s.checked_at)),`source ${id} receipt invalid`);
  }
  requireThat(c.fixture_context&&Array.isArray(c.fixture_context.source_ids),'fixture_context required');
  sourceIds(c.fixture_context.source_ids,known,'fixture_context');
  requireThat(Array.isArray(c.players)&&c.players.length>0,'research players required');
  const seen=new Set(); for(const [i,p] of c.players.entries()){
    const key=playerKey(p); requireThat(!seen.has(key),`duplicate research player ${key}`);seen.add(key);
    requireThat(String(p.player_name||'')&&String(p.team||''),`players[${i}] identity/team required`);
    requireThat(AVAIL.has(String(p.availability_status||'').toUpperCase()),`players[${i}] availability invalid`);
    sourceIds(p.availability_source_ids,known,`players[${i}] availability`);
    const m=p.projected_minutes||{},lo=Number(m.low),mid=Number(m.mean),hi=Number(m.high);
    requireThat([lo,mid,hi].every(Number.isFinite)&&0<=lo&&lo<=mid&&mid<=hi&&hi<=50,`players[${i}] minutes invalid`);
    sourceIds(m.source_ids,known,`players[${i}] projected_minutes`);
    requireThat(p.role&&Array.isArray(p.role.source_ids),`players[${i}] role required`); sourceIds(p.role.source_ids,known,`players[${i}] role`);
    const statContext=p.stat_context;requireThat(statContext&&typeof statContext==='object'&&!Array.isArray(statContext),`players[${i}] stat_context required`);
    for(const stat of Object.keys(statContext)) requireThat(stat==='assists'||stat==='rebounds',`players[${i}] stat_context invalid stat ${stat}`);
    for(const stat of requiredStats){
      const ctx=statContext[stat];requireThat(ctx&&typeof ctx==='object'&&!Array.isArray(ctx),`players[${i}] stat_context missing requested head ${stat}`);
      sourceIds(ctx.source_ids,known,`players[${i}] stat_context.${stat}`);
      requireThat(Array.isArray(ctx.notes)&&ctx.notes.map(String).some(x=>x.trim()),`players[${i}] stat_context.${stat} research note required`);
    }
    for(const [stat,ctx] of Object.entries(statContext)){
      requireThat(ctx&&typeof ctx==='object'&&!Array.isArray(ctx),`players[${i}] stat_context.${stat} invalid`);
      sourceIds(ctx.source_ids,known,`players[${i}] stat_context.${stat}`);
      requireThat(Array.isArray(ctx.notes)&&ctx.notes.map(String).some(x=>x.trim()),`players[${i}] stat_context.${stat} research note required`);
    }
  }
  return c;
}
function qbaseContract(a,stat){
  requireThat(a&&a.market_data===false&&marketKeyHits(a).length===0,`${stat} QBASE market boundary failed`);
  requireThat(a.stat_type===stat,`${stat} QBASE stat mismatch`);
  const alpha=Number(a.walk_forward?.nb2_alpha_oos),max=Number(a.probability_contract?.max_count);
  requireThat(Number.isFinite(alpha)&&alpha>0,`${stat} QBASE alpha invalid`);requireThat(Number.isInteger(max)&&max>=5&&max<=60,`${stat} QBASE max_count invalid`);
  return {stat_type:stat,model_name:a.model_name,model_version:a.model_version,feature_schema:a.feature_schema,dispersion_alpha:alpha,max_count:max};
}
function serverAttestation(head,key,stat){
  const source=String(head.server_qbase_source||'').toUpperCase();
  requireThat(SERVER_QBASE_SOURCES.has(source),`${key}.${stat} server_qbase_source invalid`);
  const receipt=head.server_qbase_receipt_sha256==null?null:String(head.server_qbase_receipt_sha256);
  const priorKey=head.server_player_prior_key==null?null:String(head.server_player_prior_key).trim();
  if(source==='SERVER_QBASE_RUNTIME_SCORE'){
    requireThat(HASH64.test(receipt||''),`${key}.${stat} server QBASE receipt required`);
    requireThat(Boolean(priorKey),`${key}.${stat} server player prior key required`);
  }else{
    requireThat(receipt===null||receipt==='',`${key}.${stat} translated head cannot claim server QBASE receipt`);
    requireThat(priorKey===null||priorKey==='',`${key}.${stat} translated head cannot claim NBL player prior key`);
  }
  return {source,receipt_sha256:receipt||null,player_prior_key:priorKey||null};
}
export async function computeFreeze(research,qbases,projections,frozenAt=new Date().toISOString()){
  validateResearchContext(research); requireThat(marketKeyHits(projections).length===0,'projection market boundary failed');
  const heads=requestedHeads(String(research.run_mode).toUpperCase()),known=new Set(Object.keys(research.sources));
  const q={}; for(const stat of heads){q[stat]=qbaseContract(qbases[stat],stat);q[stat].qbase_sha256=await sha256Json(qbases[stat]);}
  const rmap=new Map(research.players.map(p=>[playerKey(p),p])); requireThat(Array.isArray(projections)&&projections.length>0,'projections required');
  const frozenPlayers=[],seen=new Set();
  for(const projection of projections){
    const key=playerKey(projection);requireThat(!seen.has(key),`duplicate modeled player ${key}`);seen.add(key);
    const rp=rmap.get(key);requireThat(rp,`modeled player ${key} missing research`);requireThat(String(rp.player_name)===String(projection.player_name)&&String(rp.team)===String(projection.team),'modeled player identity mismatch');
    requireThat(String(rp.availability_status).toUpperCase()!=='OUT',`cannot freeze OUT player ${rp.player_name}`);
    const supplied=projection.heads||{}; for(const h of heads) requireThat(supplied[h],`${key} missing requested head ${h}`);
    for(const h of Object.keys(supplied)) requireThat(heads.includes(h),`${key} unexpected head ${h}`);
    const outHeads={};
    for(const stat of heads){
      const h=supplied[stat],qbaseMean=Number(h.qbase_mean);requireThat(Number.isFinite(qbaseMean)&&qbaseMean>=0&&qbaseMean<=50,`${key}.${stat} qbase_mean invalid`);
      const attestation=serverAttestation(h,key,stat);
      const confidence=String(h.confidence||'').toUpperCase(),fragility=String(h.fragility||'').toUpperCase();requireThat(CONF.has(confidence)&&FRAG.has(fragility),`${key}.${stat} confidence/fragility invalid`);
      requireThat(Array.isArray(h.scenarios)&&h.scenarios.length>0,`${key}.${stat} scenarios required`);let sum=0,weighted=0;const ids=new Set(),ledger=[];
      for(const s of h.scenarios){
        const id=String(s.id||''),w=Number(s.weight),mean=Number(s.mean),method=String(s.method||'').toUpperCase();requireThat(id&&!ids.has(id),'scenario id invalid');ids.add(id);
        requireThat(Number.isFinite(w)&&w>0&&w<=1&&Number.isFinite(mean)&&mean>=0&&mean<=50,'scenario weight/mean invalid');requireThat(METHODS.has(method),'scenario method invalid');
        const evidence=sourceIds(s.evidence_source_ids,known,`${key}.${stat}.${id}`),receipt=String(s.quant_input_receipt_sha256||'');requireThat(HASH64.test(receipt),`${key}.${stat}.${id} quant input receipt required`);
        ledger.push({id,weight:w,mean,method,evidence_source_ids:evidence,assumptions:Array.isArray(s.assumptions)?s.assumptions.map(String):[],quant_input_receipt_sha256:receipt});sum+=w;weighted+=w*mean;
      }
      requireThat(Math.abs(sum-1)<=1e-9,'scenario weights must sum to 1');
      let alpha=q[stat].dispersion_alpha,dispersion_source='QBASE_TEMPORAL_OOS';
      if(attestation.source==='PRIOR_COMP_TRANSLATION'){
        requireThat(ledger.every(x=>x.method==='PRIOR_COMP_TRANSLATION'),`${key}.${stat} translated head must use PRIOR_COMP_TRANSLATION scenarios only`);
        requireThat(h.dispersion_override!==undefined,`${key}.${stat} translated head requires dispersion override`);
      }
      if(h.dispersion_override!==undefined){
        const d=h.dispersion_override||{},a=Number(d.alpha);requireThat(ledger.some(x=>x.method==='PRIOR_COMP_TRANSLATION'),'dispersion override only permitted for prior-comp translation');
        requireThat(d.method==='MAX_QBASE_PRIOR_COMP'&&HASH64.test(String(d.receipt_sha256||'')),'dispersion override receipt invalid');requireThat(Number.isFinite(a)&&a>=alpha&&a<=5,'dispersion override may not narrow QBASE');alpha=a;dispersion_source=d.method;
      }
      outHeads[stat]={qbase_anchor:q[stat],qbase_mean:qbaseMean,server_quantitative_attestation:attestation,scenario_ledger:ledger,final_mean:weighted,dispersion_alpha:alpha,dispersion_source,probability_grid:probabilityGrid(weighted,alpha,q[stat].max_count),confidence,fragility};
    }
    const minutes={low:Number(rp.projected_minutes.low),mean:Number(rp.projected_minutes.mean),high:Number(rp.projected_minutes.high),source_ids:[...rp.projected_minutes.source_ids]};minutes.minutes_projection_sha256=await sha256Json(minutes);
    frozenPlayers.push({player_id:String(projection.player_id||'')||null,player_name:String(projection.player_name),team:String(projection.team),availability_status:String(rp.availability_status).toUpperCase(),role:rp.role,projected_minutes:minutes,heads:outHeads});
  }
  frozenPlayers.sort((a,b)=>(a.team+'\0'+a.player_name).localeCompare(b.team+'\0'+b.player_name));
  const core={schema_version:'nbl_dual_head_freeze_v1',market_data:false,status:'FROZEN',run_mode:String(research.run_mode).toUpperCase(),requested_heads:heads,fixture_id:String(research.fixture_id),pack_revision:String(research.pack_revision),research_context_sha256:await sha256Json(research),qbase_sha256:Object.fromEntries(heads.map(h=>[h,q[h].qbase_sha256])),frozen_at:frozenAt,players:frozenPlayers,audits:{market_boundary:'PASS',research_binding:'PASS',server_qbase_authority:'PASS',scenario_weighting:'PASS',probability_grid:'PASS',atomic_requested_heads:'PASS'}};
  requireThat(marketKeyHits(core).length===0,'frozen market boundary failed');return {...core,freeze_receipt_sha256:await sha256Json(core)};
}
