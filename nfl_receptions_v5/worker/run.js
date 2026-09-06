import {computeFrozenModel, exactKeys, requireThat, sha256Hex, evidenceIdSet} from './model_core.js';

const REPO = 'Nstp651/nfl_free_research_pack_v1';
const DATA_ROOT = `https://raw.githubusercontent.com/${REPO}/main/nfl_free_research_pack_v1/data/`;
const MAX_AGE_MS = 36 * 3600_000;

export function reply(value, status = 200) {
  return new Response(JSON.stringify(value), {status, headers: {
    'content-type': 'application/json; charset=utf-8',
    'cache-control': 'no-store',
    'access-control-allow-origin': '*',
  }});
}

function integer(value, min, max, fallback) {
  if ((value === null || value === undefined) && fallback !== undefined) return fallback;
  requireThat(/^\d+$/.test(String(value || '')), 'Invalid integer parameter');
  const n = Number(value);
  requireThat(Number.isSafeInteger(n) && n >= min && n <= max, 'Integer parameter outside allowed range');
  return n;
}

async function readJson(url) {
  const allowed = url === `${DATA_ROOT}manifest.json` ||
    new RegExp(`^${DATA_ROOT.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}games/\\d{4}/\\d{4}_\\d{2}_[A-Z0-9]{2,4}_[A-Z0-9]{2,4}\\.json$`).test(url);
  requireThat(allowed, 'Source URL not allowed');
  const res = await fetch(url, {
    headers: {'user-agent': 'nick-nfl-receptions-platform-v5/1.0.0', 'cache-control': 'no-cache'},
    signal: AbortSignal.timeout(12000),
    cf: {cacheTtl: 0, cacheEverything: false},
  });
  requireThat(res.ok, `Research source unavailable (${res.status})`);
  const raw = await res.text();
  requireThat(raw.length < 8_000_000, 'Research source exceeds size limit');
  try { return {value: JSON.parse(raw), raw}; } catch { throw new Error('Research source returned invalid JSON'); }
}

function validateInit(input) {
  exactKeys(input, ['season', 'week', 'game_id', 'fixture_date_sydney', 'validated_kickoff_utc'], 'run init');
  requireThat(Number.isInteger(input.season) && input.season >= 2000 && input.season <= 2100, 'Invalid season');
  requireThat(Number.isInteger(input.week) && input.week >= 1 && input.week <= 18, 'Invalid week');
  requireThat(new RegExp(`^${input.season}_${String(input.week).padStart(2, '0')}_[A-Z0-9]{2,4}_[A-Z0-9]{2,4}$`).test(input.game_id), 'Invalid game_id');
  requireThat(/^\d{4}-\d{2}-\d{2}$/.test(input.fixture_date_sydney), 'Invalid Australia/Sydney fixture date');
  requireThat(/(Z|[+-]\d\d:\d\d)$/.test(input.validated_kickoff_utc), 'Kickoff requires explicit timezone');
  const kickoff = Date.parse(input.validated_kickoff_utc);
  requireThat(Number.isFinite(kickoff), 'Invalid validated kickoff');
  requireThat(kickoff > Date.now(), 'Fixture already started; create a new eligible run only before kickoff');
  const sydneyDate = new Intl.DateTimeFormat('en-CA', {timeZone:'Australia/Sydney', year:'numeric', month:'2-digit', day:'2-digit'}).format(new Date(kickoff));
  requireThat(sydneyDate === input.fixture_date_sydney, 'Australia/Sydney fixture date does not match validated kickoff');
}

export async function loadLockedPack(input) {
  validateInit(input);
  let lastRevisionMismatch = false;
  for (let attempt = 0; attempt < 2; attempt++) {
    const manifestResult = await readJson(`${DATA_ROOT}manifest.json`);
    const manifest = manifestResult.value;
    requireThat(manifest.schema_version === '1.1.0' && Array.isArray(manifest.games), 'Invalid NFL research manifest');
    const checkedAt = Date.parse(manifest.last_checked_at_utc || manifest.generated_at_utc);
    requireThat(Number.isFinite(checkedAt) && checkedAt <= Date.now() + 300_000 && Date.now() - checkedAt <= MAX_AGE_MS, 'NFL research manifest stale/invalid');
    const entry = manifest.games.find(g => g.game_id === input.game_id);
    requireThat(entry && entry.season === input.season && entry.week === input.week, 'Fixture not found in locked research manifest');
    requireThat(typeof entry.path === 'string' && /^games\/\d{4}\/\d{4}_\d{2}_[A-Z0-9]{2,4}_[A-Z0-9]{2,4}\.json$/.test(entry.path), 'Invalid research pack path');

    const packResult = await readJson(`${DATA_ROOT}${entry.path}`);
    const pack = packResult.value;
    requireThat(pack.schema_version === '1.1.0' && pack.fixture?.game_id === input.game_id && pack.fixture?.season === input.season && pack.fixture?.week === input.week, 'Research pack fixture mismatch');
    requireThat(pack.fixture.away_team === entry.away_team && pack.fixture.home_team === entry.home_team, 'Research pack team mismatch');
    if (pack.pack_revision !== entry.pack_revision) {
      lastRevisionMismatch = true;
      if (attempt === 0) continue;
      requireThat(false, 'Research manifest/pack revision race; retry new run');
    }
    requireThat(typeof pack.pack_revision === 'string' && /^[a-f0-9]{16}$/.test(pack.pack_revision), 'Invalid research pack revision');
    requireThat(Array.isArray(pack.players) && pack.players.length > 0, 'Research pack has no players');
    const through = pack.data_state?.current_season_data_through_week;
    requireThat(through === null || (Number.isInteger(through) && through <= input.week - 1), 'Current-season research leakage detected');

    const manifest_sha256 = await sha256Hex(manifestResult.raw);
    const pack_content_sha256 = await sha256Hex(packResult.raw);
    const source_anchor_sha256 = await sha256Hex({
      game_id: input.game_id,
      pack_revision: pack.pack_revision,
      manifest_sha256,
      pack_content_sha256,
    });
    return {source_anchor_sha256, manifest_sha256, pack_content_sha256, manifest, entry, pack};
  }
  requireThat(!lastRevisionMismatch, 'Research source lock failed');
}

function bannedMarketKeyScan(value, path = '') {
  const banned = new Set(['odds', 'price', 'bookmaker', 'sportsbook', 'market', 'market_data', 'betting_consensus', 'implied_probability', 'spread', 'game_total', 'prop_line']);
  if (Array.isArray(value)) { value.forEach((v, i) => bannedMarketKeyScan(v, `${path}[${i}]`)); return; }
  if (!value || typeof value !== 'object') return;
  for (const [key, child] of Object.entries(value)) {
    requireThat(!banned.has(key.toLowerCase()), `Market field prohibited in pre-freeze research receipt: ${path ? path + '.' : ''}${key}`);
    bannedMarketKeyScan(child, path ? `${path}.${key}` : key);
  }
}

function validEvidenceRefArray(ids, evidenceIds, label) {
  requireThat(Array.isArray(ids) && ids.length >= 1 && ids.length <= 30, `${label} evidence_ids required`);
  for (const id of ids) requireThat(evidenceIds.has(id), `${label} references unknown evidence_id ${id}`);
}

export function validateResearchContext(context, lock, playerCount, now = Date.now(), packPlayerIds = null) {
  exactKeys(context, ['game_id', 'completed_at', 'pack_receipt', 'current_information_state', 'research_quality_permission', 'evidence', 'team_contexts', 'defensive_profiles', 'players', 'material_unknowns', 'research_summary'], 'research context');
  bannedMarketKeyScan(context);
  requireThat(context.game_id === lock.game_id, 'Research game_id does not match run lock');
  const completed = Date.parse(context.completed_at);
  requireThat(Number.isFinite(completed) && completed <= now + 300_000 && completed >= lock.created_at - 300_000, 'Invalid research completion timestamp');
  exactKeys(context.pack_receipt, ['source_anchor_sha256', 'pack_revision', 'retrieved_player_count'], 'pack receipt');
  requireThat(context.pack_receipt.source_anchor_sha256 === lock.source_anchor_sha256, 'Research source anchor mismatch');
  requireThat(context.pack_receipt.pack_revision === lock.pack_revision, 'Research pack revision mismatch');
  requireThat(context.pack_receipt.retrieved_player_count === playerCount, 'Incomplete research pack player retrieval');
  requireThat(context.current_information_state && typeof context.current_information_state === 'object', 'Current Information State required');
  requireThat(['YES', 'NO'].includes(context.research_quality_permission), 'Invalid Research Quality Permission');
  requireThat(typeof context.research_summary === 'string' && context.research_summary.length >= 20 && context.research_summary.length <= 10000, 'Research summary incomplete');
  requireThat(Array.isArray(context.material_unknowns) && context.material_unknowns.length <= 100 && context.material_unknowns.every(x => typeof x === 'string' && x.length <= 1000), 'Invalid material_unknowns');
  requireThat(Array.isArray(context.evidence) && context.evidence.length >= 4 && context.evidence.length <= 500, 'Insufficient evidence receipt');
  for (const e of context.evidence) {
    exactKeys(e, ['evidence_id', 'source', 'source_url', 'source_date', 'checked_at', 'subject', 'finding', 'model_pathway', 'availability'], 'evidence receipt');
    requireThat(typeof e.source === 'string' && e.source.length >= 2 && e.source.length <= 200, 'Invalid evidence source');
    requireThat(e.source_url === null || (typeof e.source_url === 'string' && /^https:\/\//.test(e.source_url) && e.source_url.length <= 1000), 'Invalid evidence source_url');
    requireThat(e.source_date === null || Number.isFinite(Date.parse(e.source_date)), 'Invalid evidence source_date');
    requireThat(Number.isFinite(Date.parse(e.checked_at)), 'Invalid evidence checked_at');
    requireThat(typeof e.subject === 'string' && e.subject.length >= 2 && e.subject.length <= 200, 'Invalid evidence subject');
    requireThat(typeof e.finding === 'string' && e.finding.length >= 3 && e.finding.length <= 2000, 'Invalid evidence finding');
    requireThat(['TEAM_PASS_OPPORTUNITY', 'ROUTES', 'TARGETS', 'CATCH_CONVERSION', 'QB', 'PERSONNEL', 'DEFENSE', 'WEATHER', 'ROLE', 'AVAILABILITY', 'SYSTEM', 'OTHER'].includes(e.model_pathway), 'Invalid evidence model_pathway');
    requireThat(['VERIFIED', 'PARTIAL', 'UNAVAILABLE', 'UNKNOWN'].includes(e.availability), 'Invalid evidence availability');
  }
  const evidenceIds = evidenceIdSet(context);
  const fixtureTeams = new Set([lock.away_team, lock.home_team]);
  requireThat(Array.isArray(context.team_contexts) && context.team_contexts.length === 2, 'Both team contexts required');
  const teamContexts = new Set();
  for (const t of context.team_contexts) {
    exactKeys(t, ['team', 'summary', 'evidence_ids'], 'team context');
    requireThat(fixtureTeams.has(t.team) && !teamContexts.has(t.team), 'Invalid/duplicate team context'); teamContexts.add(t.team);
    requireThat(typeof t.summary === 'string' && t.summary.length >= 10 && t.summary.length <= 5000, 'Incomplete team context');
    validEvidenceRefArray(t.evidence_ids, evidenceIds, `${t.team} team context`);
  }
  requireThat(Array.isArray(context.defensive_profiles) && context.defensive_profiles.length === 2, 'Both four-part defensive profiles required');
  const defenses = new Set();
  for (const d of context.defensive_profiles) {
    exactKeys(d, ['team', 'passing_opportunities_faced', 'position_depth_concessions', 'pressure_protection', 'current_personnel', 'limitations'], 'defensive profile');
    requireThat(fixtureTeams.has(d.team) && !defenses.has(d.team), 'Invalid/duplicate defensive profile'); defenses.add(d.team);
    for (const key of ['passing_opportunities_faced', 'position_depth_concessions', 'pressure_protection', 'current_personnel']) {
      const part = d[key];
      exactKeys(part, ['status', 'summary', 'evidence_ids'], `defensive profile ${key}`);
      requireThat(['VERIFIED', 'PARTIAL', 'UNAVAILABLE'].includes(part.status), `Invalid ${key} status`);
      requireThat(typeof part.summary === 'string' && part.summary.length >= 5 && part.summary.length <= 5000, `Incomplete ${key} summary`);
      validEvidenceRefArray(part.evidence_ids, evidenceIds, `${d.team} ${key}`);
    }
    requireThat(Array.isArray(d.limitations) && d.limitations.length <= 50 && d.limitations.every(x => typeof x === 'string' && x.length <= 1000), 'Invalid defensive limitations');
  }
  requireThat(Array.isArray(context.players) && context.players.length >= 2 && context.players.length <= 60, 'Research player handoff required');
  const canonicalPlayers = new Set();
  for (const p of context.players) {
    exactKeys(p, ['player_id', 'player_name', 'team', 'research_status', 'evidence_ids', 'handoff_summary'], 'research player');
    requireThat(typeof p.player_id === 'string' && /^[A-Z0-9_-]{3,64}$/.test(p.player_id), 'Invalid canonical research player_id');
    if (packPlayerIds) requireThat(packPlayerIds.has(p.player_id) || p.player_id.startsWith('UNLISTED_'), `Research player_id ${p.player_id} is not in locked pack and is not explicitly UNLISTED`);
    requireThat(!canonicalPlayers.has(p.player_id), `Duplicate research player ${p.player_id}`); canonicalPlayers.add(p.player_id);
    requireThat(fixtureTeams.has(p.team), 'Research player team mismatch');
    requireThat(typeof p.player_name === 'string' && p.player_name.length >= 2 && p.player_name.length <= 80, 'Invalid research player_name');
    requireThat(['INCLUDE', 'WATCHLIST', 'EXCLUDE'].includes(p.research_status), 'Invalid research_status');
    validEvidenceRefArray(p.evidence_ids, evidenceIds, `${p.player_id} research`);
    requireThat(typeof p.handoff_summary === 'string' && p.handoff_summary.length >= 5 && p.handoff_summary.length <= 3000, 'Incomplete player handoff');
  }
}

async function countServed(storage, playerCount) {
  let served = 0;
  for (let i = 0; i < playerCount; i++) if (await storage.get(`served:${i}`)) served++;
  return served;
}

export class NflReceptionsRun {
  constructor(state, env) { this.state = state; this.storage = state.storage; this.env = env; }
  async fetch(request) {
    return this.state.blockConcurrencyWhile(async () => {
      try { return await this.handle(request); }
      catch (error) {
        const meta = await this.storage.get('meta');
        return reply({market_data: false, p_model_status: meta?.status === 'FROZEN' ? 'FROZEN' : 'NOT FROZEN', error: error.message}, 422);
      }
    });
  }
  async handle(request) {
    const url = new URL(request.url);
    const action = url.pathname.split('/').slice(4);
    let meta = await this.storage.get('meta');

    if (request.method === 'POST' && action.length === 0) {
      requireThat(!meta, 'Run already initialized');
      const input = await request.json();
      const {source_anchor_sha256, manifest_sha256, pack_content_sha256, manifest, pack} = await loadLockedPack(input);
      const now = Date.now();
      const {players, ...packMeta} = pack;
      const lock = {
        ...input,
        source_anchor_sha256,
        manifest_sha256,
        pack_content_sha256,
        pack_revision: pack.pack_revision,
        away_team: pack.fixture.away_team,
        home_team: pack.fixture.home_team,
        source_checked_at: manifest.last_checked_at_utc || manifest.generated_at_utc,
        created_at: now,
      };
      await this.storage.transaction(async tx => {
        await tx.put('pack', packMeta);
        for (let i = 0; i < players.length; i++) await tx.put(`p:${i}`, players[i]);
        await tx.put('meta', {lock, player_count: players.length, status: 'RESEARCH_IN_PROGRESS', research_receipt_sha256: null, freeze: null});
      });
      meta = await this.storage.get('meta');
      return reply({
        market_data: false,
        status: meta.status,
        p_model_status: 'NOT FROZEN',
        lock: meta.lock,
        research: {player_count: meta.player_count, served_player_count: 0, checkpointed: false, research_receipt_sha256: null},
        freeze: null,
      });
    }

    requireThat(meta, 'Unknown run');
    if (request.method === 'GET' && action.length === 0) {
      const served = await countServed(this.storage, meta.player_count);
      return reply({
        market_data: false,
        status: meta.status,
        p_model_status: meta.status === 'FROZEN' ? 'FROZEN' : 'NOT FROZEN',
        lock: meta.lock,
        research: {player_count: meta.player_count, served_player_count: served, checkpointed: Boolean(meta.research_receipt_sha256), research_receipt_sha256: meta.research_receipt_sha256},
        freeze: meta.freeze ? {frozen_at: meta.freeze.frozen_at, freeze_receipt_sha256: meta.freeze.freeze_receipt_sha256, frozen_probability_sha256: meta.freeze.frozen_probability_sha256, engine_version: meta.freeze.engine_version} : null,
      });
    }

    if (request.method === 'GET' && action[0] === 'research' && action.length === 1) {
      requireThat(meta.status !== 'FROZEN', 'Frozen run research is immutable');
      const offset = integer(url.searchParams.get('offset'), 0, meta.player_count, 0);
      const limit = integer(url.searchParams.get('limit'), 1, 20, 10);
      requireThat(offset <= meta.player_count, 'Offset exceeds player count');
      const returned = Math.min(limit, meta.player_count - offset);
      const page = [];
      for (let i = offset; i < offset + returned; i++) page.push(await this.storage.get(`p:${i}`));
      await this.storage.transaction(async tx => { for (let i = offset; i < offset + returned; i++) await tx.put(`served:${i}`, true); });
      const pack = await this.storage.get('pack');
      const served = await countServed(this.storage, meta.player_count);
      return reply({market_data: false, lock: meta.lock, pack: {...pack, players: undefined}, players: page,
        pagination: {offset, returned, total_players: meta.player_count, next_offset: offset + returned < meta.player_count ? offset + returned : null},
        retrieval: {served_player_count: served, complete: served === meta.player_count}});
    }

    if (request.method === 'POST' && action[0] === 'research' && action.length === 1) {
      requireThat(meta.status === 'RESEARCH_IN_PROGRESS', 'Research checkpoint not allowed in current state');
      const body = await request.json(); exactKeys(body, ['context'], 'research checkpoint');
      const served = await countServed(this.storage, meta.player_count);
      requireThat(served === meta.player_count, `Complete locked research pack must be retrieved before checkpoint (${served}/${meta.player_count})`);
      const packPlayerIds = new Set();
      for (let i = 0; i < meta.player_count; i++) { const p = await this.storage.get(`p:${i}`); if (p?.player_id) packPlayerIds.add(p.player_id); }
      validateResearchContext(body.context, meta.lock, meta.player_count, Date.now(), packPlayerIds);
      const context = {
        ...body.context,
        fixture: {away_team: meta.lock.away_team, home_team: meta.lock.home_team},
        research_receipt_sha256: await sha256Hex(body.context),
      };
      await this.storage.transaction(async tx => {
        await tx.put('context', context);
        await tx.put('meta', {...meta, status: 'RESEARCH_COMPLETE', research_receipt_sha256: context.research_receipt_sha256});
      });
      return reply({market_data: false, status: 'RESEARCH_COMPLETE', game_id: meta.lock.game_id, research_receipt_sha256: context.research_receipt_sha256});
    }

    if (request.method === 'POST' && action[0] === 'compute' && action.length === 1) {
      const body = await request.json(); exactKeys(body, ['model_input'], 'compute request');
      if (meta.status === 'FROZEN') return reply({market_data: false, p_model_status: 'FROZEN', freeze: meta.freeze});
      requireThat(meta.status === 'RESEARCH_COMPLETE', 'Research must be checkpointed before Layer 2 compute');
      requireThat(Date.now() - meta.lock.created_at <= MAX_AGE_MS, 'Run expired; start a new research run');
      const context = await this.storage.get('context');
      requireThat(context?.research_receipt_sha256 === meta.research_receipt_sha256, 'Research receipt binding failed');
      const frozen = await computeFrozenModel(body.model_input, context, Date.now());
      await this.storage.transaction(async tx => {
        await tx.put('freeze', frozen);
        await tx.put('meta', {...meta, status: 'FROZEN', freeze: frozen});
      });
      return reply({market_data: false, complete_model_integrity_confirmed: true, p_model_status: 'FROZEN', freeze: frozen});
    }

    if (request.method === 'GET' && action[0] === 'freeze' && action.length === 1) {
      requireThat(meta.status === 'FROZEN', 'Run not frozen');
      const frozen = await this.storage.get('freeze');
      requireThat(frozen?.freeze_receipt_sha256 === meta.freeze?.freeze_receipt_sha256, 'Frozen artifact receipt mismatch');
      return reply({market_data: false, p_model_status: 'FROZEN', freeze: frozen});
    }

    if (request.method === 'GET' && action[0] === 'players' && action.length === 2) {
      requireThat(meta.status === 'FROZEN', 'Run not frozen');
      const frozen = await this.storage.get('freeze');
      const player = frozen.players.find(p => p.player_id === action[1]);
      requireThat(player, 'Frozen player not found');
      return reply({market_data: false, game_id: meta.lock.game_id, frozen_at: frozen.frozen_at, freeze_receipt_sha256: frozen.freeze_receipt_sha256, player});
    }

    throw new Error('Unknown run operation');
  }
}

export async function routeRun(request, env) {
  const url = new URL(request.url);
  if (!url.pathname.startsWith('/v1/runs')) return null;
  if (!env.NFL_RECEPTIONS_RUNS) return reply({error: 'NFL run-state storage binding unavailable', market_data: false}, 503);
  const match = url.pathname.match(/^\/v1\/runs(?:\/([a-f0-9]{64})(?:\/(research|compute|freeze|players)(?:\/([A-Z0-9_-]{3,64}))?)?)?$/);
  if (!match) return reply({error: 'Not found', market_data: false}, 404);
  if (!match[1] && request.method !== 'POST') return reply({error: 'POST required', market_data: false}, 405);
  const id = match[1] ? env.NFL_RECEPTIONS_RUNS.idFromString(match[1]) : env.NFL_RECEPTIONS_RUNS.newUniqueId();
  if (!match[1]) url.pathname += `/${id.toString()}`;
  const raw = await request.text();
  if (raw.length > 500_000) return reply({error: 'Request too large', market_data: false}, 413);
  const res = await env.NFL_RECEPTIONS_RUNS.get(id).fetch(new Request(url, {method: request.method, headers: request.headers, ...(request.method === 'GET' ? {} : {body: raw})}));
  const data = await res.json();
  return reply({run_id: id.toString(), ...data}, res.status);
}
