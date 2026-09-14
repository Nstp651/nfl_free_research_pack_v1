import test from 'node:test';
import assert from 'node:assert/strict';
import { fetchRoster, sanitizeRoster } from './roster_source.js';

function payload(){return {season:{year:2027},odds:[{x:1}],athletes:Array.from({length:6},(_,i)=>({id:String(100+i),displayName:`Player ${i}`,jersey:String(i),position:{abbreviation:i%2?'G':'F'},experience:{years:i},status:{type:'active'},injuries:i===0?[{status:'Questionable',type:{description:'Ankle'},details:{detail:'Soreness'},date:'2026-10-20'}]:[],contracts:[{salary:999999}]}))};}

test('current roster is reduced to safe identity/status fields only',()=>{const r=sanitizeRoster(payload(),{teamId:'2',expectedSeason:2027});assert.equal(r.market_data,false);assert.equal(r.athletes.length,6);assert.equal(r.athletes[0].team_id,'2');assert.equal(JSON.stringify(r).includes('salary'),false);assert.equal(JSON.stringify(r).includes('odds'),false);assert.equal(r.athletes[0].injuries[0].status,'Questionable');});
test('roster season mismatch blocks stale identity seed',()=>{assert.throws(()=>sanitizeRoster(payload(),{teamId:'2',expectedSeason:2026}),/season mismatch/);});

const json=value=>new Response(JSON.stringify(value),{headers:{'content-type':'application/json'}});
test('blocked site roster falls back to bounded ESPN core season roster',async()=>{
  const seen=[],ids=['100','101','102','103','104'];
  const fetchImpl=async value=>{
    const url=String(value);seen.push(url);
    if(url.startsWith('https://site.api.espn.com/'))return new Response('blocked',{status:403});
    if(url.includes('/teams/2/athletes?'))return json({count:5,pageIndex:1,pageSize:25,pageCount:1,items:ids.map(id=>({$ref:`http://sports.core.api.espn.com/v2/sports/basketball/leagues/nba/seasons/2027/athletes/${id}?lang=en&region=us`}))});
    const id=url.match(/\/athletes\/(\d+)/)?.[1];
    return json({id,displayName:`Player ${id}`,position:{abbreviation:'G'},experience:{years:2},status:{type:'active'},injuries:[],team:{$ref:'http://sports.core.api.espn.com/v2/sports/basketball/leagues/nba/seasons/2027/teams/2?lang=en&region=us'}});
  };
  const out=await fetchRoster('2',{expectedSeason:2027,fetchImpl,nowMs:Date.parse('2026-09-15T00:00:00Z')});
  assert.equal(out.athletes.length,5);assert.equal(out.source.fallback,'CORE_API');assert.equal(out.source.url.includes('/seasons/2027/teams/2/athletes?'),true);
  assert.equal(seen.length,7);assert.equal(seen.slice(2).every(url=>url.startsWith('https://')),true);
});

test('core fallback rejects cross-team athlete details',async()=>{
  const fetchImpl=async value=>String(value).startsWith('https://site.api.espn.com/')?new Response('blocked',{status:403}):String(value).includes('/teams/2/athletes?')?json({count:5,pageIndex:1,pageSize:25,pageCount:1,items:Array.from({length:5},(_,i)=>({$ref:`https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba/seasons/2027/athletes/${100+i}`}))}):json({id:'100',displayName:'Wrong Team',team:{$ref:'https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba/seasons/2027/teams/3'},position:{abbreviation:'G'},status:{type:'active'},injuries:[]});
  await assert.rejects(()=>fetchRoster('2',{expectedSeason:2027,fetchImpl}),/team mismatch/);
});
