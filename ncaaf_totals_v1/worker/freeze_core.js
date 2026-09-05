/** Market-blind deterministic Layer 2. No network or storage capabilities. */
import bundle from './residual_bundle.js';
export function requireThat(ok, message) { if (!ok) throw new Error(message); }
export function finite(x) { requireThat(typeof x === 'number' && Number.isFinite(x), 'Non-finite/non-numeric value'); return x; }
export function exactKeys(x, keys) {
  requireThat(x && typeof x === 'object' && !Array.isArray(x), 'Expected object');
  requireThat(Object.keys(x).every(k => keys.includes(k)), 'Unknown input field');
}
// Python float formatting rounds the exact IEEE-754 value to nearest, ties-even.
// Number.toFixed rounds ties differently; use the binary mantissa explicitly.
export function fixed(x, places) {
  finite(x);
  const neg = x < 0 || Object.is(x, -0);
  const view = new DataView(new ArrayBuffer(8)); view.setFloat64(0, Math.abs(x));
  const bits = view.getBigUint64(0), exp = Number((bits >> 52n) & 2047n);
  let num = (bits & ((1n << 52n) - 1n)) | (exp ? 1n << 52n : 0n);
  const power = (exp ? exp - 1023 : -1022) - 52;
  num *= 10n ** BigInt(places);
  let den = 1n;
  if (power >= 0) num <<= BigInt(power); else den <<= BigInt(-power);
  let q = num / den; const rem = num % den;
  if (rem * 2n > den || (rem * 2n === den && q % 2n)) q++;
  const s = q.toString().padStart(places + 1, '0');
  return (neg ? '-' : '') + (places ? s.slice(0, -places) + '.' + s.slice(-places) : s);
}
export function canonical(value) {
  if (typeof value === 'number') { finite(value); return JSON.stringify(value); }
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return JSON.stringify(value);
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  requireThat(value && typeof value === 'object', 'Invalid hash material');
  return '{' + Object.keys(value).sort().map(k => JSON.stringify(k) + ':' + canonical(value[k])).join(',') + '}';
}
export async function sha(value) {
  const bytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(canonical(value)));
  return [...new Uint8Array(bytes)].map(x => x.toString(16).padStart(2, '0')).join('');
}
// New full-snapshot hashes encode ALL numbers as exact big-endian binary64 hex.
// Existing anchor/grid hashes retain their exact V1.1.2 formats.
export function receiptMaterial(v) {
  if (typeof v === 'number') {
    finite(v); const b=new DataView(new ArrayBuffer(8)); b.setFloat64(0,v===0?0:v);
    return 'f64:'+b.getBigUint64(0).toString(16).padStart(16,'0');
  }
  if (Array.isArray(v)) return v.map(receiptMaterial);
  if (v && typeof v === 'object') return Object.fromEntries(Object.entries(v).map(([k,x])=>[k,receiptMaterial(x)]));
  return v;
}
export const receiptHash = v => sha(receiptMaterial(v));
export const gridMaterial = grid => grid.map(r => ({line:fixed(r.line,1),over:fixed(r.over,8),push:fixed(r.push,8),under:fixed(r.under,8)}));
export const gridHash = grid => sha(gridMaterial(grid));
export const anchorHash = g => sha({game_id:g.game_id,home_team:g.home_team,away_team:g.away_team,
  expected_total_qbase:fixed(g.expected_total_qbase,6),residual_bucket:g.residual_bucket,
  residual_sd:fixed(g.residual_sd,6),probability_grid:gridMaterial(g.probability_grid)});
export function indexUnique(items, label) {
  requireThat(Array.isArray(items) && items.length, label + ': empty/missing records');
  const map = new Map();
  for (const g of items) {
    requireThat(typeof g.game_id === 'string' && g.game_id.length > 0 && g.game_id === g.game_id.trim(), label + ': invalid game_id');
    requireThat(!map.has(g.game_id), label + ': duplicate game_id'); map.set(g.game_id,g);
  }
  return map;
}
export function auditGrid(grid) {
  requireThat(Array.isArray(grid) && grid.length === 162, 'Incomplete probability grid');
  let over = 1, under = 0;
  grid.forEach((r,i) => {
    requireThat(r.line === 20 + i/2, 'Invalid grid line');
    for (const p of [r.over,r.push,r.under]) requireThat(finite(p)>=0 && p<=1, 'Invalid probability');
    requireThat(Math.abs(r.over+r.push+r.under-1)<=3e-8, 'Probability partition');
    requireThat(r.over<=over+1e-10 && r.under>=under-1e-10, 'Probability monotonicity');
    requireThat(Number.isInteger(r.line) || r.push===0, 'Half-point push');
    over=r.over; under=r.under;
  });
}
export function cutoff(pack) {
  const w=pack.data_state?.current_season_data_through_week;
  if (w===null) {
    for (const g of pack.games) for (const side of ['home_profile','away_profile'])
      for (const key of ['summary','ratings']) requireThat(Object.keys(g[side]?.current?.[key] || {}).length===0, 'Null cutoff with current structured data');
    return 'NO_CURRENT_SEASON_STRUCTURED_DATA_USED';
  }
  requireThat(Number.isInteger(w) && w>=0 && w<=pack.week-1, 'Invalid current-season cutoff');
  return 'CURRENT_SEASON_CUTOFF_PASS';
}
export async function verifySources(pack, qbase, lock) {
  requireThat(pack.market_data===false && qbase.market_data===false, 'Market boundary violation');
  requireThat(pack.schema_version==='0.1.0' && qbase.schema_version==='0.1.0', 'Source schema mismatch');
  for (const x of [pack,qbase]) requireThat(x.slate_id===lock.slate_id && x.season===lock.season && x.week===lock.week, 'Slate identity mismatch');
  requireThat(pack.pack_revision===lock.pack_revision && qbase.research_pack_revision===lock.pack_revision && qbase.qbase_revision===lock.qbase_revision, 'Revision mismatch');
  requireThat(qbase.qbase_model_sha256===bundle.model_sha256 && qbase.qbase_model_version===bundle.model_version, 'QBASE model hash/version mismatch');
  requireThat(qbase.probability_schema_version==='0.2.0' && qbase.integer_line_method==='continuity_corrected_discrete_mass', 'Probability schema mismatch');
  requireThat(pack.source_health?.failed_required?.length===0 && ['PASS','PARTIAL'].includes(pack.source_health?.status), 'Required research source failed');
  const rmap=indexUnique(pack.games,'research'), qmap=indexUnique(qbase.games,'qbase');
  requireThat(rmap.size===qmap.size, 'Research/QBASE universe mismatch');
  const receipts=[];
  for (const gid of [...rmap.keys()].sort()) {
    const r=rmap.get(gid), q=qmap.get(gid);
    requireThat(q && q.home_team===r.fixture?.home_team && q.away_team===r.fixture?.away_team, 'Missing game/team mismatch: '+gid);
    auditGrid(q.probability_grid);
    const anchor=await anchorHash(q);
    requireThat(q.qbase_anchor_sha256===anchor, 'Bad QBASE anchor: '+gid);
    receipts.push({game_id:gid,qbase_anchor_sha256:anchor,qbase_probability_grid_sha256:await gridHash(q.probability_grid)});
  }
  return {rmap,qmap,receipts,cutoff:cutoff(pack)};
}
// Normal CDF via convergent erf power series; tails here are bounded by QBASE
// endpoint quantiles. Beyond |z|=9 the clamped residual CDF is unchanged.
export function normalCDF(z) {
  if (z<=-9) return 0; if(z>=9) return 1;
  // Integrate exp(-t*t/2) using a positive series, avoiding cancellation.
  let term=z, sum=z;
  for(let k=1;k<400;k++) { term*=z*z/(2*k+1); sum+=term; if(Math.abs(term)<Math.abs(sum)*1e-16) break; }
  return Math.max(0,Math.min(1,0.5+sum*Math.exp(-z*z/2)/Math.sqrt(2*Math.PI)));
}
export function residualCDF(r,dist) {
  const levels=dist.quantile_levels, qs=dist.residual_quantiles.map(x=>x-dist.bias_actual_minus_pred), sd=dist.residual_sd;
  if(r<=qs[0]) return Math.max(1e-6,Math.min(levels[0],levels[0]*normalCDF(r/sd)/Math.max(1e-9,normalCDF(qs[0]/sd))));
  const last=qs.length-1;
  if(r>=qs[last]) return Math.max(levels[last],Math.min(1-1e-6,1-(1-levels[last])*(1-normalCDF(r/sd))/Math.max(1e-9,1-normalCDF(qs[last]/sd))));
  let i=1; while(qs[i]<r) i++;
  return levels[i-1]+(r-qs[i-1])/(qs[i]-qs[i-1])*(levels[i]-levels[i-1]);
}
export const TEAM_CHECKS=['qb_backup','offensive_line','skill_defense_absences','coaching_playcaller','transfers_depth','suspensions','rest_travel','late_news'];
export const GAME_CHECKS=['schedule_status','venue_roof_surface','weather'];
function textValue(x) { return typeof x==='string' && x.trim().length>0; }
function checkEvidence(check, now) {
  exactKeys(check,['finding','checked_at','sources','unresolved']);
  requireThat(textValue(check.finding) && typeof check.unresolved==='boolean', 'Incomplete research finding');
  const t=Date.parse(check.checked_at);
  requireThat(Number.isFinite(t) && t<=now+300000 && now-t<=36*3600000, 'Stale/invalid research timestamp');
  requireThat(Array.isArray(check.sources) && check.sources.length>0 && check.sources.every(x=>typeof x==='string' && /^https:\/\//.test(x)), 'Research evidence URLs required');
}
export function validateContext(c, fixture, now) {
  exactKeys(c,['game_id','contextual_shift','distribution_changed','scenarios','confidence','fragility','ledger','research','frozen_thesis']);
  finite(c.contextual_shift);
  requireThat(typeof c.distribution_changed==='boolean', 'distribution_changed must be boolean');
  requireThat(['A','A-','B+','B','B-','C+','C','D'].includes(c.confidence) && ['LOW','MEDIUM','HIGH'].includes(c.fragility), 'Confidence/Fragility required');
  requireThat(textValue(c.frozen_thesis), 'Frozen thesis required');
  exactKeys(c.research,['home_team','away_team','home','away','game','deep_triggers','deep_evidence','market_data']);
  requireThat(c.research.market_data===false && c.research.home_team===fixture.home_team && c.research.away_team===fixture.away_team, 'Research identity/boundary mismatch');
  for(const side of ['home','away']) { exactKeys(c.research[side],TEAM_CHECKS); for(const k of TEAM_CHECKS) checkEvidence(c.research[side][k],now); }
  exactKeys(c.research.game,GAME_CHECKS); for(const k of GAME_CHECKS) checkEvidence(c.research.game[k],now);
  requireThat(Array.isArray(c.research.deep_triggers) && c.research.deep_triggers.every(textValue) && Array.isArray(c.research.deep_evidence), 'Deep research receipt missing');
  if(c.research.deep_triggers.length) requireThat(c.research.deep_evidence.length>0, 'Triggered deep research incomplete');
  c.research.deep_evidence.forEach(x=>checkEvidence(x,now));
  requireThat(Array.isArray(c.ledger), 'Material ledger required');
  for(const l of c.ledger) {
    exactKeys(l,['id','evidence','pathway','impact','quantified_basis']);
    requireThat(['id','pathway','impact','quantified_basis'].every(k=>textValue(l[k])), 'Incomplete material ledger'); checkEvidence(l.evidence,now);
  }
  requireThat(new Set(c.ledger.map(x=>x.id)).size===c.ledger.length, 'Duplicate ledger identifier');
  requireThat(Array.isArray(c.scenarios) && c.scenarios.length>=1 && c.scenarios.length<=8, 'Invalid scenario count');
  let weight=0, shift=0;
  const ledgerIds=new Set(c.ledger.map(x=>x.id));
  for(const s of c.scenarios) {
    exactKeys(s,['id','weight','shift','residual_scale','ledger_ids']);
    requireThat(textValue(s.id) && finite(s.weight)>0 && s.weight<=1 && finite(s.residual_scale)>0, 'Invalid scenario');
    finite(s.shift); weight+=s.weight; shift+=s.weight*s.shift;
    requireThat(Array.isArray(s.ledger_ids) && s.ledger_ids.every(x=>ledgerIds.has(x)), 'Unknown scenario ledger');
    if(s.shift!==0 || s.residual_scale!==1) requireThat(s.ledger_ids.length>0, 'Unledgered adjustment');
  }
  requireThat(new Set(c.scenarios.map(x=>x.id)).size===c.scenarios.length, 'Duplicate scenario');
  requireThat(Math.abs(weight-1)<=1e-8 && Math.abs(shift-c.contextual_shift)<=1e-9, 'Scenario weight/shift mismatch');
  const changed=c.scenarios.length!==1 || c.scenarios[0].residual_scale!==1;
  requireThat(c.distribution_changed===changed, 'Distribution change flag mismatch');
  return c;
}
export async function validateFrozenGame(f,q) {
  requireThat(f.expected_total_qbase===q.expected_total_qbase, 'QBASE total mismatch');
  requireThat(Math.abs(f.expected_total_final-q.expected_total_qbase-f.contextual_shift)<=1e-9, 'Final total mismatch');
  if(Math.abs(f.contextual_shift)<=1e-9 && !f.distribution_changed) {
    requireThat(Math.abs(f.expected_total_final-q.expected_total_qbase)<=1e-9, 'Zero-shift total mismatch');
    requireThat(await gridHash(f.probability_grid)===await gridHash(q.probability_grid), 'Zero-shift grid mismatch');
  }
  auditGrid(f.probability_grid);
}
export async function computeFreeze(pack,qbase,lock,contexts,now) {
  lock={...lock,eligible_game_ids:[...lock.eligible_game_ids].sort()};
  const verified=await verifySources(pack,qbase,lock);
  const cmap=indexUnique(contexts,'contexts'), ids=[...lock.eligible_game_ids].sort();
  requireThat(ids.length>0 && new Set(ids).size===ids.length && ids.length===cmap.size, 'Incomplete/duplicate eligible context set');
  const games=[];
  for(const gid of ids) {
    const r=verified.rmap.get(gid),q=verified.qmap.get(gid),c=cmap.get(gid);
    requireThat(r && q && c, 'Missing eligible game/context');
    requireThat(Date.parse(r.fixture.start_utc)>now && !r.fixture.completed, 'Eligible game has started');
    validateContext(c,r.fixture,now);
    const dist=bundle.residuals[q.residual_bucket]; requireThat(dist,'Unknown residual bucket');
    requireThat(fixed(dist.residual_sd,6)===fixed(q.residual_sd,6), 'Residual SD mismatch');
    let grid;
    if(Math.abs(c.contextual_shift)<=1e-9 && !c.distribution_changed) grid=structuredClone(q.probability_grid);
    else grid=q.probability_grid.map(row=>{
      let under=0,push=0,over=0;
      for(const s of c.scenarios) {
        const mu=q.expected_total_qbase+s.shift;
        const cdf=line=>residualCDF((line-mu)/s.residual_scale,dist);
        const low=cdf(Number.isInteger(row.line)?row.line-0.5:row.line);
        const high=Number.isInteger(row.line)?cdf(row.line+0.5):low;
        under+=s.weight*low; push+=s.weight*(high-low); over+=s.weight*(1-high);
      }
      return {line:row.line,over:Number(fixed(over,8)),push:Number(fixed(push,8)),under:Number(fixed(under,8))};
    });
    const f={game_id:gid,fixture:r.fixture,home_team:q.home_team,away_team:q.away_team,commence_time:r.fixture.start_utc,
      expected_total_raw:q.expected_total_raw,oos_bias_calibration:q.oos_bias_calibration,
      expected_total_qbase:q.expected_total_qbase,contextual_shift:c.contextual_shift,expected_total_final:q.expected_total_qbase+c.contextual_shift,
      distribution_changed:c.distribution_changed,residual_bucket:q.residual_bucket,residual_sd:q.residual_sd,
      residual_method:'qbase_calibrated_residual_cdf_scenario_mixture',probability_grid:grid,
      qbase_anchor_sha256:q.qbase_anchor_sha256,qbase_probability_grid_sha256:await gridHash(q.probability_grid),frozen_probability_grid_sha256:await gridHash(grid),
      confidence:c.confidence,fragility:c.fragility,frozen_thesis:c.frozen_thesis,context:structuredClone(c)};
    await validateFrozenGame(f,q); games.push(f);
  }
  const identity={status:'PASS',game_ids:ids,per_game:games.map(g=>({game_id:g.game_id,qbase_anchor_sha256:g.qbase_anchor_sha256,qbase_probability_grid_sha256:g.qbase_probability_grid_sha256,frozen_probability_grid_sha256:g.frozen_probability_grid_sha256,expected_total_qbase:fixed(g.expected_total_qbase,6),contextual_shift:fixed(g.contextual_shift,12),expected_total_final:fixed(g.expected_total_final,12)}))};
  const result={schema_version:'1.1.3',market_data:false,p_model_status:'FROZEN',frozen_at:new Date(now).toISOString(),
    lock,cutoff_status:verified.cutoff,qbase_model_sha256:bundle.model_sha256,probability_schema_version:'0.2.0',
    identity_binding_audit:'PASS',probability_audit:'PASS',zero_shift_audit:'PASS',verified_anchor_count:verified.receipts.length,
    identity_receipt_sha256:await sha(identity),input_sha256:await receiptHash({lock,contexts:ids.map(g=>cmap.get(g))}),
    numerical_output_sha256:await receiptHash(games),games};
  result.freeze_receipt_sha256=await receiptHash(result);
  return result;
}
