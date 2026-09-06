/** Deterministic server-side QBASE inference for NBL player props V1.
 *
 * This mirrors model/runtime_score.py + model/current_features.py. It keeps the
 * Custom GPT from being authoritative for quantitative baseline means: returning
 * NBL-player baselines and minutes scenarios are recomputed from the pinned prior
 * snapshot and serialized QBASE coefficients inside the Worker.
 */
const finite=value=>{const n=Number(value);return Number.isFinite(n)?n:null;};
export const normName=value=>String(value||'').toLowerCase().replace(/[^a-z0-9]+/g,'');
const canonicalValue=v=>Array.isArray(v)?v.map(canonicalValue):(v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonicalValue(v[k])])):v);
const canonicalJson=v=>JSON.stringify(canonicalValue(v));
export async function quantSha256Json(v){
  const bytes=new TextEncoder().encode(canonicalJson(v));
  const hash=await crypto.subtle.digest('SHA-256',bytes);
  return [...new Uint8Array(hash)].map(x=>x.toString(16).padStart(2,'0')).join('');
}
const need=(condition,message)=>{if(!condition)throw new Error(message);};

export function validateSerializedQbase(artifact){
  need(artifact&&typeof artifact==='object'&&artifact.market_data===false,'QBASE artifact must declare market_data=false');
  const selected=artifact.selected_model;need(selected&&typeof selected==='object','QBASE selected_model required');
  need(['poisson','ridge_log1p'].includes(String(selected.family||'')),`unsupported serialized family ${selected.family}`);
  const arrays=['features','imputer_medians','scaler_mean','scaler_scale','coefficients'].map(k=>selected[k]);
  need(arrays.every(Array.isArray),'serialized model arrays required');
  const n=arrays[0].length;need(n>0&&arrays.slice(1).every(x=>x.length===n),'serialized model array lengths must match');
  need(new Set(arrays[0].map(String)).size===n,'serialized feature names must be unique');
  need(finite(selected.intercept)!==null,'serialized model intercept required');
  arrays[3].forEach((x,i)=>need(finite(x)!==null&&Number(x)!==0,`invalid scaler_scale[${i}]`));
  return artifact;
}

export async function scoreQbase(artifact,featureValues){
  validateSerializedQbase(artifact);need(featureValues&&typeof featureValues==='object'&&!Array.isArray(featureValues),'feature_values must be an object');
  const selected=artifact.selected_model,names=selected.features.map(String),medians=selected.imputer_medians.map(Number),centers=selected.scaler_mean.map(Number),scales=selected.scaler_scale.map(Number),coefs=selected.coefficients.map(Number);
  const resolved={},imputed=[];let eta=Number(selected.intercept);
  for(let i=0;i<names.length;i++){
    const name=names[i];let value=finite(featureValues[name]);if(value===null){value=medians[i];imputed.push(name);}resolved[name]=value;eta+=coefs[i]*((value-centers[i])/scales[i]);
  }
  let rawMean;if(selected.family==='poisson'){eta=Math.min(eta,Math.log(40));rawMean=Math.exp(eta);}else{eta=Math.min(eta,Math.log1p(40));rawMean=Math.expm1(eta);}
  const mean=Math.min(40,Math.max(0.02,rawMean));
  const receiptInput={stat_type:artifact.stat_type,model_version:artifact.model_version,feature_schema:artifact.feature_schema,selected_model_sha256:await quantSha256Json(selected),resolved_features:resolved};
  return {mean,linear_predictor:eta,imputed_features:imputed,resolved_features:resolved,quant_input_receipt_sha256:await quantSha256Json(receiptInput)};
}

function isoDate(value,field){const text=String(value||'').trim();need(text,`${field} required`);const ms=Date.parse(text);need(Number.isFinite(ms)&&/(Z|[+-]\d\d:\d\d)$/.test(text),`${field} must be ISO-8601 with timezone`);return ms;}
function daysBetween(target,previous){if(previous===null||previous===undefined||String(previous).trim()==='')return null;const days=(isoDate(target,'target_time')-isoDate(previous,'previous_time'))/86400000;need(Number.isFinite(days)&&days>=0,'target fixture precedes historical prior timestamp');return days;}
function findPlayer(snapshot,name){const players=snapshot?.players;need(players&&typeof players==='object'&&!Array.isArray(players),'prior snapshot players map missing');const key=normName(name);if(players[key]&&typeof players[key]==='object')return players[key];const matches=Object.entries(players).filter(([k,v])=>normName(k)===key&&v&&typeof v==='object').map(([,v])=>v);if(matches.length===1)return matches[0];const e=new Error(`No NBL historical prior for ${name}; prior-competition translation required`);e.code='PRIOR_COMP_TRANSLATION_REQUIRED';throw e;}
function findTeam(snapshot,name){const teams=snapshot?.teams;need(teams&&typeof teams==='object'&&!Array.isArray(teams),'prior snapshot teams map missing');const wanted=normName(name),matches=Object.entries(teams).filter(([k,v])=>normName(k)===wanted&&v&&typeof v==='object').map(([,v])=>v);need(matches.length===1,`Expected one historical team prior for ${name}, found ${matches.length}`);return matches[0];}
function seasonGames(record,targetSeason,key){const last=Number(record?.last_season_start);if(!Number.isInteger(last)||last!==Number(targetSeason))return 0;const v=finite(record?.features?.[key]);return v===null?0:v;}
function copyIf(values,target,source,sourceKey=target){const v=finite(source?.[sourceKey]);if(v!==null)values[target]=v;}

export function assembleFeatureVector(artifact,snapshot,{playerName,team,opponent,targetSeasonStart,targetTime,homeFlag}){
  need(snapshot?.market_data===false,'prior snapshot must declare market_data=false');validateSerializedQbase(artifact);
  const required=artifact.selected_model.features.map(String),player=findPlayer(snapshot,playerName),own=findTeam(snapshot,team),opp=findTeam(snapshot,opponent),pf=player.features||{},tf=own.features||{},of=opp.features||{},values={};
  for(const key of required)if(key.startsWith('player_')&&!['player_season_games_prior','player_days_rest'].includes(key))copyIf(values,key,pf);
  values.player_season_games_prior=seasonGames(player,targetSeasonStart,'player_last_season_games');const playerRest=daysBetween(targetTime,player.last_match_time);if(playerRest!==null)values.player_days_rest=playerRest;
  const ownDirect=new Set(['team_games_prior','team_points_mean_5','team_points_mean_10','team_possessions_mean_5','team_possessions_mean_10','team_assists_mean_5','team_assists_mean_10','team_fgm_mean_5','team_fgm_mean_10','team_rebounds_mean_5','team_rebounds_mean_10','team_missed_fg_mean_5','team_missed_fg_mean_10']);
  for(const key of required)if(ownDirect.has(key))copyIf(values,key,tf);values.team_season_games_prior=seasonGames(own,targetSeasonStart,'team_last_season_games');const ownRest=daysBetween(targetTime,own.last_match_time);if(ownRest!==null)values.team_days_rest=ownRest;
  const opponentMap={opponent_points_allowed_mean_5:'points_allowed_mean_5',opponent_points_allowed_mean_10:'points_allowed_mean_10',opponent_possessions_mean_5:'team_possessions_mean_5',opponent_possessions_mean_10:'team_possessions_mean_10',opponent_assists_allowed_mean_5:'assists_allowed_mean_5',opponent_assists_allowed_mean_10:'assists_allowed_mean_10',opponent_fgm_allowed_mean_5:'fgm_allowed_mean_5',opponent_fgm_allowed_mean_10:'fgm_allowed_mean_10',opponent_missed_fg_mean_5:'team_missed_fg_mean_5',opponent_missed_fg_mean_10:'team_missed_fg_mean_10',opponent_rebounds_allowed_mean_5:'rebounds_allowed_mean_5',opponent_rebounds_allowed_mean_10:'rebounds_allowed_mean_10'};
  for(const [target,source] of Object.entries(opponentMap))if(required.includes(target))copyIf(values,target,of,source);const oppRest=daysBetween(targetTime,opp.last_match_time);if(oppRest!==null)values.opponent_days_rest=oppRest;
  const hf=Number(homeFlag);need(hf===0||hf===1,'home_flag must be 0 or 1');values.home_flag=hf;
  const exact=Object.fromEntries(required.filter(k=>Object.hasOwn(values,k)).map(k=>[k,values[k]]));return {features:exact,missing_features:required.filter(k=>!Object.hasOwn(exact,k)),player_prior_key:String(player.player_key||normName(playerName)),player_last_team:player.last_team,player_last_match_time:player.last_match_time,own_team_last_match_time:own.last_match_time,opponent_last_match_time:opp.last_match_time,target_season_start:Number(targetSeasonStart),target_time:targetTime,snapshot_revision:snapshot.snapshot_revision};
}

export async function projectedMinutesScore(artifact,baseFeatures,projectedMinutes,{starterProbability=null}={}){
  const minutes=Number(projectedMinutes);need(Number.isFinite(minutes)&&minutes>=0&&minutes<=50,'projected_minutes must be finite in [0, 50]');const values={...baseFeatures},names=new Set(artifact.selected_model.features.map(String));
  for(const name of ['player_minutes_mean_3','player_minutes_mean_5','player_minutes_mean_10'])if(names.has(name))values[name]=minutes;
  if(starterProbability!==null&&starterProbability!==undefined){const starter=Number(starterProbability);need(Number.isFinite(starter)&&starter>=0&&starter<=1,'starter_probability must be in [0,1]');for(const name of ['player_start_rate_5','player_start_rate_10'])if(names.has(name))values[name]=starter;}
  const result=await scoreQbase(artifact,values);return {...result,projected_minutes:minutes,starter_probability:starterProbability,method:'QBASE_MINUTES_RECOMPUTE'};
}

export function fixtureSide(fixture,team){const wanted=normName(team),home=normName(fixture?.home_team?.name),away=normName(fixture?.away_team?.name);if(wanted===home)return {opponent:fixture.away_team.name,homeFlag:1};if(wanted===away)return {opponent:fixture.home_team.name,homeFlag:0};throw new Error(`Team ${team} is not in locked fixture`);}

export async function returningPlayerBaseline(artifact,snapshot,{playerName,team,fixture,targetSeasonStart}){
  const side=fixtureSide(fixture,team);const assembled=assembleFeatureVector(artifact,snapshot,{playerName,team,opponent:side.opponent,targetSeasonStart,targetTime:fixture.start_time,homeFlag:side.homeFlag});const score=await scoreQbase(artifact,assembled.features);return {...score,missing_features:assembled.missing_features,feature_context:{player_prior_key:assembled.player_prior_key,player_last_match_time:assembled.player_last_match_time,own_team_last_match_time:assembled.own_team_last_match_time,opponent_last_match_time:assembled.opponent_last_match_time,snapshot_revision:assembled.snapshot_revision}};
}
