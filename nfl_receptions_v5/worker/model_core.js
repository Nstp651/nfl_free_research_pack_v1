const ALLOCATION_TOLERANCE = 1e-8;
const PROBABILITY_TOLERANCE = 1e-10;

export function requireThat(condition, message) {
  if (!condition) throw new Error(message);
}

export function exactKeys(value, keys, label = 'object') {
  requireThat(value && typeof value === 'object' && !Array.isArray(value), `Invalid ${label}`);
  const actual = Object.keys(value).sort();
  const expected = [...keys].sort();
  requireThat(actual.length === expected.length && actual.every((k, i) => k === expected[i]),
    `${label} keys mismatch: expected ${expected.join(',')}`);
}

function finiteNumber(value, label, min = -Infinity, max = Infinity) {
  requireThat(typeof value === 'number' && Number.isFinite(value) && value >= min && value <= max,
    `Invalid ${label}`);
  return value;
}

function finiteInteger(value, label, min, max) {
  requireThat(Number.isInteger(value) && value >= min && value <= max, `Invalid ${label}`);
  return value;
}

function canonicalize(value) {
  if (Array.isArray(value)) return value.map(canonicalize);
  if (value && typeof value === 'object') {
    const out = {};
    for (const key of Object.keys(value).sort()) out[key] = canonicalize(value[key]);
    return out;
  }
  return value;
}

export function canonicalJson(value) {
  return JSON.stringify(canonicalize(value));
}

export async function sha256Hex(value) {
  const raw = typeof value === 'string' ? value : canonicalJson(value);
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(raw));
  return [...new Uint8Array(digest)].map(x => x.toString(16).padStart(2, '0')).join('');
}

function validateDiscreteSupport(items, label, maxValue = 120) {
  requireThat(Array.isArray(items) && items.length >= 1 && items.length <= 121, `${label} must be a non-empty array`);
  const seen = new Set();
  let p = 0;
  for (const row of items) {
    exactKeys(row, ['value', 'probability'], `${label} row`);
    finiteInteger(row.value, `${label}.value`, 0, maxValue);
    finiteNumber(row.probability, `${label}.probability`, 0, 1);
    requireThat(!seen.has(row.value), `${label} contains duplicate value ${row.value}`);
    seen.add(row.value);
    p += row.probability;
  }
  requireThat(Math.abs(p - 1) <= ALLOCATION_TOLERANCE, `${label} probabilities must sum to 1`);
}

function supportMean(items) {
  return items.reduce((acc, row) => acc + row.value * row.probability, 0);
}

function validateRate(rate, label) {
  exactKeys(rate, ['mean', 'strength'], label);
  finiteNumber(rate.mean, `${label}.mean`, 0, 1);
  finiteNumber(rate.strength, `${label}.strength`, 0, 1000000);
  if (rate.mean > 0 && rate.mean < 1) requireThat(rate.strength >= 2, `${label}.strength must be >= 2 for non-degenerate beta rate`);
}

// Lanczos approximation; stable for the small integer-count beta-binomial ranges used here.
function logGamma(z) {
  const p = [
    0.99999999999980993, 676.5203681218851, -1259.1392167224028,
    771.32342877765313, -176.61502916214059, 12.507343278686905,
    -0.13857109526572012, 9.9843695780195716e-6, 1.5056327351493116e-7,
  ];
  if (z < 0.5) return Math.log(Math.PI) - Math.log(Math.sin(Math.PI * z)) - logGamma(1 - z);
  z -= 1;
  let x = p[0];
  for (let i = 1; i < p.length; i++) x += p[i] / (z + i);
  const t = z + p.length - 1.5;
  return 0.5 * Math.log(2 * Math.PI) + (z + 0.5) * Math.log(t) - t + Math.log(x);
}

function logChoose(n, k) {
  return logGamma(n + 1) - logGamma(k + 1) - logGamma(n - k + 1);
}

function betaBinomialPmf(k, n, mean, strength) {
  if (mean === 0) return k === 0 ? 1 : 0;
  if (mean === 1) return k === n ? 1 : 0;
  const a = mean * strength;
  const b = (1 - mean) * strength;
  const logP = logChoose(n, k) + logGamma(k + a) + logGamma(n - k + b) - logGamma(n + a + b)
    + logGamma(a + b) - logGamma(a) - logGamma(b);
  return Math.exp(logP);
}

function hierarchicalReceptionPmf(opportunitySupport, targetRate, catchRate) {
  const maxN = Math.max(...opportunitySupport.map(x => x.value));
  const out = Array(maxN + 1).fill(0);
  for (const opp of opportunitySupport) {
    const targetPmf = Array(opp.value + 1).fill(0).map((_, t) =>
      betaBinomialPmf(t, opp.value, targetRate.mean, targetRate.strength));
    for (let t = 0; t <= opp.value; t++) {
      const targetWeight = opp.probability * targetPmf[t];
      if (targetWeight === 0) continue;
      for (let r = 0; r <= t; r++) {
        out[r] += targetWeight * betaBinomialPmf(r, t, catchRate.mean, catchRate.strength);
      }
    }
  }
  const total = out.reduce((a, b) => a + b, 0);
  requireThat(Number.isFinite(total) && Math.abs(total - 1) <= 1e-8, 'Reception PMF failed normalization');
  return out.map(x => x / total);
}

function playerScenarioExpectedTargets(teamOppMean, playerParam) {
  if (playerParam.target_method === 'A') return teamOppMean * playerParam.target_rate.mean;
  return supportMean(playerParam.route_counts) * playerParam.target_rate.mean;
}

function derivedAllocationShare(teamOppMean, playerParam) {
  requireThat(teamOppMean > 0, 'Team targetable-pass mean must be positive');
  return playerScenarioExpectedTargets(teamOppMean, playerParam) / teamOppMean;
}

function validatePlayerMeta(player) {
  exactKeys(player, ['player_id', 'player_name', 'confidence', 'fragility', 'key_assumptions'], 'player metadata');
  requireThat(typeof player.player_id === 'string' && /^[A-Z0-9_-]{3,64}$/.test(player.player_id), 'Invalid player_id');
  requireThat(typeof player.player_name === 'string' && player.player_name.length >= 2 && player.player_name.length <= 80, 'Invalid player_name');
  requireThat(['HIGH', 'MEDIUM', 'LOW'].includes(player.confidence), 'Invalid Confidence');
  requireThat(['LOW', 'MODERATE', 'HIGH'].includes(player.fragility), 'Invalid Fragility');
  requireThat(Array.isArray(player.key_assumptions) && player.key_assumptions.length <= 20 && player.key_assumptions.every(x => typeof x === 'string' && x.length <= 300), 'Invalid key assumptions');
}

function validatePlayerParam(param, playerIds) {
  const baseKeys = ['player_id', 'target_method', 'target_rate', 'catch_rate', 'route_counts'];
  exactKeys(param, baseKeys, 'player parameter');
  requireThat(playerIds.has(param.player_id), `Unknown player_id ${param.player_id}`);
  requireThat(['A', 'B'].includes(param.target_method), 'target_method must be A or B');
  validateRate(param.target_rate, `${param.player_id}.target_rate`);
  validateRate(param.catch_rate, `${param.player_id}.catch_rate`);
  if (param.target_method === 'A') {
    requireThat(param.route_counts === null || Array.isArray(param.route_counts), 'Method A route_counts must be null or discrete support');
    if (Array.isArray(param.route_counts)) validateDiscreteSupport(param.route_counts, `${param.player_id}.route_counts`, 100);
  } else {
    validateDiscreteSupport(param.route_counts, `${param.player_id}.route_counts`, 100);
  }
}

function validateLedger(ledger, evidenceIds) {
  requireThat(Array.isArray(ledger) && ledger.length >= 1 && ledger.length <= 500, 'source_to_parameter_ledger must be a non-empty array');
  for (const item of ledger) {
    exactKeys(item, ['parameter_path', 'evidence_ids', 'rationale'], 'ledger item');
    requireThat(typeof item.parameter_path === 'string' && item.parameter_path.length >= 3 && item.parameter_path.length <= 240, 'Invalid parameter_path');
    requireThat(Array.isArray(item.evidence_ids) && item.evidence_ids.length >= 1 && item.evidence_ids.length <= 20, 'Invalid evidence_ids');
    for (const id of item.evidence_ids) requireThat(evidenceIds.has(id), `Ledger references unknown evidence_id ${id}`);
    requireThat(typeof item.rationale === 'string' && item.rationale.length >= 3 && item.rationale.length <= 1000, 'Invalid ledger rationale');
  }
}

export function evidenceIdSet(context) {
  const ids = new Set();
  for (const item of context.evidence || []) {
    requireThat(item && typeof item === 'object' && typeof item.evidence_id === 'string' && /^[A-Z0-9_-]{3,80}$/.test(item.evidence_id), 'Invalid evidence_id');
    requireThat(!ids.has(item.evidence_id), `Duplicate evidence_id ${item.evidence_id}`);
    ids.add(item.evidence_id);
  }
  return ids;
}

export function validateModelInput(input, context) {
  exactKeys(input, ['game_id', 'engine_version', 'threshold_max', 'teams', 'source_to_parameter_ledger'], 'model input');
  requireThat(input.game_id === context.game_id, 'Model game_id does not match checkpointed research');
  requireThat(input.engine_version === 'NFL_RECEPTIONS_V5_EXACT_HBB_1.0.0', 'Unsupported engine_version');
  finiteInteger(input.threshold_max, 'threshold_max', 1, 20);
  requireThat(Array.isArray(input.teams) && input.teams.length === 2, 'Exactly two teams are required');
  const researchPlayers = new Map((context.players || []).map(p => [p.player_id, p]));
  requireThat(researchPlayers.size === (context.players || []).length && researchPlayers.size >= 2, 'Checkpointed research player identities required');
  const teamCodes = new Set();
  for (const team of input.teams) {
    exactKeys(team, ['team', 'players', 'scenarios'], 'team model');
    requireThat(typeof team.team === 'string' && /^[A-Z0-9]{2,4}$/.test(team.team), 'Invalid team code');
    requireThat(!teamCodes.has(team.team), 'Duplicate team model'); teamCodes.add(team.team);
    requireThat(Array.isArray(team.players) && team.players.length >= 1 && team.players.length <= 20, 'Invalid players array');
    const playerIds = new Set();
    for (const player of team.players) {
      validatePlayerMeta(player);
      const researchPlayer = researchPlayers.get(player.player_id);
      requireThat(researchPlayer, `Model player_id ${player.player_id} not present in checkpointed research`);
      requireThat(researchPlayer.team === team.team, `Model player ${player.player_id} team does not match checkpointed research`);
      requireThat(['INCLUDE', 'WATCHLIST'].includes(researchPlayer.research_status), `Model player ${player.player_id} is not eligible from checkpointed research`);
      requireThat(researchPlayer.player_name === player.player_name, `Model player ${player.player_id} name does not match checkpointed research`);
      requireThat(!playerIds.has(player.player_id), `Duplicate player_id ${player.player_id}`); playerIds.add(player.player_id);
    }
    requireThat(Array.isArray(team.scenarios) && team.scenarios.length >= 1 && team.scenarios.length <= 12, 'Invalid scenarios array');
    let scenarioWeight = 0;
    const scenarioIds = new Set();
    let combinedOpp = 0, combinedTargets = 0, combinedOtherTargets = 0;
    for (const scenario of team.scenarios) {
      exactKeys(scenario, ['scenario_id', 'weight', 'targetable_passes', 'other_share', 'player_params', 'football_rationale'], 'scenario');
      requireThat(typeof scenario.scenario_id === 'string' && /^[A-Z0-9_-]{2,64}$/.test(scenario.scenario_id), 'Invalid scenario_id');
      requireThat(!scenarioIds.has(scenario.scenario_id), `Duplicate scenario_id ${scenario.scenario_id}`); scenarioIds.add(scenario.scenario_id);
      finiteNumber(scenario.weight, 'scenario.weight', 0, 1); scenarioWeight += scenario.weight;
      validateDiscreteSupport(scenario.targetable_passes, `${team.team}.${scenario.scenario_id}.targetable_passes`, 100);
      finiteNumber(scenario.other_share, 'other_share', 0, 1);
      requireThat(typeof scenario.football_rationale === 'string' && scenario.football_rationale.length >= 3 && scenario.football_rationale.length <= 1200, 'Invalid football_rationale');
      requireThat(Array.isArray(scenario.player_params) && scenario.player_params.length === team.players.length, 'Each scenario must parameterize every modelled player');
      const paramIds = new Set();
      for (const param of scenario.player_params) {
        validatePlayerParam(param, playerIds);
        requireThat(!paramIds.has(param.player_id), `Duplicate scenario parameter ${param.player_id}`); paramIds.add(param.player_id);
      }
      requireThat([...playerIds].every(id => paramIds.has(id)), 'Scenario player parameter set is incomplete');
      const oppMean = supportMean(scenario.targetable_passes);
      const shares = scenario.player_params.map(p => derivedAllocationShare(oppMean, p));
      for (const share of shares) finiteNumber(share, 'derived player allocation share', 0, 1);
      const modelledShare = shares.reduce((a, b) => a + b, 0);
      const totalShare = modelledShare + scenario.other_share;
      requireThat(Math.abs(totalShare - 1) <= ALLOCATION_TOLERANCE,
        `${team.team}/${scenario.scenario_id} target allocation ${totalShare} != 1`);
      combinedOpp += scenario.weight * oppMean;
      combinedTargets += scenario.weight * scenario.player_params.reduce((sum, p) => sum + playerScenarioExpectedTargets(oppMean, p), 0);
      combinedOtherTargets += scenario.weight * scenario.other_share * oppMean;
    }
    requireThat(Math.abs(scenarioWeight - 1) <= ALLOCATION_TOLERANCE, `${team.team} scenario weights must sum to 1`);
    requireThat(combinedOpp > 0, `${team.team} combined targetable-pass mean must be positive`);
    const combinedTotalShare = (combinedTargets + combinedOtherTargets) / combinedOpp;
    requireThat(Math.abs(combinedTotalShare - 1) <= ALLOCATION_TOLERANCE, `${team.team} combined allocation failed`);
  }
  const fixtureTeams = new Set([context.fixture.away_team, context.fixture.home_team]);
  requireThat(teamCodes.size === fixtureTeams.size && [...teamCodes].every(x => fixtureTeams.has(x)), 'Model teams do not match frozen fixture');
  validateLedger(input.source_to_parameter_ledger, evidenceIdSet(context));
}

function pmfMean(pmf) { return pmf.reduce((acc, p, i) => acc + i * p, 0); }

function ladderFromPmf(pmf, maxThreshold) {
  const ladder = {};
  for (let k = 1; k <= maxThreshold; k++) {
    let p = 0;
    for (let r = k; r < pmf.length; r++) p += pmf[r];
    ladder[String(k)] = Math.max(0, Math.min(1, p));
  }
  let prior = 1;
  for (let k = 1; k <= maxThreshold; k++) {
    requireThat(ladder[String(k)] <= prior + PROBABILITY_TOLERANCE, 'Reception ladder monotonicity failed');
    prior = ladder[String(k)];
  }
  return ladder;
}

export async function computeFrozenModel(input, context, now = Date.now()) {
  validateModelInput(input, context);
  const outputs = [];
  const teamAudits = [];
  for (const team of input.teams) {
    const metaById = new Map(team.players.map(p => [p.player_id, p]));
    const playerPmfs = new Map(team.players.map(p => [p.player_id, []]));
    let combinedOpp = 0, combinedOtherTargets = 0;
    const combinedExpectedTargets = new Map(team.players.map(p => [p.player_id, 0]));
    const scenarioAudits = [];
    for (const scenario of team.scenarios) {
      const oppMean = supportMean(scenario.targetable_passes);
      combinedOpp += scenario.weight * oppMean;
      combinedOtherTargets += scenario.weight * scenario.other_share * oppMean;
      const paramById = new Map(scenario.player_params.map(p => [p.player_id, p]));
      const shares = {};
      let modelledShare = 0;
      for (const player of team.players) {
        const param = paramById.get(player.player_id);
        const oppSupport = param.target_method === 'A' ? scenario.targetable_passes : param.route_counts;
        const pmf = hierarchicalReceptionPmf(oppSupport, param.target_rate, param.catch_rate);
        playerPmfs.get(player.player_id).push({weight: scenario.weight, pmf, scenario_id: scenario.scenario_id});
        const expTargets = playerScenarioExpectedTargets(oppMean, param);
        combinedExpectedTargets.set(player.player_id, combinedExpectedTargets.get(player.player_id) + scenario.weight * expTargets);
        const share = expTargets / oppMean; shares[player.player_id] = share; modelledShare += share;
      }
      scenarioAudits.push({scenario_id: scenario.scenario_id, weight: scenario.weight, team_opportunity_mean: oppMean,
        player_shares: shares, modelled_share: modelledShare, other_share: scenario.other_share,
        total_share: modelledShare + scenario.other_share, allocation_status: 'PASS'});
    }
    const combinedModelledTargets = [...combinedExpectedTargets.values()].reduce((a, b) => a + b, 0);
    teamAudits.push({team: team.team, scenarios: scenarioAudits, combined_team_opportunity_mean: combinedOpp,
      combined_modelled_targets: combinedModelledTargets, combined_other_targets: combinedOtherTargets,
      combined_total_share: (combinedModelledTargets + combinedOtherTargets) / combinedOpp, allocation_status: 'PASS'});

    for (const player of team.players) {
      const pieces = playerPmfs.get(player.player_id);
      const maxLen = Math.max(...pieces.map(x => x.pmf.length));
      const mixed = Array(maxLen).fill(0);
      for (const piece of pieces) for (let i = 0; i < piece.pmf.length; i++) mixed[i] += piece.weight * piece.pmf[i];
      const total = mixed.reduce((a, b) => a + b, 0);
      requireThat(Math.abs(total - 1) <= 1e-8, `${player.player_id} scenario mixture failed normalization`);
      const normalized = mixed.map(x => x / total);
      const expectedTargets = combinedExpectedTargets.get(player.player_id);
      const expectedReceptions = pmfMean(normalized);
      outputs.push({
        player_id: player.player_id,
        player_name: player.player_name,
        team: team.team,
        expected_targets: expectedTargets,
        expected_receptions: expectedReceptions,
        distribution_method: 'EXACT_HIERARCHICAL_BETA_BINOMIAL',
        ladder: ladderFromPmf(normalized, input.threshold_max),
        confidence: player.confidence,
        fragility: player.fragility,
        key_assumptions: player.key_assumptions,
        pmf_sha256: await sha256Hex(normalized),
      });
    }
  }
  outputs.sort((a, b) => a.team.localeCompare(b.team) || a.player_id.localeCompare(b.player_id));
  const frozen = {
    schema_version: 'betting-platform-v1/nfl-receptions-freeze-1.0.0',
    game_id: input.game_id,
    engine_version: input.engine_version,
    research_receipt_sha256: context.research_receipt_sha256,
    frozen_at: new Date(now).toISOString(),
    threshold_max: input.threshold_max,
    team_allocation_audits: teamAudits,
    source_to_parameter_ledger: input.source_to_parameter_ledger,
    players: outputs,
  };
  frozen.model_input_sha256 = await sha256Hex(input);
  frozen.frozen_probability_sha256 = await sha256Hex(outputs.map(p => ({player_id: p.player_id, ladder: p.ladder, pmf_sha256: p.pmf_sha256})));
  frozen.freeze_receipt_sha256 = await sha256Hex({...frozen, freeze_receipt_sha256: undefined});
  return frozen;
}
