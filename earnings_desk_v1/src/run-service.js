import { MODEL_VERSION, RETURN_HORIZON_ID, RETURN_HORIZON_METHODOLOGY_VERSION, SELECTION_VERSION, VALUATION_VERSION } from "./config.js";
import { canonicalJson, dateOnly, isoTimestamp, parseJsonColumn, randomId, requireThat, sha256Hex, tickerText } from "./canonical.js";
import { buildPModel } from "./pmodel.js";
import { validateResearchPack } from "./research.js";
import { buildCandidates, validateMarketInput } from "./market-input.js";
import { valueCandidate } from "./option-pricing.js";
import { selectCandidates, tradeCard } from "./selection.js";
import { fetchEvent, fetchFreeze, fetchResearch, fetchRun, seedModelVersions } from "./repository.js";
import { validateHistoricalHorizon } from "./market-time.js";
import { assertLiveReadiness } from "./risk-config.js";

function sydneyParts(date) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Australia/Sydney",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23"
  }).formatToParts(date);
  return Object.fromEntries(parts.map((part) => [part.type, part.value]));
}

function validateUniverse(events, cutoff, intendedExit) {
  requireThat(Array.isArray(events) && events.length <= 100, "events must contain at most 100 rows");
  const cutoffMs = Date.parse(cutoff);
  const exitMs = Date.parse(intendedExit);
  const tickers = new Set();
  return events.map((input, index) => {
    requireThat(input && typeof input === "object", `event ${index} invalid`);
    const ticker = tickerText(input.ticker);
    requireThat(!tickers.has(ticker), `duplicate event ticker ${ticker}`);
    tickers.add(ticker);
    const reportAt = isoTimestamp(input.report_at, `event ${ticker} report_at`);
    const timing = String(input.event_timing ?? "").toUpperCase();
    requireThat(timing === "AMC" || timing === "BMO", `event ${ticker} timing invalid`);
    const timingReliability = String(input.timing_reliability ?? "").toUpperCase();
    requireThat(timingReliability === "HIGH" || timingReliability === "MEDIUM", `event ${ticker} timing reliability invalid`);
    requireThat(/^https:\/\//.test(String(input.timing_source_url ?? "")), `event ${ticker} timing source invalid`);
    const verifiedAt = isoTimestamp(input.timing_verified_at, `event ${ticker} timing_verified_at`);
    requireThat(Date.parse(verifiedAt) <= cutoffMs, `event ${ticker} timing verified after research cutoff`);
    const liquid = input.liquid_us_listing === true;
    const weekly = input.weekly_options_available === true;
    const inWindow = Date.parse(reportAt) > cutoffMs && Date.parse(reportAt) < exitMs;
    const eligible = liquid && weekly && inWindow;
    const reasons = [
      liquid ? null : "ILLIQUID_OR_NON_US_LISTING",
      weekly ? null : "NO_LIQUID_WEEKLY_OPTIONS",
      inWindow ? null : "OUTSIDE_RUN_TO_EXIT_WINDOW"
    ].filter(Boolean);
    const realizedVol = Number(input.realized_vol_20d);
    const preEventPrice = Number(input.pre_event_price);
    requireThat(Number.isFinite(realizedVol) && realizedVol > 0, `event ${ticker} realized_vol_20d invalid`);
    requireThat(Number.isFinite(preEventPrice) && preEventPrice > 0, `event ${ticker} pre_event_price invalid`);
    return {
      event_id: String(input.event_id ?? randomId("evt")),
      ticker,
      company_name: String(input.company_name ?? "").trim(),
      sector: String(input.sector ?? "").trim(),
      market_cap_cohort: String(input.market_cap_cohort ?? "").trim(),
      report_at: reportAt,
      event_timing: timing,
      timing_source_url: String(input.timing_source_url),
      timing_verified_at: verifiedAt,
      timing_reliability: timingReliability,
      intended_exit_at: intendedExit,
      realized_vol_20d: realizedVol,
      pre_event_price: preEventPrice,
      liquid_us_listing: liquid ? 1 : 0,
      weekly_options_available: weekly ? 1 : 0,
      eligible: eligible ? 1 : 0,
      eligibility_reason: eligible ? "ELIGIBLE" : reasons.join("|")
    };
  });
}

export async function createRun(db, input, riskConfig, now = new Date()) {
  const nowIso = now.toISOString();
  const parts = sydneyParts(now);
  const mode = String(input.mode ?? riskConfig.operating_mode ?? "SHADOW").toUpperCase();
  requireThat(mode === "SHADOW" || mode === "LIVE", "mode must be SHADOW or LIVE");
  requireThat(mode === riskConfig.operating_mode, `run mode ${mode} does not match configured EARNINGS_DESK_MODE=${riskConfig.operating_mode}`, "CONFIGURATION_ERROR");
  const liveReadiness = mode === "LIVE" ? await assertLiveReadiness(db, riskConfig) : null;
  const researchCutoff = isoTimestamp(input.research_cutoff ?? nowIso, "research_cutoff");
  requireThat(Date.parse(researchCutoff) <= now.getTime() + 120_000, "research_cutoff cannot be in the future");
  const intendedExitAt = isoTimestamp(input.intended_exit_at, "intended_exit_at");
  requireThat(Date.parse(intendedExitAt) > Date.parse(researchCutoff), "intended exit must follow research cutoff");
  const usTradingDate = dateOnly(input.us_trading_date, "us_trading_date");
  const events = validateUniverse(input.events ?? [], researchCutoff, intendedExitAt);
  const universe = events.map((event) => ({ ...event })).sort((a, b) => a.ticker.localeCompare(b.ticker));
  const eligibleCount = universe.filter((event) => event.eligible === 1).length;
  const initialStatus = eligibleCount === 0 ? "FROZEN" : "RUN_LOCKED";
  const universeSha = await sha256Hex(universe);
  const lock = {
    sydney_timestamp: nowIso,
    sydney_local_date: `${parts.year}-${parts.month}-${parts.day}`,
    sydney_local_time: `${parts.hour}:${parts.minute}:${parts.second}`,
    us_trading_date: usTradingDate,
    mode,
    model_version: MODEL_VERSION,
    research_cutoff: researchCutoff,
    intended_exit_at: intendedExitAt,
    universe_sha256: universeSha,
    max_core_positions: riskConfig.max_core_positions,
    max_daily_capital_usd: riskConfig.max_daily_capital_usd,
    risk_profile_id: riskConfig.risk_profile_id,
    live_readiness: liveReadiness
  };
  const runId = await sha256Hex(lock);
  await seedModelVersions(db, nowIso);
  const statements = [
    db.prepare(`INSERT INTO earnings_runs
      (run_id, sydney_timestamp, sydney_local_date, us_trading_date, mode, status, model_version,
       research_cutoff, intended_exit_at, universe_sha256, max_core_positions, max_daily_capital_usd,
       operator_started_at, created_at, updated_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
      .bind(runId, nowIso, lock.sydney_local_date, usTradingDate, mode, initialStatus, MODEL_VERSION, researchCutoff, intendedExitAt, universeSha, riskConfig.max_core_positions, riskConfig.max_daily_capital_usd, nowIso, nowIso, nowIso)
  ];
  for (const event of universe) {
    statements.push(db.prepare(`INSERT INTO earnings_events
      (event_id, run_id, ticker, company_name, sector, market_cap_cohort, report_at, event_timing,
       timing_source_url, timing_verified_at, timing_reliability, intended_exit_at, realized_vol_20d,
       pre_event_price, liquid_us_listing, weekly_options_available, eligible, eligibility_reason, created_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
      .bind(event.event_id, runId, event.ticker, event.company_name, event.sector, event.market_cap_cohort, event.report_at, event.event_timing, event.timing_source_url, event.timing_verified_at, event.timing_reliability, event.intended_exit_at, event.realized_vol_20d, event.pre_event_price, event.liquid_us_listing, event.weekly_options_available, event.eligible, event.eligibility_reason, nowIso));
  }
  const decision = { run_id: runId, lock, universe };
  const decisionJson = canonicalJson(decision);
  statements.push(db.prepare(`INSERT INTO earnings_decision_records
    (decision_id, run_id, event_id, record_type, record_json, record_sha256, created_at)
    VALUES (?, ?, NULL, 'RUN_LOCK', ?, ?, ?)`)
    .bind(randomId("decision"), runId, decisionJson, await sha256Hex(decision), nowIso));
  await db.batch(statements);
  return { run_id: runId, status: initialStatus, lock, universe, eligible_count: eligibleCount };
}

export async function submitResearch(db, runId, eventKey, input, now = new Date()) {
  const [run, event] = await Promise.all([fetchRun(db, runId), fetchEvent(db, runId, eventKey)]);
  requireThat(event.eligible === 1, `event is not eligible: ${event.eligibility_reason}`, "DATA_BLOCKED");
  requireThat(!["FROZEN", "VALUED", "CLOSED"].includes(run.status), "run is no longer accepting research");
  const validated = validateResearchPack(input, event, run.research_cutoff);
  const researchJson = canonicalJson(validated);
  const researchSha = await sha256Hex(validated);
  const researchId = randomId("research");
  const nowIso = now.toISOString();
  const receipt = { research_id: researchId, run_id: runId, event_id: event.event_id, ticker: event.ticker, research_sha256: researchSha, submitted_at: nowIso };
  const receiptJson = canonicalJson(receipt);
  await db.batch([
    db.prepare(`INSERT INTO earnings_research_packs
      (research_id, run_id, event_id, ticker, research_json, research_sha256, evidence_quality, feature_contract_version, submitted_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`) 
      .bind(researchId, runId, event.event_id, event.ticker, researchJson, researchSha, validated.evidence_quality, validated.model_feature_contract, nowIso),
    db.prepare("UPDATE earnings_runs SET status = CASE WHEN status = 'RUN_LOCKED' THEN 'RESEARCH_IN_PROGRESS' ELSE status END, updated_at = ? WHERE run_id = ?")
      .bind(nowIso, runId),
    db.prepare(`INSERT INTO earnings_decision_records
      (decision_id, run_id, event_id, record_type, record_json, record_sha256, created_at)
      VALUES (?, ?, ?, 'RESEARCH_CHECKPOINT', ?, ?, ?)`)
      .bind(randomId("decision"), runId, event.event_id, receiptJson, await sha256Hex(receipt), nowIso)
  ]);
  return receipt;
}

export async function freezeEvent(db, runId, eventKey, now = new Date()) {
  const [run, event] = await Promise.all([fetchRun(db, runId), fetchEvent(db, runId, eventKey)]);
  requireThat(event.eligible === 1, "cannot freeze an ineligible event", "DATA_BLOCKED");
  const existing = await db.prepare("SELECT * FROM earnings_freezes WHERE run_id = ? AND event_id = ? LIMIT 1").bind(runId, event.event_id).first();
  if (existing) return parseJsonColumn(existing.freeze_json);
  const research = await fetchResearch(db, runId, event.event_id);
  const historyResult = await db.prepare(`SELECT ticker, event_date, event_timing, sector, market_cap_cohort,
      pre_event_price_timestamp, exit_price_timestamp, return_horizon_id, return_horizon_methodology_version,
      event_return, absolute_return, gap_open_return, realized_vol_20d, pre_event_drift,
      reported_eps, consensus_eps, reported_revenue, consensus_revenue, guidance_change_z,
      estimate_revision_z, consensus_dispersion_z, sector_return, market_return, peer_variables_json
    FROM earnings_historical_events_current
    WHERE event_date < ? AND return_horizon_id = ? AND return_horizon_methodology_version = ?
    ORDER BY event_date DESC LIMIT 1000`).bind(run.us_trading_date, RETURN_HORIZON_ID, RETURN_HORIZON_METHODOLOGY_VERSION).all();
  const pModel = buildPModel({ event, research: research.research, history: historyResult.results ?? [], researchCutoff: run.research_cutoff });
  const frozenAt = now.toISOString();
  const freezeCore = {
    run_id: runId,
    event_id: event.event_id,
    ticker: event.ticker,
    event: {
      report_at: event.report_at,
      event_timing: event.event_timing,
      intended_exit_at: event.intended_exit_at,
      timing_source_url: event.timing_source_url,
      timing_verified_at: event.timing_verified_at
    },
    research_evidence: research.research.evidence,
    structured_features: research.research.features,
    research_sha256: research.research_sha256,
    model_version: MODEL_VERSION,
    return_distribution: pModel,
    confidence: pModel.confidence,
    frozen_at: frozenAt,
    p_model_status: "FROZEN",
    market_data: false
  };
  const receipt = await sha256Hex(freezeCore);
  const freeze = { ...freezeCore, freeze_receipt_sha256: receipt };
  const freezeId = randomId("freeze");
  const counts = await db.prepare(`SELECT
      SUM(CASE WHEN eligible = 1 THEN 1 ELSE 0 END) AS eligible_count,
      SUM(CASE WHEN eligible = 1 AND event_id IN (SELECT event_id FROM earnings_freezes WHERE run_id = ?) THEN 1 ELSE 0 END) AS frozen_count,
      SUM(CASE WHEN eligible = 1 AND event_id IN (SELECT event_id FROM earnings_event_dispositions WHERE run_id = ?) THEN 1 ELSE 0 END) AS disposed_count
    FROM earnings_events WHERE run_id = ?`).bind(runId, runId, runId).first();
  const resolvedCount = Number(counts.frozen_count ?? 0) + Number(counts.disposed_count ?? 0) + 1;
  const targetStatus = resolvedCount >= Number(counts.eligible_count ?? 0) ? "FROZEN" : "PARTIALLY_FROZEN";
  const freezeJson = canonicalJson(freeze);
  const decision = { freeze_id: freezeId, freeze_receipt_sha256: receipt, p_model_status: "FROZEN", ticker: event.ticker };
  await db.batch([
    db.prepare(`INSERT INTO earnings_freezes
      (freeze_id, run_id, event_id, ticker, model_version, research_id, research_sha256, freeze_json,
       freeze_receipt_sha256, frozen_at, p_model_status, confidence)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'FROZEN', ?)`)
      .bind(freezeId, runId, event.event_id, event.ticker, MODEL_VERSION, research.research_id, research.research_sha256, freezeJson, receipt, frozenAt, pModel.confidence),
    db.prepare("UPDATE earnings_runs SET status = ?, updated_at = ? WHERE run_id = ?")
      .bind(targetStatus, frozenAt, runId),
    db.prepare(`INSERT INTO earnings_decision_records
      (decision_id, run_id, event_id, record_type, record_json, record_sha256, created_at)
      VALUES (?, ?, ?, 'P_MODEL_FREEZE', ?, ?, ?)`)
      .bind(randomId("decision"), runId, event.event_id, canonicalJson(decision), await sha256Hex(decision), frozenAt)
  ]);
  return freeze;
}

export async function dispositionEvent(db, runId, eventKey, input, now = new Date()) {
  const [run, event] = await Promise.all([fetchRun(db, runId), fetchEvent(db, runId, eventKey)]);
  requireThat(event.eligible === 1, "only an eligible event can receive a run disposition");
  requireThat(!["FROZEN", "VALUED", "CLOSED"].includes(run.status), "run is no longer accepting dispositions");
  const disposition = String(input.disposition ?? "").toUpperCase();
  requireThat(disposition === "DATA_BLOCKED" || disposition === "PASS", "disposition must be DATA_BLOCKED or PASS");
  const reason = String(input.reason ?? "").trim();
  requireThat(reason.length >= 5, "disposition reason required");
  const existingFreeze = await db.prepare("SELECT freeze_id FROM earnings_freezes WHERE run_id = ? AND event_id = ? LIMIT 1").bind(runId, event.event_id).first();
  requireThat(!existingFreeze, "frozen event cannot be passed");
  const nowIso = now.toISOString();
  const counts = await db.prepare(`SELECT
      SUM(CASE WHEN eligible = 1 THEN 1 ELSE 0 END) AS eligible_count,
      SUM(CASE WHEN eligible = 1 AND event_id IN (SELECT event_id FROM earnings_freezes WHERE run_id = ?) THEN 1 ELSE 0 END) AS frozen_count,
      SUM(CASE WHEN eligible = 1 AND event_id IN (SELECT event_id FROM earnings_event_dispositions WHERE run_id = ?) THEN 1 ELSE 0 END) AS disposed_count
    FROM earnings_events WHERE run_id = ?`).bind(runId, runId, runId).first();
  const resolvedCount = Number(counts.frozen_count ?? 0) + Number(counts.disposed_count ?? 0) + 1;
  const targetStatus = resolvedCount >= Number(counts.eligible_count ?? 0) ? "FROZEN" : "PARTIALLY_FROZEN";
  const record = { run_id: runId, event_id: event.event_id, ticker: event.ticker, disposition, reason, created_at: nowIso };
  await db.batch([
    db.prepare(`INSERT INTO earnings_event_dispositions
      (disposition_id, run_id, event_id, disposition, reason, created_at)
      VALUES (?, ?, ?, ?, ?, ?)`)
      .bind(randomId("disposition"), runId, event.event_id, disposition, reason, nowIso),
    db.prepare("UPDATE earnings_runs SET status = ?, updated_at = ? WHERE run_id = ?").bind(targetStatus, nowIso, runId),
    db.prepare(`INSERT INTO earnings_decision_records
      (decision_id, run_id, event_id, record_type, record_json, record_sha256, created_at)
      VALUES (?, ?, ?, 'EVENT_DISPOSITION', ?, ?, ?)`)
      .bind(randomId("decision"), runId, event.event_id, canonicalJson(record), await sha256Hex(record), nowIso)
  ]);
  return record;
}

export async function ingestHistory(db, input, now = new Date()) {
  requireThat(input && typeof input === "object", "history batch required");
  requireThat(/^https:\/\//.test(String(input.source_url ?? "")), "history source_url invalid");
  requireThat(Array.isArray(input.events) && input.events.length > 0 && input.events.length <= 500, "history batch must contain 1-500 events");
  const nowIso = now.toISOString();
  const manifest = {
    source_name: String(input.source_name ?? ""),
    source_revision: String(input.source_revision ?? ""),
    source_url: String(input.source_url),
    as_of: isoTimestamp(input.as_of, "history as_of"),
    count: input.events.length,
    submitted_events_sha256: await sha256Hex(input.events)
  };
  requireThat(manifest.source_name && manifest.source_revision, "history source identity required");
  const manifestSha = await sha256Hex(manifest);
  const batchId = `hist_${manifestSha.slice(0, 32)}`;
  const statements = [db.prepare(`INSERT INTO earnings_history_batches
    (batch_id, source_name, source_revision, source_url, as_of, manifest_json, manifest_sha256, ingested_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)`)
    .bind(batchId, manifest.source_name, manifest.source_revision, manifest.source_url, manifest.as_of, canonicalJson(manifest), manifestSha, nowIso)];
  for (const raw of input.events) {
    const ticker = tickerText(raw.ticker);
    const eventDate = dateOnly(raw.event_date, `history ${ticker} event_date`);
    const version = Math.trunc(Number(raw.event_version ?? 1));
    requireThat(version >= 1, "history event_version invalid");
    const pre = Number(raw.pre_event_price);
    const exit = Number(raw.exit_price);
    requireThat(Number.isFinite(pre) && pre > 0 && Number.isFinite(exit) && exit > 0, `history ${ticker} prices invalid`);
    const eventTiming = String(raw.event_timing).toUpperCase();
    requireThat(eventTiming === "AMC" || eventTiming === "BMO", `history ${ticker} timing invalid`);
    const horizon = validateHistoricalHorizon(raw, eventDate, eventTiming);
    const calculatedReturn = exit / pre - 1;
    if (raw.event_return !== null && raw.event_return !== undefined) {
      requireThat(Number.isFinite(Number(raw.event_return)) && Math.abs(Number(raw.event_return) - calculatedReturn) <= 1e-10, `history ${ticker} event_return does not match timestamped prices`, "DATA_BLOCKED");
    }
    const eventReturn = calculatedReturn;
    const preEventPriceSourceUrl = String(raw.pre_event_price_source_url ?? manifest.source_url);
    const exitPriceSourceUrl = String(raw.exit_price_source_url ?? manifest.source_url);
    requireThat(/^https:\/\//.test(preEventPriceSourceUrl) && /^https:\/\//.test(exitPriceSourceUrl), `history ${ticker} price provenance URL invalid`);
    const normalized = {
      ticker, event_date: eventDate, event_version: version,
      event_timing: eventTiming, sector: String(raw.sector ?? ""), market_cap_cohort: String(raw.market_cap_cohort ?? ""),
      pre_event_price: pre, exit_price: exit, event_return: eventReturn, absolute_return: Math.abs(eventReturn),
      ...horizon, pre_event_price_source_url: preEventPriceSourceUrl, exit_price_source_url: exitPriceSourceUrl,
      gap_open_return: raw.gap_open_return ?? null, realized_vol_20d: raw.realized_vol_20d ?? null, pre_event_drift: raw.pre_event_drift ?? null,
      reported_eps: raw.reported_eps ?? null, consensus_eps: raw.consensus_eps ?? null, reported_revenue: raw.reported_revenue ?? null, consensus_revenue: raw.consensus_revenue ?? null,
      guidance_change_z: raw.guidance_change_z ?? null, estimate_revision_z: raw.estimate_revision_z ?? null, consensus_dispersion_z: raw.consensus_dispersion_z ?? null,
      sector_return: raw.sector_return ?? null, market_return: raw.market_return ?? null, peer_variables: raw.peer_variables ?? null, option_history: raw.option_history ?? null
    };
    requireThat(normalized.sector && normalized.market_cap_cohort, `history ${ticker} cohort fields required`);
    const recordSha = await sha256Hex(normalized);
    statements.push(db.prepare(`INSERT INTO earnings_historical_event_versions
      (historical_id, batch_id, ticker, event_date, event_version, event_timing, sector, market_cap_cohort,
       pre_event_price, pre_event_price_timestamp, pre_event_price_source_url,
       exit_price, exit_price_timestamp, exit_price_source_url, return_horizon_id, return_horizon_methodology_version,
       event_return, absolute_return, gap_open_return, realized_vol_20d,
       pre_event_drift, reported_eps, consensus_eps, reported_revenue, consensus_revenue, guidance_change_z,
       estimate_revision_z, consensus_dispersion_z, sector_return, market_return, peer_variables_json,
       option_history_json, record_sha256, created_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
      .bind(`hev_${recordSha.slice(0, 32)}`, batchId, ticker, eventDate, version, normalized.event_timing, normalized.sector, normalized.market_cap_cohort, pre, normalized.pre_event_price_timestamp, normalized.pre_event_price_source_url, exit, normalized.exit_price_timestamp, normalized.exit_price_source_url, normalized.return_horizon_id, normalized.return_horizon_methodology_version, eventReturn, Math.abs(eventReturn), normalized.gap_open_return, normalized.realized_vol_20d, normalized.pre_event_drift, normalized.reported_eps, normalized.consensus_eps, normalized.reported_revenue, normalized.consensus_revenue, normalized.guidance_change_z, normalized.estimate_revision_z, normalized.consensus_dispersion_z, normalized.sector_return, normalized.market_return, normalized.peer_variables === null ? null : canonicalJson(normalized.peer_variables), normalized.option_history === null ? null : canonicalJson(normalized.option_history), recordSha, nowIso));
  }
  await db.batch(statements);
  return { batch_id: batchId, manifest_sha256: manifestSha, count: input.events.length, ingested_at: nowIso };
}

export async function ingestIvObservations(db, input, now = new Date()) {
  requireThat(Array.isArray(input?.observations) && input.observations.length > 0 && input.observations.length <= 500, "IV observations must contain 1-500 rows");
  const source = String(input.source ?? "").trim();
  const revision = String(input.source_revision ?? "").trim();
  requireThat(source && revision, "IV source and revision required");
  const nowIso = now.toISOString();
  const statements = [];
  for (const raw of input.observations) {
    const row = {
      ticker: tickerText(raw.ticker), event_date: dateOnly(raw.event_date, "IV event_date"), sector: String(raw.sector ?? ""), market_cap_cohort: String(raw.market_cap_cohort ?? ""),
      moneyness_bucket: String(raw.moneyness_bucket ?? ""), dte_bucket: String(raw.dte_bucket ?? ""), residual_iv: Number(raw.residual_iv),
      exit_spread_fraction: raw.exit_spread_fraction === null || raw.exit_spread_fraction === undefined ? null : Number(raw.exit_spread_fraction), source, source_revision: revision
    };
    requireThat(row.sector && row.market_cap_cohort && row.moneyness_bucket && row.dte_bucket, "IV cohort fields required");
    requireThat(Number.isFinite(row.residual_iv) && row.residual_iv > 0 && row.residual_iv < 8, "residual_iv invalid");
    requireThat(row.exit_spread_fraction === null || (Number.isFinite(row.exit_spread_fraction) && row.exit_spread_fraction >= 0 && row.exit_spread_fraction <= 1), "exit_spread_fraction invalid");
    const hash = await sha256Hex(row);
    statements.push(db.prepare(`INSERT INTO earnings_post_event_iv_observations
      (iv_observation_id, ticker, event_date, sector, market_cap_cohort, moneyness_bucket, dte_bucket,
       residual_iv, exit_spread_fraction, source, source_revision, observation_sha256, created_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
      .bind(`iv_${hash.slice(0, 32)}`, row.ticker, row.event_date, row.sector, row.market_cap_cohort, row.moneyness_bucket, row.dte_bucket, row.residual_iv, row.exit_spread_fraction, source, revision, hash, nowIso));
  }
  await db.batch(statements);
  return { count: statements.length, source, source_revision: revision, ingested_at: nowIso };
}

export async function storeMarketInput(db, runId, eventKey, input, riskConfig, now = new Date()) {
  const [run, event] = await Promise.all([fetchRun(db, runId), fetchEvent(db, runId, eventKey)]);
  const freezeRow = await fetchFreeze(db, runId, event.event_id);
  requireThat(freezeRow.freeze.p_model_status === "FROZEN", "P_MODEL_STATUS must be FROZEN", "DATA_BLOCKED");
  const normalized = await validateMarketInput(input, event, freezeRow.freeze, riskConfig, now);
  const marketInputId = randomId("market");
  const nowIso = now.toISOString();
  const statements = [db.prepare(`INSERT INTO earnings_market_inputs
    (market_input_id, run_id, event_id, freeze_id, ticker, source_type, screenshot_sha256, captured_at,
     underlying_price, market_input_json, market_input_sha256, created_at)
    VALUES (?, ?, ?, ?, ?, 'IBKR_SCREENSHOT', ?, ?, ?, ?, ?, ?)`)
    .bind(marketInputId, runId, event.event_id, freezeRow.freeze_id, event.ticker, normalized.screenshot_sha256, normalized.captured_at, normalized.underlying_price, canonicalJson(normalized), normalized.market_input_sha256, nowIso)];
  for (const quote of normalized.quotes) {
    statements.push(db.prepare(`INSERT INTO earnings_option_quotes
      (quote_id, market_input_id, contract_key, expiry, strike, right_type, bid, ask, visible_iv,
       visible_delta, open_interest, volume, spread_fraction)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
      .bind(randomId("quote"), marketInputId, quote.contract_key, quote.expiry, quote.strike, quote.right, quote.bid, quote.ask, quote.iv, quote.delta, quote.open_interest, quote.volume, quote.spread_fraction));
  }
  const decision = { market_input_id: marketInputId, ticker: event.ticker, market_input_sha256: normalized.market_input_sha256, captured_at: normalized.captured_at };
  statements.push(db.prepare(`INSERT INTO earnings_decision_records
    (decision_id, run_id, event_id, record_type, record_json, record_sha256, created_at)
    VALUES (?, ?, ?, 'MARKET_INPUT', ?, ?, ?)`)
    .bind(randomId("decision"), runId, event.event_id, canonicalJson(decision), await sha256Hex(decision), nowIso));
  await db.batch(statements);
  return { market_input_id: marketInputId, ...normalized };
}

export async function valueRun(db, runId, input, riskConfig, now = new Date()) {
  const run = await fetchRun(db, runId);
  requireThat(run.status === "FROZEN", "all eligible events must be frozen or explicitly passed before valuation", "DATA_BLOCKED");
  const supplied = input?.market_input_ids ?? {};
  requireThat(supplied && typeof supplied === "object" && !Array.isArray(supplied), "market_input_ids must map ticker to market_input_id");
  const freezeResult = await db.prepare(`SELECT f.*, e.ticker, e.report_at, e.event_timing, e.sector,
      e.market_cap_cohort, e.intended_exit_at, e.pre_event_price, e.realized_vol_20d
    FROM earnings_freezes f JOIN earnings_events e ON e.event_id = f.event_id
    WHERE f.run_id = ? ORDER BY e.ticker`).bind(runId).all();
  const frozenEvents = freezeResult.results ?? [];
  requireThat(Object.keys(supplied).length === frozenEvents.length, "provide exactly one fresh market input for every frozen event", "DATA_BLOCKED");
  const ivRows = await db.prepare(`SELECT ticker, event_date, sector, market_cap_cohort, moneyness_bucket,
    dte_bucket, residual_iv, exit_spread_fraction FROM earnings_post_event_iv_observations
    WHERE event_date < ? ORDER BY event_date DESC LIMIT 2000`).bind(run.us_trading_date).all();
  const allValuations = [];
  const eventContexts = [];
  for (const row of frozenEvents) {
    const marketInputId = String(supplied[row.ticker] ?? "");
    requireThat(marketInputId, `missing market input for ${row.ticker}`, "DATA_BLOCKED");
    const marketRow = await db.prepare("SELECT * FROM earnings_market_inputs WHERE market_input_id = ? AND run_id = ? AND event_id = ? LIMIT 1").bind(marketInputId, runId, row.event_id).first();
    requireThat(marketRow, `market input not found for ${row.ticker}`, "NOT_FOUND");
    const marketInput = parseJsonColumn(marketRow.market_input_json);
    const ageMinutes = (now.getTime() - Date.parse(marketInput.captured_at)) / 60_000;
    requireThat(ageMinutes <= riskConfig.market_input_max_age_minutes, `IBKR market input is stale for ${row.ticker}`, "DATA_BLOCKED");
    const freeze = parseJsonColumn(row.freeze_json);
    const event = { ...row, event_id: row.event_id };
    const valuations = buildCandidates(marketInput).map((candidate) => ({
      ...valueCandidate({ candidate, marketInput, pModel: freeze.return_distribution, event, ivObservations: ivRows.results ?? [], riskConfig }),
      event_id: row.event_id,
      freeze_id: row.freeze_id,
      market_input_id: marketInputId
    }));
    allValuations.push(...valuations);
    eventContexts.push({ event_id: row.event_id, ticker: row.ticker, freeze_id: row.freeze_id, market_input_id: marketInputId });
  }
  const selection = selectCandidates(allValuations, riskConfig);
  const nowIso = now.toISOString();
  const batchByEvent = new Map();
  const statements = [];
  for (const context of eventContexts) {
    const batchId = randomId("valuation");
    batchByEvent.set(context.event_id, batchId);
    statements.push(db.prepare(`INSERT INTO earnings_valuation_batches
      (valuation_batch_id, run_id, event_id, freeze_id, market_input_id, valuation_version,
       selection_version, risk_config_json, created_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`)
      .bind(batchId, runId, context.event_id, context.freeze_id, context.market_input_id, VALUATION_VERSION, SELECTION_VERSION, canonicalJson(riskConfig), nowIso));
  }
  for (const value of selection.selections) {
    const valuationId = randomId("value");
    value.valuation_id = valuationId;
    statements.push(db.prepare(`INSERT INTO earnings_valuations
      (valuation_id, valuation_batch_id, candidate_id, desk, trade_type, valuation_json, entry_ask,
       max_entry, expected_exit_value, p_profit, expected_net_dollars, ev_per_dollar_risk, max_loss,
       model_edge, confidence, selection, rank, created_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
      .bind(valuationId, batchByEvent.get(value.event_id), value.candidate_id, value.desk, value.trade_type, canonicalJson(value), value.entry_ask, value.max_entry, value.expected_exit_value, value.p_profit, value.expected_net_dollars, value.ev_per_dollar_risk, value.max_loss, value.model_edge, value.confidence, value.selection, value.rank, nowIso));
  }
  const decision = { run_id: runId, batches: Object.fromEntries(eventContexts.map((context) => [context.ticker, batchByEvent.get(context.event_id)])), selection };
  statements.push(db.prepare(`INSERT INTO earnings_decision_records
    (decision_id, run_id, event_id, record_type, record_json, record_sha256, created_at)
    VALUES (?, ?, NULL, 'SELECTION', ?, ?, ?)`)
    .bind(randomId("decision"), runId, canonicalJson(decision), await sha256Hex(decision), nowIso));
  statements.push(db.prepare("UPDATE earnings_runs SET status = 'VALUED', updated_at = ? WHERE run_id = ?").bind(nowIso, runId));
  await db.batch(statements);
  return { run_id: runId, valuation_batches: decision.batches, ...selection, trade_cards: selection.selections.map(tradeCard).filter(Boolean) };
}

export async function getRunState(db, runId) {
  const run = await fetchRun(db, runId);
  const [events, freezes, selections] = await Promise.all([
    db.prepare(`SELECT e.*, d.disposition, d.reason AS disposition_reason
      FROM earnings_events e LEFT JOIN earnings_event_dispositions d ON d.event_id = e.event_id
      WHERE e.run_id = ? ORDER BY e.report_at, e.ticker`).bind(runId).all(),
    db.prepare("SELECT freeze_id, event_id, ticker, freeze_receipt_sha256, frozen_at, confidence FROM earnings_freezes WHERE run_id = ? ORDER BY ticker").bind(runId).all(),
    db.prepare(`SELECT v.valuation_id, v.candidate_id, v.trade_type, v.selection, v.rank, v.expected_net_dollars,
      v.ev_per_dollar_risk, v.p_profit, v.confidence, b.event_id
      FROM earnings_valuations v JOIN earnings_valuation_batches b ON b.valuation_batch_id = v.valuation_batch_id
      WHERE b.run_id = ? ORDER BY v.rank`).bind(runId).all()
  ]);
  return { run, events: events.results ?? [], freezes: freezes.results ?? [], selections: selections.results ?? [] };
}

export async function getFreezeArtifact(db, runId, eventKey) {
  const event = await fetchEvent(db, runId, eventKey);
  return (await fetchFreeze(db, runId, event.event_id)).freeze;
}
