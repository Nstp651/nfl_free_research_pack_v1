import test from 'node:test';
import assert from 'node:assert/strict';
import { etLeagueDate, sanitizeScoreboard, listFixturesForEtDate } from './fixture_source.js';

function payload(){return {events:[{id:'401909088',date:'2026-10-21T00:30:00Z',season:{year:2027},status:{type:{completed:false,state:'pre'}},odds:[{details:'BOS -4.5'}],competitions:[{competitors:[{homeAway:'home',team:{id:'2',displayName:'Boston Celtics',abbreviation:'BOS'}},{homeAway:'away',team:{id:'18',displayName:'New York Knicks',abbreviation:'NYK'}}]}]},{id:'4019999998',date:'2026-10-20T22:00:00Z',season:{year:2027},status:{type:{completed:true,state:'post'}},competitions:[{competitors:[{homeAway:'home',team:{id:'1',displayName:'Atlanta Hawks'}},{homeAway:'away',team:{id:'3',displayName:'New Orleans Pelicans'}}]}]}]};}

const json=value=>new Response(JSON.stringify(value),{status:200,headers:{'content-type':'application/json'}});

test('UTC fixture is assigned by America/New_York league date',()=>{assert.equal(etLeagueDate('2026-10-21T00:30:00Z'),'2026-10-20');});
test('sanitizer accepts current 9-digit and legacy 10-digit ESPN ids while stripping markets',()=>{const rows=sanitizeScoreboard(payload(),{slateDateEt:'2026-10-20',nowMs:Date.parse('2026-10-20T12:00:00Z')});assert.equal(rows.length,1);assert.equal(rows[0].game_id,'401909088');assert.deepEqual(rows[0].home_team,{id:'2',name:'Boston Celtics',abbreviation:'BOS'});assert.equal(JSON.stringify(rows).includes('odds'),false);assert.equal(JSON.stringify(rows).includes('-4.5'),false);});
test('games already started are not eligible for a new run',()=>{const rows=sanitizeScoreboard(payload(),{slateDateEt:'2026-10-20',nowMs:Date.parse('2026-10-21T01:00:00Z')});assert.equal(rows.length,0);});
test('blocked scoreboard falls back to bounded ESPN core fixture data',async()=>{
  const seen=[];
  const fetchImpl=async url=>{
    const u=String(url);seen.push(u);
    if(u.startsWith('https://site.api.espn.com/'))return new Response('blocked',{status:403});
    if(u.includes('/events?'))return json({items:[{$ref:'https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba/events/401909088'}]});
    if(u.endsWith('/events/401909088'))return json({id:'401909088',date:'2026-10-21T00:30:00Z',season:{$ref:'https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba/seasons/2027'},competitions:[{competitors:[{homeAway:'home',team:{$ref:'https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba/seasons/2027/teams/2'}},{homeAway:'away',team:{$ref:'https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba/seasons/2027/teams/18'}}]}],odds:[{details:'never expose'}]});
    if(u.endsWith('/teams/2'))return json({id:'2',displayName:'Boston Celtics',abbreviation:'BOS'});
    if(u.endsWith('/teams/18'))return json({id:'18',displayName:'New York Knicks',abbreviation:'NYK'});
    throw new Error(`unexpected URL ${u}`);
  };
  const out=await listFixturesForEtDate('2026-10-20',{nowMs:Date.parse('2026-10-20T12:00:00Z'),fetchImpl});
  assert.equal(seen.length,5);assert.equal(out.source.fallback,'CORE_API');assert.equal(out.fixtures[0].game_id,'401909088');assert.equal(out.fixtures[0].source,'ESPN_CORE_NON_MARKET');assert.equal(JSON.stringify(out).includes('never expose'),false);
});
test('core fallback rejects untrusted references before fetching them',async()=>{
  const fetchImpl=async url=>String(url).startsWith('https://site.api.espn.com/')?new Response('blocked',{status:403}):json({items:[{$ref:'https://evil.example/events/401909088'}]});
  await assert.rejects(()=>listFixturesForEtDate('2026-10-20',{nowMs:Date.parse('2026-10-20T12:00:00Z'),fetchImpl}),/core ref invalid/);
});
