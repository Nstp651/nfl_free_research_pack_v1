import test from 'node:test';
import assert from 'node:assert/strict';
import { sanitizeRoster } from './roster_source.js';

function payload(){return {season:{year:2027},odds:[{x:1}],athletes:Array.from({length:6},(_,i)=>({id:String(100+i),displayName:`Player ${i}`,jersey:String(i),position:{abbreviation:i%2?'G':'F'},experience:{years:i},status:{type:'active'},injuries:i===0?[{status:'Questionable',type:{description:'Ankle'},details:{detail:'Soreness'},date:'2026-10-20'}]:[],contracts:[{salary:999999}]}))};}

test('current roster is reduced to safe identity/status fields only',()=>{const r=sanitizeRoster(payload(),{teamId:'2',expectedSeason:2027});assert.equal(r.market_data,false);assert.equal(r.athletes.length,6);assert.equal(r.athletes[0].team_id,'2');assert.equal(JSON.stringify(r).includes('salary'),false);assert.equal(JSON.stringify(r).includes('odds'),false);assert.equal(r.athletes[0].injuries[0].status,'Questionable');});
test('roster season mismatch blocks stale identity seed',()=>{assert.throws(()=>sanitizeRoster(payload(),{teamId:'2',expectedSeason:2026}),/season mismatch/);});
