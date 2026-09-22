import { FEATURE_CONTRACT_VERSION, SOURCE_HIERARCHY } from "./config.js";
import { isoTimestamp, requireThat, tickerText } from "./canonical.js";
import { scoreFeatureInputs, validateFeatureEvidence } from "./feature-contract.js";

const MARKET_KEY_PATTERN = /(?:^|_)(?:options?|option_market|option_pric(?:e|es|ing)|premiums?|straddles?|strangles?|implied_(?:move|volatility|probability|distribution)|market_implied|iv(?:_crush)?|volatility_(?:skew|smile|surface|term_structure)|open_interest|greeks?|delta|gamma|theta|vega|rho|call_(?:bid|ask)|put_(?:bid|ask)|option_volume)(?:$|_)/i;
const MARKET_TEXT_PATTERNS = Object.freeze([
  /\b(?:straddles?|strangles?)\b/i,
  /\boptions?[- ](?:market|derived|implied|price|prices|pricing|premium|premiums|quote|quotes|volume|open interest|flow|chain)\b/i,
  /\b(?:call|put)\s+(?:bid|ask|premium|price|quote|volume|open interest)\b/i,
  /\b(?:market[- ]implied|implied)\s+(?:move|volatility|vol|probability|distribution)\b/i,
  /\b(?:iv|implied vol)(?:\s+crush)?\b/i,
  /\b(?:iv|vol|volatility)\s+(?:skew|smile|surface|term structure)\b/i,
  /\bterm structure\s+of\s+(?:iv|implied volatility|volatility)\b/i,
  /\bopen interest\b/i,
  /\b(?:option )?greeks?\b/i,
  /\b(?:delta|gamma|theta|vega|rho)\b/i,
  /\b(?:earnings|event)\s+move\s+(?:priced in|implied by|derived from)\b/i
]);

function keyText(value) {
  return String(value).replace(/([a-z0-9])([A-Z])/g, "$1_$2").replace(/[^A-Za-z0-9]+/g, "_").toLowerCase();
}

export function findMarketContamination(value, path = "$", hits = []) {
  if (value === null || value === undefined) return hits;
  if (typeof value === "string") {
    if (MARKET_TEXT_PATTERNS.some((pattern) => pattern.test(value))) hits.push(path);
    return hits;
  }
  if (Array.isArray(value)) {
    value.forEach((item, index) => findMarketContamination(item, `${path}[${index}]`, hits));
    return hits;
  }
  if (typeof value === "object") {
    for (const [key, nested] of Object.entries(value)) {
      const next = `${path}.${key}`;
      if (MARKET_KEY_PATTERN.test(keyText(key))) hits.push(next);
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
  requireThat(input.feature_contract_version === FEATURE_CONTRACT_VERSION, `feature_contract_version must be ${FEATURE_CONTRACT_VERSION}`);
  requireThat(input.features === undefined, "features are server-derived; submit feature_inputs instead");
  const contamination = findMarketContamination(input);
  requireThat(contamination.length === 0, `market-blind boundary breached at ${contamination.join(", ")}`, "MARKET_CONTAMINATION");
  const cutoff = Date.parse(researchCutoff);
  requireThat(Number.isFinite(cutoff), "research cutoff invalid");
  requireThat(Array.isArray(input.evidence) && input.evidence.length > 0, "research evidence required");
  const evidenceById = new Map();
  for (const evidence of input.evidence) {
    requireThat(evidence && typeof evidence === "object", "research evidence row invalid");
    const evidenceId = String(evidence.evidence_id ?? "").trim();
    requireThat(/^[A-Za-z0-9._:-]{3,100}$/.test(evidenceId), "evidence_id invalid");
    requireThat(!evidenceById.has(evidenceId), `duplicate evidence_id ${evidenceId}`);
    requireThat(SOURCE_HIERARCHY.includes(String(evidence.source_type)), `unsupported evidence source_type ${evidence.source_type}`);
    evidenceById.set(evidenceId, { ...evidence, source_type: String(evidence.source_type) });
    requireThat(/^https:\/\//.test(String(evidence.url ?? "")), `evidence ${evidenceId} URL invalid`);
    requireThat(String(evidence.title ?? "").trim().length >= 3, `evidence ${evidenceId} title required`);
    requireThat(String(evidence.fact ?? "").trim().length >= 3, `evidence ${evidenceId} extracted fact required`);
    const retrieved = Date.parse(isoTimestamp(evidence.retrieved_at, `evidence ${evidenceId} retrieved_at`));
    requireThat(retrieved <= cutoff, `evidence ${evidenceId} was retrieved after research cutoff`);
    if (evidence.published_at !== null && evidence.published_at !== undefined) {
      requireThat(Date.parse(isoTimestamp(evidence.published_at, `evidence ${evidenceId} published_at`)) <= cutoff, `evidence ${evidenceId} was published after research cutoff`);
    }
  }
  const normalizedFeatures = scoreFeatureInputs(input.feature_inputs);
  const normalizedFeatureEvidence = validateFeatureEvidence(input.feature_evidence, evidenceById);
  const conflicts = Array.isArray(input.conflicts) ? input.conflicts : [];
  const unresolvedMaterial = conflicts.filter((conflict) => conflict?.material === true && conflict?.resolved !== true);
  requireThat(unresolvedMaterial.length === 0, "unresolved material research conflict", "DATA_BLOCKED");
  requireThat(["HIGH", "MEDIUM", "LOW"].includes(String(input.evidence_quality)), "evidence_quality invalid");
  return {
    ...input,
    ticker: tickerText(input.ticker),
    features: normalizedFeatures,
    feature_evidence: normalizedFeatureEvidence,
    conflicts,
    model_feature_contract: FEATURE_CONTRACT_VERSION
  };
}
