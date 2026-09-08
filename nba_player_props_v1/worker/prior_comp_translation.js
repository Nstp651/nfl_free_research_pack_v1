/** Controlled prior-competition translation for NBA V1 newcomers. */
const need=(ok,msg)=>{if(!ok)throw new Error(msg)};
const finite=v=>{const n=Number(v);return Number.isFinite(n)?n:null};
const clamp=(v,lo,hi,f)=>{const n=finite(v);need(n!==null&&n>=lo&&n<=hi,`${f} must be in [${lo}, ${hi}]`);return n};
const allowedCompetitions=new Set(['NCAA_D1','G_LEAGUE','EUROLEAGUE','EUROCUP','NBL_AU','ACB','BSL','LNB_PRO_A','BBL_DE','LEGABASKET','OTHER_VALIDATED']);

export function validateTranslationArtifact(artifact,head){
  need(artifact&&typeof artifact==='object','translation artifact required');
  need(artifact.status==='PROMOTED','prior-competition translation artifact is not promoted');
  need(artifact.market_data===false,'translation artifact must be market blind');
  need(artifact.head===head,'translation head mismatch');
  need(Array.isArray(artifact.routes)&&artifact.routes.length>0,'translation routes required');
  for(const r of artifact.routes){
    need(allowedCompetitions.has(String(r.competition)),'unsupported competition route');
    need(finite(r.intercept)!==null&&finite(r.log_rate_coef)!==null&&finite(r.minutes_coef)!==null,'route coefficients required');
    need(finite(r.uncertainty_multiplier)!==null&&Number(r.uncertainty_multiplier)>=1,'uncertainty multiplier must be >=1');
    need(Number.isInteger(r.min_sample_games)&&r.min_sample_games>=1,'min_sample_games required');
  }
  return artifact;
}

export function translatePrior(artifact,{competition,games,minutes_per_game,stat_per_min,role_share=null}){
  validateTranslationArtifact(artifact,artifact.head);
  const route=artifact.routes.find(r=>String(r.competition)===String(competition));
  need(route,`no empirically validated route for ${competition}`);
  need(Number.isInteger(Number(games))&&Number(games)>=route.min_sample_games,`insufficient ${competition} sample`);
  const mpg=clamp(minutes_per_game,0,48,'minutes_per_game');
  const rate=clamp(stat_per_min,0,2,'stat_per_min');
  const share=role_share===null||role_share===undefined?0:clamp(role_share,0,1,'role_share');
  const logRate=Math.log(Math.max(rate,1e-6));
  const eta=Number(route.intercept)+Number(route.log_rate_coef)*logRate+Number(route.minutes_coef)*(mpg/36)+Number(route.role_share_coef||0)*share;
  const translatedRate=Math.max(0.0001,Math.min(2,Math.exp(eta)));
  return {competition:String(competition),translated_stat_per_min:translatedRate,uncertainty_multiplier:Number(route.uncertainty_multiplier),sample_games:Number(games),method:'PRIOR_COMP_TRANSLATION',route_version:String(route.version||artifact.version||'unknown')};
}

export function buildPriorCompFeaturePatch(head,translation,projectedMinutes){
  need(['assists','rebounds'].includes(head),'head required');
  const minutes=clamp(projectedMinutes,0,48,'projected_minutes');
  need(translation&&translation.method==='PRIOR_COMP_TRANSLATION','validated translation required');
  const rate=clamp(translation.translated_stat_per_min,0,2,'translated_stat_per_min');
  const expected=rate*minutes;
  if(head==='assists') return {minutes_l3:minutes,minutes_l5:minutes,minutes_l10:minutes,minutes_l20:minutes,assists_per_min_l5:rate,assists_per_min_l10:rate,assists_l3:expected,assists_l5:expected,assists_l10:expected,assists_l20:expected};
  return {minutes_l3:minutes,minutes_l5:minutes,minutes_l10:minutes,minutes_l20:minutes,rebounds_per_min_l5:rate,rebounds_per_min_l10:rate,rebounds_l3:expected,rebounds_l5:expected,rebounds_l10:expected,rebounds_l20:expected};
}
