import { requireThat } from "./canonical.js";

const EVENT_LIST_SQL = `
  SELECT
    e.id,
    target.asx_ticker AS ticker,
    target.legal_name AS target_name,
    bidder.legal_name AS bidder_name,
    e.deal_type,
    e.consideration_type,
    e.status,
    e.announcement_date,
    latest.current_market_price AS current_price,
    latest.deal_value,
    latest.break_value_base AS break_value,
    latest.market_implied_probability AS market_probability,
    latest.model_completion_probability AS model_probability,
    latest.fair_value,
    latest.annualised_expected_return,
    latest.decision,
    latest.next_catalyst,
    latest.prediction_timestamp AS model_run_at
  FROM events e
  JOIN companies target ON target.id = e.target_company_id
  LEFT JOIN companies bidder ON bidder.id = e.bidder_company_id
  LEFT JOIN model_runs latest ON latest.id = (
    SELECT mr.id
    FROM model_runs mr
    WHERE mr.event_id = e.id
    ORDER BY mr.prediction_timestamp DESC, mr.id DESC
    LIMIT 1
  )
`;

function boundedLimit(url) {
  const requested = Number(url.searchParams.get("limit") ?? "50");
  if (!Number.isInteger(requested) || requested < 1) return 50;
  return Math.min(requested, 200);
}

export async function listLegacyEvents(request, db) {
  const url = new URL(request.url);
  const status = url.searchParams.get("status") ?? "active";
  const allowed = new Set(["identified", "active", "completed", "failed", "withdrawn", "superseded"]);
  requireThat(allowed.has(status), `Unsupported status: ${status}`);
  const result = await db.prepare(`${EVENT_LIST_SQL} WHERE e.status = ? ORDER BY e.announcement_date DESC LIMIT ?`)
    .bind(status, boundedLimit(url)).all();
  return { data: result.results, meta: { status, count: result.results.length } };
}

export async function getLegacyEvent(eventId, db) {
  const event = await db.prepare(`${EVENT_LIST_SQL} WHERE e.id = ? LIMIT 1`).bind(eventId).first();
  requireThat(event, `No event exists with id ${eventId}`, "NOT_FOUND");
  const [terms, timeline, documents, modelRuns] = await Promise.all([
    db.prepare("SELECT * FROM event_terms WHERE event_id = ? ORDER BY effective_from DESC").bind(eventId).all(),
    db.prepare("SELECT * FROM event_timeline WHERE event_id = ? ORDER BY start_date ASC").bind(eventId).all(),
    db.prepare(`SELECT id, document_type, title, source_url, source_published_at,
      retrieved_at, content_sha256, access_class, extraction_confidence, manually_verified
      FROM event_documents WHERE event_id = ? ORDER BY source_published_at ASC`).bind(eventId).all(),
    db.prepare(`SELECT id, model_version_id, prediction_timestamp, information_cutoff_at,
      current_market_price, deal_value, break_value_base, market_implied_probability,
      model_completion_probability, higher_bid_probability, fair_value, percentage_edge,
      annualised_expected_return, confidence, decision, frozen_at
      FROM model_runs WHERE event_id = ? ORDER BY prediction_timestamp DESC`).bind(eventId).all()
  ]);
  return { data: { ...event, terms: terms.results, timeline: timeline.results, documents: documents.results, modelRuns: modelRuns.results } };
}
