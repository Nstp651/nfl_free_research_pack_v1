/** Post-freeze The Odds API gateway for NBA Assists + Rebounds V1. */
import { NBA_PROP_MARKETS } from './odds_api_budget.js';

const SPORT='basketball_nba';
const API_ROOT='https://api.the-odds-api.com/v4';
const need=(ok,msg)=>{if(!ok) throw new Error(msg);};
const HASH64=/^[0-9a-f]{64}$/;
const MARKET_TO_HEAD=Object.freeze({
  player_assists:'assists',
  player_assists_alternate:'assists',
  player_rebounds:'rebounds',
  player_rebounds_alternate:'rebounds',
});

export function normalizeIdentity(value){
  return String(value||'').normalize('NFKD').replace(/[\u0300-\u036f]/g,'').toLowerCase()
    .replace(/\blos angeles\b/g,'la').replace(/\b(jr|sr|ii|iii|iv)\b\.?/g,'')
    .replace(/[^a-z0-9]+/g,'').trim();
}

export function validateGrantAgainstFreeze(grant,freeze){
  need(grant?.schema_version==='nba_market_access_grant_v1','market access grant invalid');
  need(freeze?.schema_version==='nba_slate_freeze_v1'&&freeze.status==='FROZEN','immutable slate freeze required');
  need(HASH64.test(String(grant.freeze_receipt_sha256||'')),'market grant freeze receipt invalid');
  need(grant.freeze_receipt_sha256===freeze.freeze_receipt_sha256,'market grant/freeze receipt mismatch');
  need(grant.run_mode===freeze.run_mode&&grant.slate_date_et===freeze.slate_date_et,'market grant/freeze identity mismatch');
  need(grant.frozen_at===freeze.frozen_at,'market grant/freeze timestamp mismatch');
  const frozenIds=new Set(freeze.eligible_game_ids.map(String));
  need(Array.isArray(grant.allowed_game_ids)&&grant.allowed_game_ids.length>0,'market grant has no allowed games');
  for(const id of [...grant.allowed_game_ids,...(grant.invalidated_game_ids||[])])need(frozenIds.has(String(id)),`market grant unknown game ${id}`);
  return true;
}

function eventIdentity(event){return {home:normalizeIdentity(event?.home_team),away:normalizeIdentity(event?.away_team),time:Date.parse(String(event?.commence_time||''))};}
function fixtureIdentity(game){return {home:normalizeIdentity(game?.fixture?.home_team?.name),away:normalizeIdentity(game?.fixture?.away_team?.name),time:Date.parse(String(game?.fixture?.start_time_utc||''))};}

export function resolveOddsEvents(freeze,grant,events,{toleranceMs=15*60*1000}={}){
  validateGrantAgainstFreeze(grant,freeze);need(Array.isArray(events),'Odds API events array required');
  const eventRows=events.filter(e=>e?.id&&e?.sport_key===SPORT).map(e=>({event:e,...eventIdentity(e)}));
  const gameById=new Map(freeze.games.map(g=>[String(g.game_id),g]));const resolved={};
  for(const gameId of grant.allowed_game_ids.map(String)){
    const game=gameById.get(gameId);need(game,`frozen game missing ${gameId}`);const f=fixtureIdentity(game);need(f.home&&f.away&&Number.isFinite(f.time),`frozen fixture identity invalid ${gameId}`);
    const hits=eventRows.filter(x=>x.home===f.home&&x.away===f.away&&Number.isFinite(x.time)&&Math.abs(x.time-f.time)<=toleranceMs);
    need(hits.length===1,`Odds API event resolution ${gameId} expected 1 match, found ${hits.length}`);
    resolved[gameId]={odds_event_id:String(hits[0].event.id),commence_time:String(hits[0].event.commence_time),home_team:String(hits[0].event.home_team),away_team:String(hits[0].event.away_team),kickoff_delta_seconds:Math.round((hits[0].time-f.time)/1000)};
  }
  need(new Set(Object.values(resolved).map(x=>x.odds_event_id)).size===Object.keys(resolved).length,'Odds API event mapped to multiple frozen games');
  return resolved;
}

function frozenPlayerIndex(game){
  const map=new Map(),ambiguous=new Set();
  for(const p of game.players||[]){const key=normalizeIdentity(p.player_name);if(!key)continue;if(map.has(key)){ambiguous.add(key);map.delete(key);}else if(!ambiguous.has(key))map.set(key,p);}
  return {map,ambiguous};
}

export function parseEventOdds(eventOdds,frozenGame,capturedAt=new Date().toISOString()){
  need(eventOdds&&typeof eventOdds==='object','event odds payload required');need(String(eventOdds.id||''),'Odds API event id required');need(Number.isFinite(Date.parse(capturedAt)),'captured_at invalid');
  const {map:players,ambiguous}=frozenPlayerIndex(frozenGame);const quotes=[],issues=[];
  for(const book of eventOdds.bookmakers||[]){
    const bookmaker=String(book.title||book.key||'').trim();if(!bookmaker)continue;
    for(const market of book.markets||[]){
      const marketKey=String(market.key||'');const head=MARKET_TO_HEAD[marketKey];if(!head)continue;
      for(const outcome of market.outcomes||[]){
        if(String(outcome.name||'').toLowerCase()!=='over')continue;
        const playerName=String(outcome.description||'').trim(),identity=normalizeIdentity(playerName),player=players.get(identity);
        if(!identity||ambiguous.has(identity)){issues.push({type:'AMBIGUOUS_PLAYER_IDENTITY',bookmaker,market_key:marketKey,player_name:playerName});continue;}
        if(!player){issues.push({type:'UNMODELED_PLAYER',bookmaker,market_key:marketKey,player_name:playerName});continue;}
        if(!player.heads?.[head]){issues.push({type:'HEAD_NOT_FROZEN',bookmaker,market_key:marketKey,player_id:String(player.player_id),player_name:player.player_name,stat_type:head});continue;}
        const threshold=Number(outcome.point),price=Number(outcome.price);
        if(!Number.isFinite(threshold)||!Number.isFinite(price)||price<=1){issues.push({type:'INVALID_PRICE_OR_THRESHOLD',bookmaker,market_key:marketKey,player_name:playerName});continue;}
        quotes.push({source:'ODDS_API',odds_event_id:String(eventOdds.id),game_id:String(frozenGame.game_id),player_id:String(player.player_id),player_name:String(player.player_name),stat_type:head,side:'over',threshold,decimal_price:price,bookmaker,bookmaker_key:String(book.key||''),source_market_key:marketKey,captured_at:capturedAt,last_update:String(market.last_update||book.last_update||capturedAt)});
      }
    }
  }
  return {quotes,issues};
}

function quotaHeaders(response){
  const n=k=>{const v=response.headers.get(k);return v===null?null:Number(v);};
  return {requests_remaining:n('x-requests-remaining'),requests_used:n('x-requests-used'),requests_last:n('x-requests-last')};
}

async function getJson(url,fetchImpl){const res=await fetchImpl(url,{headers:{accept:'application/json','user-agent':'nba-player-props-market-v1/1.0'},signal:AbortSignal.timeout(15000)});const quota=quotaHeaders(res);const text=await res.text();need(res.ok,`Odds API request failed ${res.status}: ${text.slice(0,200)}`);return {value:JSON.parse(text),quota};}

export async function fetchOddsApiSlate({apiKey,freeze,grant,regions='au',fetchImpl=fetch,capturedAt=new Date().toISOString()}){
  need(String(apiKey||'').trim(),'ODDS_API_KEY required');validateGrantAgainstFreeze(grant,freeze);need(/^[a-z,]+$/.test(String(regions||'')),'Odds API regions invalid');
  const eventUrl=new URL(`${API_ROOT}/sports/${SPORT}/events`);eventUrl.searchParams.set('apiKey',apiKey);eventUrl.searchParams.set('dateFormat','iso');
  const eventResponse=await getJson(eventUrl,fetchImpl);const resolved=resolveOddsEvents(freeze,grant,eventResponse.value);const gameById=new Map(freeze.games.map(g=>[String(g.game_id),g]));const quotes=[],issues=[],quota=[];
  for(const gameId of grant.allowed_game_ids.map(String)){
    const eventId=resolved[gameId].odds_event_id,url=new URL(`${API_ROOT}/sports/${SPORT}/events/${eventId}/odds`);url.searchParams.set('apiKey',apiKey);url.searchParams.set('regions',regions);url.searchParams.set('markets',NBA_PROP_MARKETS.join(','));url.searchParams.set('oddsFormat','decimal');url.searchParams.set('dateFormat','iso');
    const result=await getJson(url,fetchImpl);quota.push({game_id:gameId,odds_event_id:eventId,...result.quota});const parsed=parseEventOdds(result.value,gameById.get(gameId),capturedAt);quotes.push(...parsed.quotes);issues.push(...parsed.issues.map(x=>({game_id:gameId,...x})));
  }
  return {schema_version:'nba_odds_api_refresh_v1',source:'ODDS_API',captured_at:capturedAt,regions,markets:[...NBA_PROP_MARKETS],freeze_receipt_sha256:freeze.freeze_receipt_sha256,event_resolution:resolved,quotes,issues,quota};
}
