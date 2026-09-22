import { clamp, requireThat, round } from "./canonical.js";

export function mean(values) {
  requireThat(values.length > 0, "mean requires observations");
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

export function sampleStd(values) {
  if (values.length < 2) return 0;
  const center = mean(values);
  return Math.sqrt(
    values.reduce((sum, value) => sum + (value - center) ** 2, 0) /
      (values.length - 1)
  );
}

export function median(values) {
  return quantile(values, 0.5);
}

export function quantile(values, probability) {
  requireThat(values.length > 0, "quantile requires observations");
  requireThat(probability >= 0 && probability <= 1, "quantile probability invalid");
  const sorted = [...values].sort((a, b) => a - b);
  const position = probability * (sorted.length - 1);
  const lower = Math.floor(position);
  const upper = Math.ceil(position);
  if (lower === upper) return sorted[lower];
  return sorted[lower] + (sorted[upper] - sorted[lower]) * (position - lower);
}

// Peter J. Acklam's inverse-normal approximation, deterministic and dependency-free.
export function inverseNormal(probability) {
  requireThat(probability > 0 && probability < 1, "inverseNormal probability invalid");
  const a = [-39.69683028665376, 220.9460984245205, -275.9285104469687, 138.357751867269, -30.66479806614716, 2.506628277459239];
  const b = [-54.47609879822406, 161.5858368580409, -155.6989798598866, 66.80131188771972, -13.28068155288572];
  const c = [-0.007784894002430293, -0.3223964580411365, -2.400758277161838, -2.549732539343734, 4.374664141464968, 2.938163982698783];
  const d = [0.007784695709041462, 0.3224671290700398, 2.445134137142996, 3.754408661907416];
  const low = 0.02425;
  const high = 1 - low;
  if (probability < low) {
    const q = Math.sqrt(-2 * Math.log(probability));
    return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) /
      ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1);
  }
  if (probability <= high) {
    const q = probability - 0.5;
    const r = q * q;
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q /
      (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1);
  }
  const q = Math.sqrt(-2 * Math.log(1 - probability));
  return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) /
    ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1);
}

export function normalCdf(value) {
  const sign = value < 0 ? -1 : 1;
  const x = Math.abs(value) / Math.sqrt(2);
  const t = 1 / (1 + 0.3275911 * x);
  const erf = 1 - (((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t) * Math.exp(-x * x);
  return 0.5 * (1 + sign * erf);
}

export function weightedAverage(items) {
  const denominator = items.reduce((sum, item) => sum + item.weight, 0);
  requireThat(denominator > 0, "weightedAverage requires positive weight");
  return items.reduce((sum, item) => sum + item.value * item.weight, 0) / denominator;
}

export function credibleWeight(count, prior) {
  return count <= 0 ? 0 : count / (count + prior);
}

export function summarizeDraws(draws) {
  requireThat(draws.length > 0 && draws.every(Number.isFinite), "distribution draws invalid");
  const thresholds = [0.02, 0.03, 0.05, 0.075, 0.10];
  const tails = Object.fromEntries(
    thresholds.map((threshold) => [
      `P_ABS_GT_${String(threshold * 100).replace(".", "_")}_PCT`,
      round(draws.filter((value) => Math.abs(value) > threshold).length / draws.length)
    ])
  );
  return {
    p_up: round(draws.filter((value) => value > 0).length / draws.length),
    p_down: round(draws.filter((value) => value <= 0).length / draws.length),
    expected_return: round(mean(draws)),
    median_return: round(median(draws)),
    expected_abs_move: round(mean(draws.map(Math.abs))),
    quantiles: {
      p05: round(quantile(draws, 0.05)),
      p10: round(quantile(draws, 0.10)),
      p25: round(quantile(draws, 0.25)),
      p50: round(quantile(draws, 0.50)),
      p75: round(quantile(draws, 0.75)),
      p90: round(quantile(draws, 0.90)),
      p95: round(quantile(draws, 0.95))
    },
    tail_probabilities: tails,
    support: {
      minimum: round(Math.min(...draws)),
      maximum: round(Math.max(...draws)),
      draw_count: draws.length
    }
  };
}

export function winsorize(value, limit) {
  return clamp(value, -Math.abs(limit), Math.abs(limit));
}
