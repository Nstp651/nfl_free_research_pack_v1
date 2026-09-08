/** Convert evidence-bound basketball state into typed runtime transforms. */
import { validateQbaseArtifact } from './runtime_score.js';
const need=(ok,msg)=>{if(!ok) throw new Error(msg);};
function finite(v,label){const n=Number(v);need(Number.isFinite(n),`${label} required`);return n;}

export function buildTransformsFromResearch(artifact,researchPlayer){
  validateQbaseArtifact(artifact);
  need(researchPlayer&&typeof researchPlayer==='object','research player required');
  const minutes=researchPlayer.projected_minutes||{};
  const starter=finite(researchPlayer.expected_starter_probability,'expected_starter_probability');
  const opportunity=researchPlayer.stat_context?.[artifact.head]?.current_opportunity;
  need(opportunity&&typeof opportunity==='object',`${artifact.head} current_opportunity required`);
  const transforms=[{
    type:'MINUTES_RECOMPUTE',
    projected_minutes:finite(minutes.mean,'projected_minutes.mean'),
    starter_probability:starter,
  }];
  if(artifact.head==='assists'){
    const share=finite(opportunity.expected_assist_share,'expected_assist_share');
    const team=finite(opportunity.expected_team_assists,'expected_team_assists');
    transforms.push({type:'ROLE_OPPORTUNITY_RECOMPUTE',inputs:{assist_share_l5:share,assist_share_l10:share,team_assists_l5:team,team_assists_l10:team}});
    const poss=finite(opportunity.expected_possessions,'expected_possessions');
    transforms.push({type:'LINEUP_DEPENDENCY_RECOMPUTE',inputs:{team_possessions_l5:poss,team_possessions_l10:poss}});
  }else{
    const share=finite(opportunity.expected_rebound_share,'expected_rebound_share');
    const team=finite(opportunity.expected_team_rebounds,'expected_team_rebounds');
    transforms.push({type:'ROLE_OPPORTUNITY_RECOMPUTE',inputs:{rebound_share_l5:share,rebound_share_l10:share,team_rebounds_l5:team,team_rebounds_l10:team}});
    const poss=finite(opportunity.expected_possessions,'expected_possessions');
    transforms.push({type:'LINEUP_DEPENDENCY_RECOMPUTE',inputs:{team_possessions_l5:poss,team_possessions_l10:poss}});
  }
  return transforms;
}
