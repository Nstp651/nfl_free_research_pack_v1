import { MODEL_CONFIG, REQUIRED_FEATURES, SOURCE_HIERARCHY } from "./config.js";
import { finiteNumber, isoTimestamp, requireThat, tickerText } from "./canonical.js";

const MARKET_KEY_PATTERN = /^(?:option|options|option_price|premium|implied_move|implied_probability|implied_volatility|iv|call_bid|call_ask|put_bid|put_ask|bid|ask|greeks?|delta|gamma|theta|vega)$/i;
const MARKET_TEXT_PATTERN = /\b(?:option premium|implied move|implied volatility|call bid|call ask|put bid|put ask|option-derived probability)\b/i;

export function findMarketContamination(value, path = "$", hits = []) {
  if (value === null || value === undefined) return hits;
  if (typeof value === "string") {
    if (MARKET_TEXT_PATTERN.test(value)) hits.push(path);
    return hits;
  }
  if (Array.isArray(value)) {
    value.forEach((item, index) => findMarketContamination(item, `${path}[${index}]`, hits));
    return hits;
  }
  if (typeof value === "object") {
    for (const [key, nested] of Object.entries(value)) {
      const next = `${path}.${key}`;
      if (MARKET_KEY_PATTERN.test(key)) hits.push(next);
      findMarketContamination(nested, next, hits);
    }
  }
  return hits;
}

export function validateResearchPack(input, event, researchCutoff) {
  requireThat(input && typeof input === "object" && !Array.isArray(input), "research pack required");
  requireThat(tickerText(input.ticker) === tickerText(event.ticker), "research ticker mismatch");
  requireThat(String(input.event_id) === String(event.event_id), "research event_id mismatch");
  requireThat(input.market_data === false, "research pack must declare market_data=false", "MARKET_CONTAMINATION");
  const contamination = findMarketContamination(input);
  requireThat(contamination.length === 0, `market-blind boundary breached at ${contamination.join(", ")}`, "MARKET_CONTAMINATION");
  const cutoff = Date.parse(researchCutoff);
  requireThat(Number.isFinite(cutoff), "research cutoff invalid");
  requireThat(Array.isArray(input.evidence) && input.evidence.length > 0, "research evidence required");
  const evidenceIds = new Set();
  for (const evidence of input.evidence) {
    requireThat(evidence && typeof evidence === "object", "research evidence row invalid");
    const evidenceId = String(evidence.evidence_id ?? "").trim();
    requireThat(/^[A-Za-z0-9._:-]{3,100}$/.test(evidenceId), "evidence_id invalid");
    requireThat(!evidenceIds.has(evidenceId), `duplicate evidence_id ${evidenceId}`);
    evidenceIds.add(evidenceId);
    requireThat(SOURCE_HIERARCHY.includes(String(evidence.source_type)), `unsupported evidence source_type ${evidence.source_type}`);
    requireThat(/^https:\/\//.test(String(evidence.url ?? "")), `evidence ${evidenceId} URL invalid`);
    requireThat(String(evidence.title ?? "").trim().length >= 3, `evidence ${evidenceId} title required`);
    requireThat(String(evidence.fact ?? "").trim().length >= 3, `evidence ${evidenceId} extracted fact required`);
    const retrieved = Date.parse(isoTimestamp(evidence.retrieved_at, `evidence ${evidenceId} retrieved_at`));
    requireThat(retrieved <= cutoff, `evidence ${evidenceId} was retrieved after research cutoff`);
    if (evidence.published_at !== null && evidence.published_at !== undefined) {
      requireThat(Date.parse(isoTimestamp(evidence.published_at, `evidence ${evidenceId} published_at`)) <= cutoff, `evidence ${evidenceId} was published after research cutoff`);
    }
  }
  requireThat(input.features && typeof input.features === "object", "structured features required");
  const normalizedFeatures = {};
  const featureEvidence = input.feature_evidence ?? {};
  for (const name of REQUIRED_FEATURES) {
    const value = finiteNumber(input.features[name], `feature ${name}`);
    requireThat(value >= -3 && value <= 3, `feature ${name} must be within [-3, 3]`);
    normalizedFeatures[name] = value;
    const mappings = featureEvidence[name];
    requireThat(Array.isArray(mappings) && mappings.length > 0, `feature ${name} lacks evidence mapping`);
    requireThat(mappings.every((id) => evidenceIds.has(String(id))), `feature ${name} cites unknown evidence`);
  }
  const extraFeatures = Object.keys(input.features).filter((name) => !REQUIRED_FEATURES.includes(name));
  requireThat(extraFeatures.length === 0, `unversioned feature(s): ${extraFeatures.join(", ")}`);
  const conflicts = Array.isArray(input.conflicts) ? input.conflicts : [];
  const unresolvedMaterial = conflicts.filter((conflict) => conflict?.material === true && conflict?.resolved !== true);
  requireThat(unresolvedMaterial.length === 0, "unresolved material research conflict", "DATA_BLOCKED");
  requireThat(["HIGH", "MEDIUM", "LOW"].includes(String(input.evidence_quality)), "evidence_quality invalid");
  return {
    ...input,
    ticker: tickerText(input.ticker),
    features: normalizedFeatures,
    feature_evidence: Object.fromEntries(REQUIRED_FEATURES.map((name) => [name, [...featureEvidence[name]].map(String).sort()])),
    conflicts,
    model_feature_contract: MODEL_CONFIG.model_version
  };
}
