import {readFileSync} from 'node:fs';
import {TEAM_CHECKS,GAME_CHECKS} from './freeze_core.js';
const root=new URL('../',import.meta.url);
export const pack=JSON.parse(readFileSync(new URL('data/slates/2026/2026_01.json',root)));
export const qbase=JSON.parse(readFileSync(new URL('model/slates/2026/2026_01.json',root)));
export const now=Date.parse('2026-09-05T10:00:00Z');
export const ids=pack.games.filter(g=>!g.fixture.completed && Date.parse(g.fixture.start_utc)>now).map(g=>g.game_id).sort();
export const lock={season:2026,week:1,slate_id:'2026_01',pack_revision:pack.pack_revision,qbase_revision:qbase.qbase_revision,eligible_game_ids:ids};
export function context(gid) {
 const fx=pack.games.find(x=>x.game_id===gid).fixture;
 const evidence=()=>({finding:'SYNTHETIC CONTRACT TEST ONLY',checked_at:new Date(now).toISOString(),sources:['https://example.org/test-fixture'],unresolved:false});
 return {game_id:gid,contextual_shift:0,distribution_changed:false,scenarios:[{id:'base',weight:1,shift:0,residual_scale:1,ledger_ids:[]}],confidence:'B',fragility:'MEDIUM',ledger:[],frozen_thesis:'Synthetic test; not football research',research:{market_data:false,home_team:fx.home_team,away_team:fx.away_team,home:Object.fromEntries(TEAM_CHECKS.map(k=>[k,evidence()])),away:Object.fromEntries(TEAM_CHECKS.map(k=>[k,evidence()])),game:Object.fromEntries(GAME_CHECKS.map(k=>[k,evidence()])),deep_triggers:[],deep_evidence:[]}};
}
