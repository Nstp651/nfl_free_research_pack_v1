import test from 'node:test';
import assert from 'node:assert/strict';
import {fetchEventsDiscovery} from './index_v130.js';

const fixture={start_time:'2026-09-19T09:30:00Z',home_team:{name:'Melbourne United'},away_team:{name:'Adelaide 36ers'}};

test('filtered discovery uses Odds API second-precision commence time format',async()=>{
  const original=globalThis.fetch;const calls=[];
  globalThis.fetch=async input=>{const url=String(input);calls.push(url);return new Response(JSON.stringify([]),{status:200,headers:{'content-type':'application/json','x-requests-last':'1','x-requests-used':'216','x-requests-remaining':'284'}});};
  try{const out=await fetchEventsDiscovery({ODDS_API_KEY:'test-key'},fixture);assert.equal(out.ok,true);assert.equal(out.mode,'windowed');assert.equal(calls.length,1);const url=new URL(calls[0]);assert.equal(url.searchParams.get('commenceTimeFrom'),'2026-09-18T09:30:00Z');assert.equal(url.searchParams.get('commenceTimeTo'),'2026-09-20T09:30:00Z');assert.ok(!url.searchParams.get('commenceTimeFrom').includes('.000Z'));assert.ok(!url.searchParams.get('commenceTimeTo').includes('.000Z'));}
  finally{globalThis.fetch=original;}
});

test('filtered 422 exposes provider error and retries unfiltered discovery once',async()=>{
  const original=globalThis.fetch;const calls=[];
  globalThis.fetch=async input=>{const url=String(input);calls.push(url);if(url.includes('commenceTimeFrom='))return new Response(JSON.stringify({error_code:'INVALID_PARAMETER',message:'commenceTimeFrom rejected'}),{status:422,headers:{'content-type':'application/json','x-requests-last':'0','x-requests-used':'215','x-requests-remaining':'285'}});return new Response(JSON.stringify([]),{status:200,headers:{'content-type':'application/json','x-requests-last':'1','x-requests-used':'216','x-requests-remaining':'284'}});};
  try{const out=await fetchEventsDiscovery({ODDS_API_KEY:'test-key'},fixture);assert.equal(out.ok,true);assert.equal(out.mode,'unfiltered_retry');assert.equal(out.body.length,0);assert.equal(out.attempts.length,1);assert.equal(out.attempts[0].http_status,422);assert.equal(out.attempts[0].error_code,'INVALID_PARAMETER');assert.match(out.attempts[0].message,/rejected/);assert.equal(calls.length,2);assert.ok(calls[0].includes('commenceTimeFrom='));assert.ok(!calls[1].includes('commenceTimeFrom='));}
  finally{globalThis.fetch=original;}
});
