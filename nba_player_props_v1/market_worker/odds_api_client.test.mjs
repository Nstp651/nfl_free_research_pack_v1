import test from 'node:test';
import assert from 'node:assert/strict';
import { normalizeIdentity, resolveOddsEvents, parseEventOdds, validateGrantAgainstFreeze } from './odds_api_client.js';

const H='a'.repeat(64);
function grid(){return {half_point_grid:[{line:5.5,over:.52,push:0,under:.48}],integer_push_grid:[{line:5,over:.58,push:.12,under:.30}]};}
function freeze(){return {schema_version:'nba_slate_freeze_v1',status:'FROZEN',market_data:false,slate_date_et:'2026-10-20',run_mode:'BOTH',eligible_game_ids:['4019999999'],frozen_at:'2026-10-20T12:00:00Z',freeze_receipt_sha256:H,games:[{game_id:'4019999999',fixture:{season:2027,home_team:{id:'2',name:'Boston Celtics'},away_team:{id:'18',name:'New York Knicks'},start_time_utc:'2026-10-21T00:00:00Z'},players:[{player_id:'100',player_name:'Test Guard Jr.',heads:{assists:{probability_grid:grid()},rebounds:{probability_grid:grid()}}}]}]};}
function grant(){return {schema_version:'nba_market_access_grant_v1',run_id:'run-1',slate_date_et:'2026-10-20',run_mode:'BOTH',frozen_at:'2026-10-20T12:00:00Z',freeze_receipt_sha256:H,allowed_game_ids:['4019999999'],invalidated_game_ids:[]};}

test('grant must identify exact immutable freeze',()=>{assert.equal(validateGrantAgainstFreeze(grant(),freeze()),true);const g=grant();g.freeze_receipt_sha256='b'.repeat(64);assert.throws(()=>validateGrantAgainstFreeze(g,freeze()),/receipt mismatch/);});

test('Odds API event resolution requires exact home away and tight kickoff match',()=>{const events=[{id:'odds-1',sport_key:'basketball_nba',commence_time:'2026-10-21T00:05:00Z',home_team:'Boston Celtics',away_team:'New York Knicks'}];const r=resolveOddsEvents(freeze(),grant(),events);assert.equal(r['4019999999'].odds_event_id,'odds-1');assert.equal(r['4019999999'].kickoff_delta_seconds,300);const swapped=[{...events[0],home_team:'New York Knicks',away_team:'Boston Celtics'}];assert.throws(()=>resolveOddsEvents(freeze(),grant(),swapped),/found 0/);});

test('player identity normalizer tolerates suffix punctuation but not guessing',()=>{assert.equal(normalizeIdentity('Test Guard Jr.'),normalizeIdentity('Test Guard'));assert.notEqual(normalizeIdentity('Test Guard'),normalizeIdentity('Other Guard'));});

test('Odds API parser keeps exact modeled Overs and records unmodeled players',()=>{const payload={id:'odds-1',bookmakers:[{key:'book',title:'Book',last_update:'2026-10-20T12:01:00Z',markets:[{key:'player_assists',outcomes:[{name:'Over',description:'Test Guard',point:5.5,price:1.95},{name:'Under',description:'Test Guard',point:5.5,price:1.87},{name:'Over',description:'Someone Else',point:3.5,price:2.0}]},{key:'player_rebounds_alternate',outcomes:[{name:'Over',description:'Test Guard Jr.',point:5,price:2.2}]}]}]};const out=parseEventOdds(payload,freeze().games[0],'2026-10-20T12:02:00Z');assert.equal(out.quotes.length,2);assert.deepEqual(out.quotes.map(x=>x.side),['over','over']);assert.deepEqual(out.quotes.map(x=>x.stat_type),['assists','rebounds']);assert.equal(out.issues.filter(x=>x.type==='UNMODELED_PLAYER').length,1);});
