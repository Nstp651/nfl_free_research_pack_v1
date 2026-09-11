/** Server-authoritative NBA V1 runtime scoring. No free-form mean overrides. */
const finite = (v) => { const n = Number(v); return Number.isFinite(n) ? n : null; };
const need = (ok, msg) => { if (!ok) throw new Error(msg); };
const clamp = (v, lo, hi, field) => { const n = finite(v); need(n !== null && n >= lo && n <= hi, `${field} must be in [${lo}, ${hi}]`); return n; };
const canonical = (v) => Array.isArray(v) ? v.map(canonical) : (v && typeof v === 'object' ? Object.fromEntries(Object.keys(v).sort().map(k => [k, canonical(v[k])])) : v);
export async function sha256Json(v) { const b = new TextEncoder().encode(JSON.stringify(canonical(v))); const h = await crypto.subtle.digest('SHA-256', b); return [...new Uint8Array(h)].map(x => x.toString(16).padStart(2, '0')).join(''); }

export function validateQbaseArtifact(a, expectedHead = null) {
  need(a && typeof a === 'object', 'QBASE artifact required');
  need(a.family === 'regularized_poisson_glm', `unsupported family ${a.family}`);
  need(['assists', 'rebounds'].includes(a.head), 'artifact head required');
  if (expectedHead) need(a.head === expectedHead, 'artifact head mismatch');
  for (const k of ['features','medians','centers','scales','coefficients']) need(Array.isArray(a[k]), `${k} required`);
  const n = a.features.length;
  need(n > 0 && ['medians','centers','scales','coefficients'].every(k => a[k].length === n), 'serialized array lengths must match');
  need(new Set(a.features.map(String)).size === n, 'duplicate features');
  a.scales.forEach((v, i) => need(finite(v) !== null && Number(v) !== 0, `invalid scale ${i}`));
  need(finite(a.intercept) !== null, 'intercept required');
  need(finite(a.dispersion_alpha) !== null && Number(a.dispersion_alpha) >= 0, 'dispersion_alpha invalid');
  return a;
}

export async function scoreQbase(a, featureValues) {
  validateQbaseArtifact(a);
  need(featureValues && typeof featureValues === 'object' && !Array.isArray(featureValues), 'feature_values object required');
  let eta = Number(a.intercept); const resolved = {}; const imputed = [];
  for (let i = 0; i < a.features.length; i++) {
    const name = String(a.features[i]); let value = finite(featureValues[name]);
    if (value === null) { value = Number(a.medians[i]); imputed.push(name); }
    resolved[name] = value; eta += Number(a.coefficients[i]) * ((value - Number(a.centers[i])) / Number(a.scales[i]));
  }
  eta = Math.min(eta, Math.log(60));
  const mean = Math.max(0.01, Math.min(60, Math.exp(eta)));
  const receipt = { head: a.head, family: a.family, trained_before_season: a.trained_before_season, artifact_sha256: await sha256Json(a), resolved_features: resolved };
  return { mean, dispersion_alpha: Number(a.dispersion_alpha), linear_predictor: eta, resolved_features: resolved, imputed_features: imputed, quant_input_receipt_sha256: await sha256Json(receipt) };
}

const sharedAllowed = new Set(['season_games_before','team_games_before','team_rest_days','player_days_since_last_game','team_changed_since_last_game','starter_prev','start_rate_l5','start_rate_l10','minutes_l3','minutes_l5','minutes_l10','minutes_l20','team_possessions_l5','team_possessions_l10']);
const headAllowed = {
  assists: new Set(['assists_l3','assists_l5','assists_l10','assists_l20','assists_per_min_l5','assists_per_min_l10','assist_share_l5','assist_share_l10','turnovers_l5','fga_l5','team_assists_l5','team_assists_l10','opponent_assists_allowed_l5','opponent_assists_allowed_l10']),
  rebounds: new Set(['rebounds_l3','rebounds_l5','rebounds_l10','rebounds_l20','offensive_rebounds_l5','defensive_rebounds_l5','rebounds_per_min_l5','rebounds_per_min_l10','rebound_share_l5','rebound_share_l10','team_rebounds_l5','team_rebounds_l10','opponent_rebounds_allowed_l5','opponent_rebounds_allowed_l10'])
};

function setIfPresent(out, artifact, key, value, lo, hi) { if (artifact.features.includes(key)) out[key] = clamp(value, lo, hi, key); }
function featureStats(artifact,key){const i=artifact.features.indexOf(key);need(i>=0,`unsupported promoted feature ${key}`);const center=finite(artifact.centers[i]),scale=Math.abs(Number(artifact.scales[i]));need(center!==null&&Number.isFinite(scale)&&scale>0,`invalid promoted feature statistics ${key}`);return {center,scale};}
function minimumShiftFloor(key){if(key.includes('share')||key.includes('rate'))return .05;if(key.includes('possessions'))return 8;if(key.startsWith('team_')||key.startsWith('opponent_'))return 6;if(key.startsWith('minutes_'))return 6;return 4;}
function empiricalTransformValue(artifact,baseFeatures,key,raw,lo,hi){
  const n=clamp(raw,lo,hi,key),{center,scale}=featureStats(artifact,key);const envelopeLo=Math.max(lo,center-6*scale),envelopeHi=Math.min(hi,center+6*scale);need(n>=envelopeLo-1e-12&&n<=envelopeHi+1e-12,`${key} outside promoted training envelope`);const base=finite(baseFeatures[key]);if(base!==null){const maxShift=Math.max(4*scale,minimumShiftFloor(key));need(Math.abs(n-base)<=maxShift+1e-12,`${key} change exceeds promoted transform envelope`);}return n;
}

export function applyTypedTransform(artifact, baseFeatures, transform) {
  validateQbaseArtifact(artifact);
  need(baseFeatures && typeof baseFeatures === 'object', 'base_features required');
  need(transform && typeof transform === 'object', 'transform required');
  const type = String(transform.type || ''); const out = { ...baseFeatures };
  if (type === 'QBASE_RUNTIME_SCORE') return { features: out, transform_receipt: { type } };
  if (type === 'MINUTES_RECOMPUTE') {
    const m = clamp(transform.projected_minutes, 0, 48, 'projected_minutes');
    for (const k of ['minutes_l3','minutes_l5','minutes_l10','minutes_l20']) setIfPresent(out, artifact, k, m, 0, 48);
    if (transform.starter_probability !== undefined) {
      const s = clamp(transform.starter_probability, 0, 1, 'starter_probability');
      for (const k of ['start_rate_l5','start_rate_l10']) setIfPresent(out, artifact, k, s, 0, 1);
      setIfPresent(out, artifact, 'starter_prev', s >= 0.5 ? 1 : 0, 0, 1);
    }
    return { features: out, transform_receipt: { type, projected_minutes: m, starter_probability: transform.starter_probability ?? null } };
  }
  if (type === 'ROLE_OPPORTUNITY_RECOMPUTE') {
    need(transform.inputs && typeof transform.inputs === 'object', 'role inputs required');
    const allowed = new Set([...sharedAllowed, ...headAllowed[artifact.head]]);
    const accepted={};
    for (const [k, raw] of Object.entries(transform.inputs)) {
      need(allowed.has(k) && artifact.features.includes(k), `unsupported role feature ${k}`);
      let lo = 0, hi = 100;
      if (k.includes('share') || k.includes('rate') || k === 'starter_prev' || k === 'team_changed_since_last_game') hi = 1;
      if (k.includes('per_min')) hi = 2;
      if (k.startsWith('minutes_')) hi = 48;
      out[k] = empiricalTransformValue(artifact,baseFeatures,k,raw,lo,hi);accepted[k]=out[k];
    }
    return { features: out, transform_receipt: { type, inputs: accepted, empirical_guardrail:'PROMOTED_CENTER_6SD_AND_BASE_SHIFT_4SD' } };
  }
  if (type === 'LINEUP_DEPENDENCY_RECOMPUTE') {
    need(transform.inputs && typeof transform.inputs === 'object', 'lineup inputs required');
    const allowed = artifact.head === 'assists'
      ? new Set(['team_assists_l5','team_assists_l10','opponent_assists_allowed_l5','opponent_assists_allowed_l10','team_possessions_l5','team_possessions_l10'])
      : new Set(['team_rebounds_l5','team_rebounds_l10','opponent_rebounds_allowed_l5','opponent_rebounds_allowed_l10','team_possessions_l5','team_possessions_l10']);
    const accepted={};for (const [k, raw] of Object.entries(transform.inputs)) { need(allowed.has(k) && artifact.features.includes(k), `unsupported lineup feature ${k}`); out[k] = empiricalTransformValue(artifact,baseFeatures,k,raw,0,160);accepted[k]=out[k]; }
    return { features: out, transform_receipt: { type, inputs: accepted, empirical_guardrail:'PROMOTED_CENTER_6SD_AND_BASE_SHIFT_4SD' } };
  }
  throw new Error(`unsupported transform ${type}`);
}

export async function scoreRuntime(artifact, baseFeatures, transforms = [{ type: 'QBASE_RUNTIME_SCORE' }]) {
  need(Array.isArray(transforms) && transforms.length >= 1 && transforms.length <= 4, '1-4 typed transforms required');
  let features = { ...baseFeatures }; const receipts = [];
  for (const t of transforms) { const r = applyTypedTransform(artifact, features, t); features = r.features; receipts.push(r.transform_receipt); }
  const scored = await scoreQbase(artifact, features);
  return { ...scored, transform_receipts: receipts, transform_chain_sha256: await sha256Json(receipts) };
}
