/** Assemble exact pregame QBASE feature priors from the accepted-history runtime pack. */
import { sha256Json, validateQbaseArtifact } from './runtime_score.js';
const need=(ok,msg)=>{if(!ok) throw new Error(msg);};
const DAY=86_400_000;
const clip=(v,lo,hi)=>Math.max(lo,Math.min(hi,v));
const countForSeason=(row,season)=>Number(row?.games_by_season?.[String(season)]||0);
const value=(v)=>Number.isFinite(Number(v))?Number(v):null;

function opponentTeamId(fixture,currentTeamId){
  const home=String(fixture?.home_team?.id||''),away=String(fixture?.away_team?.id||'');
  need(home&&away&&home!==away,'fixture team identity invalid');
  if(String(currentTeamId)===home)return away;
  if(String(currentTeamId)===away)return home;
  throw new Error('player team not in fixture');
}
function daysBetween(startIso,endIso,label){const a=Date.parse(String(startIso||'')),b=Date.parse(String(endIso||''));need(Number.isFinite(a)&&Number.isFinite(b),`${label} timestamps invalid`);need(b>a,`${label} prior timestamp must precede fixture`);return (b-a)/DAY;}

export function assembleBaseFeatures(priorPack,researchPlayer,fixture){
  need(priorPack?.schema_version==='nba_runtime_prior_pack_v1'&&priorPack.market_data===false,'runtime prior pack invalid');
  const playerId=String(researchPlayer?.player_id||''),teamId=String(researchPlayer?.team_id||''),season=Number(fixture?.season),fixtureStart=String(fixture?.start_time_utc||'');
  need(playerId&&teamId&&Number.isInteger(season),'runtime prior identity invalid');
  const player=priorPack.players?.[playerId];if(!player)return null;
  const opponentId=opponentTeamId(fixture,teamId),team=priorPack.teams?.[teamId],opponent=priorPack.teams?.[opponentId];
  need(team,`current team prior missing ${teamId}`);need(opponent,`opponent team prior missing ${opponentId}`);
  const playerDays=clip(daysBetween(player.last_game_start_utc,fixtureStart,'player'),0,60);
  const teamDays=daysBetween(team.last_game_start_utc,fixtureStart,'team');
  daysBetween(opponent.last_game_start_utc,fixtureStart,'opponent');
  const f={
    season_games_before:countForSeason(player,season),
    team_games_before:countForSeason(team,season),
    team_rest_days:clip(teamDays-1,0,14),
    player_days_since_last_game:playerDays,
    team_changed_since_last_game:String(player.last_team_id)===teamId?0:1,
    ...player.features,
    team_possessions_l5:value(team.features?.team_possessions_l5),team_possessions_l10:value(team.features?.team_possessions_l10),
    team_assists_l5:value(team.features?.team_assists_l5),team_assists_l10:value(team.features?.team_assists_l10),
    team_rebounds_l5:value(team.features?.team_rebounds_l5),team_rebounds_l10:value(team.features?.team_rebounds_l10),
    opponent_assists_allowed_l5:value(opponent.features?.assists_allowed_l5),opponent_assists_allowed_l10:value(opponent.features?.assists_allowed_l10),
    opponent_rebounds_allowed_l5:value(opponent.features?.rebounds_allowed_l5),opponent_rebounds_allowed_l10:value(opponent.features?.rebounds_allowed_l10),
  };
  return {player_id:playerId,current_team_id:teamId,opponent_team_id:opponentId,last_team_id:String(player.last_team_id),feature_context:f};
}

export async function buildPriorSnapshotsForResearch(priorPack,research,qbaseArtifacts){
  need(research?.market_data===false,'research must be market blind');const heads=research.run_mode==='BOTH'?['assists','rebounds']:(research.run_mode==='ASSISTS_ONLY'?['assists']:['rebounds']);const out=[];
  for(const rp of research.players||[]){const assembled=assembleBaseFeatures(priorPack,rp,research.fixture);if(!assembled)continue;const row={player_id:String(rp.player_id),heads:{}};
    for(const head of heads){const artifact=qbaseArtifacts[head];validateQbaseArtifact(artifact,head);const base={};for(const name of artifact.features)base[name]=assembled.feature_context[name]??null;const receiptInput={schema_version:'nba_player_prior_snapshot_v1',market_data:false,prior_pack_sha256:priorPack.pack_sha256,history_sha256:priorPack.history_sha256,player_id:row.player_id,head,fixture_game_id:research.game_id,fixture_start_time_utc:research.fixture.start_time_utc,current_team_id:assembled.current_team_id,opponent_team_id:assembled.opponent_team_id,last_team_id:assembled.last_team_id,base_features:base};row.heads[head]={prior_snapshot_sha256:await sha256Json(receiptInput),base_features:base};}
    out.push(row);
  }
  return out;
}
