const finite=x=>Number.isFinite(Number(x));
const norm=x=>String(x||'').normalize('NFKD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,'');
const round3=x=>Math.round(Number(x)*1000)/1000;
function maxFinite(values){const xs=values.filter(finite).map(Number);return xs.length?Math.max(...xs):null;}
function median(values){const xs=values.filter(finite).map(Number).sort((a,b)=>a-b);if(!xs.length)return null;const m=Math.floor(xs.length/2);return xs.length%2?xs[m]:(xs[m-1]+xs[m])/2;}
export function researchPriority(priorNbl,currentTeam){
  if(!priorNbl)return {research_priority:'DEEP',research_priority_reason:'NO_NBL_PRIOR',prior_minutes_peak:null};
  const f=priorNbl.features||{},peak=maxFinite([f.player_minutes_mean_3,f.player_minutes_mean_5,f.player_minutes_mean_10]);
  if(norm(priorNbl.last_team)!==norm(currentTeam))return {research_priority:'DEEP',research_priority_reason:'TEAM_CHANGE',prior_minutes_peak:peak};
  if(peak!==null&&peak>=18)return {research_priority:'DEEP',research_priority_reason:'ESTABLISHED_ROTATION',prior_minutes_peak:peak};
  if(peak!==null&&peak>=9)return {research_priority:'SCREEN',research_priority_reason:'FRINGE_ROTATION',prior_minutes_peak:peak};
  return {research_priority:'LOW',research_priority_reason:'LOW_HISTORICAL_MINUTES',prior_minutes_peak:peak};
}
export function projectionAnchor(priorPlayer,stat,projectedMinutes){
  const f=priorPlayer?.features||{},prefix=`player_${stat}`;
  const mean3=finite(f[`${prefix}_mean_3`])?Number(f[`${prefix}_mean_3`]):null;
  const mean5=finite(f[`${prefix}_mean_5`])?Number(f[`${prefix}_mean_5`]):null;
  const mean10=finite(f[`${prefix}_mean_10`])?Number(f[`${prefix}_mean_10`]):null;
  const rate5=finite(f[`${prefix}_per_min_mean_5`])?Number(f[`${prefix}_per_min_mean_5`]):null;
  const rate10=finite(f[`${prefix}_per_min_mean_10`])?Number(f[`${prefix}_per_min_mean_10`]):null;
  const pm=finite(projectedMinutes)?Number(projectedMinutes):maxFinite([f.player_minutes_mean_3,f.player_minutes_mean_5,f.player_minutes_mean_10]);
  const rateMeans=pm===null?[]:[rate5,rate10].filter(finite).map(r=>r*pm);
  return {robust_anchor:median([mean5,mean10,...rateMeans]),recent_peak:maxFinite([mean3,mean5,mean10]),rate_anchor:median(rateMeans),projected_minutes:pm};
}
export function projectionSanity({playerName,stat,method,mean,priorPlayer,projectedMinutes,seasonGamesPrior=0,confidence,fragility}){
  if(!priorPlayer||method==='PRIOR_COMP_TRANSLATION')return {status:'NOT_APPLICABLE'};
  const a=projectionAnchor(priorPlayer,stat,projectedMinutes);if(!finite(a.robust_anchor)||Number(a.robust_anchor)<=0)return {status:'NO_ANCHOR'};
  const anchor=Number(a.robust_anchor),opening=Number(seasonGamesPrior||0)<3,absAllowance=stat==='assists'?1.75:2.5,stableFactor=opening?1.45:1.55,stableCeiling=Math.max(anchor*stableFactor,anchor+absAllowance),roleCeiling=Math.max(anchor*1.80,anchor+2*absAllowance),value=Number(mean);
  let error=null;
  if(method==='QBASE_RUNTIME_SCORE'||method==='QBASE_MINUTES_RECOMPUTE'){
    if(value>stableCeiling+1e-9)error=`${playerName}.${stat} projection sanity failed: ${method} mean ${round3(value)} exceeds ${opening?'opening-season ':''}stable-role ceiling ${round3(stableCeiling)} from robust prior anchor ${round3(anchor)}; use an evidence-backed EMPIRICAL_ROLE_SPLIT or exclude the head`;
  }else if(method==='EMPIRICAL_ROLE_SPLIT'){
    if(value>roleCeiling+1e-9)error=`${playerName}.${stat} projection sanity failed: EMPIRICAL_ROLE_SPLIT mean ${round3(value)} exceeds evidence envelope ${round3(roleCeiling)} from robust prior anchor ${round3(anchor)}`;
    else if(value>stableCeiling+1e-9&&String(fragility||'').toUpperCase()!=='HIGH')error=`${playerName}.${stat} role-split beyond stable envelope requires HIGH fragility`;
    else if(value>stableCeiling+1e-9&&String(confidence||'').toUpperCase()==='A')error=`${playerName}.${stat} role-split beyond stable envelope cannot use Confidence A`;
  }
  return {status:error?'FAIL':'PASS',error,anchor:round3(anchor),recent_peak:finite(a.recent_peak)?round3(a.recent_peak):null,rate_anchor:finite(a.rate_anchor)?round3(a.rate_anchor):null,stable_ceiling:round3(stableCeiling),role_ceiling:round3(roleCeiling),opening_regime:opening};
}
