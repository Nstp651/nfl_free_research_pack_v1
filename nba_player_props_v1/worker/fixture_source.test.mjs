import test from 'node:test';
import assert from 'node:assert/strict';
import { etLeagueDate, sanitizeScoreboard } from './fixture_source.js';

function payload(){return {events:[{id:'4019999999',date:'2026-10-21T00:30:00Z',season:{year:2027},status:{type:{completed:false,state:'pre'}},odds:[{details:'BOS -4.5'}],competitions:[{competitors:[{homeAway:'home',team:{id:'2',displayName:'Boston Celtics',abbreviation:'BOS'}},{homeAway:'away',team:{id:'18',displayName:'New York Knicks',abbreviation:'NYK'}}]}]},{id:'4019999998',date:'2026-10-20T22:00:00Z',season:{year:2027},status:{type:{completed:true,state:'post'}},competitions:[{competitors:[{homeAway:'home',team:{id:'1',displayName:'Atlanta Hawks'}},{homeAway:'away',team:{id:'3',displayName:'New Orleans Pelicans'}}]}]}]};}

test('UTC fixture is assigned by America/New_York league date',()=>{assert.equal(etLeagueDate('2026-10-21T00:30:00Z'),'2026-10-20');});
test('sanitizer strips all raw market fields and completed games',()=>{const rows=sanitizeScoreboard(payload(),{slateDateEt:'2026-10-20',nowMs:Date.parse('2026-10-20T12:00:00Z')});assert.equal(rows.length,1);assert.deepEqual(rows[0].home_team,{id:'2',name:'Boston Celtics',abbreviation:'BOS'});assert.equal(JSON.stringify(rows).includes('odds'),false);assert.equal(JSON.stringify(rows).includes('-4.5'),false);});
test('games already started are not eligible for a new run',()=>{const rows=sanitizeScoreboard(payload(),{slateDateEt:'2026-10-20',nowMs:Date.parse('2026-10-21T01:00:00Z')});assert.equal(rows.length,0);});
