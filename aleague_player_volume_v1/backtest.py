"""Leakage-safe historical evaluation for A-League Player Volume V1.

The backtest layer is deliberately sportsbook-free. It evaluates only frozen
pre-match forecasts against realised counts and may be run before any price data
exists. Production gates are pre-registered here so they cannot be relaxed after
seeing a holdout result without an explicit model-version change and rationale.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from math import exp, lgamma, log
from typing import Any, Dict, Iterable, Mapping, Sequence

from .model_core import ModelIntegrityError, negative_binomial_log_pmf, probability_at_least


VALID_HEADS = frozenset({"SHOTS", "SOT", "SAVES"})
HEAD_THRESHOLDS: Mapping[str, tuple[int, ...]] = {
    "SHOTS": (1, 2, 3, 4, 5, 6),
    "SOT": (1, 2, 3, 4),
    "SAVES": (1, 2, 3, 4, 5, 6),
}

# Initial gates are intentionally registered before the historical holdout is
# available. Any later change must be accompanied by a model-version bump and a
# written reason; do not tune these against the test set.
DEFAULT_MIN_SAMPLES: Mapping[str, int] = {"SHOTS": 500, "SOT": 500, "SAVES": 150}
DEFAULT_MAX_THRESHOLD_ECE = 0.07
DEFAULT_MAX_ABS_MEAN_BIAS_RATIO = 0.12
DEFAULT_MIN_BASELINE_NLL_IMPROVEMENT = 0.005
DEFAULT_MIN_BASELINE_BRIER_IMPROVEMENT = 0.002
DEFAULT_MAX_POISSON_RELATIVE_REGRESSION = 0.002


def _utc(value: str, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ModelIntegrityError(f"{label} is required")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ModelIntegrityError(f"{label} must be ISO-8601") from exc
    if dt.tzinfo is None:
        raise ModelIntegrityError(f"{label} must be timezone-aware")
    return dt.astimezone(timezone.utc)


@dataclass(frozen=True)
class CountForecastObservation:
    fixture_id: str
    kickoff_utc: str
    forecast_created_utc: str
    player_id: str
    head: str
    mean: float
    dispersion: float
    actual_count: int
    baseline_mean: float | None = None
    source_run_id: str | None = None

    def validate(self) -> None:
        if not self.fixture_id or not self.player_id:
            raise ModelIntegrityError("fixture_id and player_id are required")
        if self.head not in VALID_HEADS:
            raise ModelIntegrityError(f"unsupported backtest head {self.head}")
        if self.mean < 0 or self.dispersion <= 0:
            raise ModelIntegrityError("forecast mean must be >= 0 and dispersion > 0")
        if isinstance(self.actual_count, bool) or not isinstance(self.actual_count, int) or self.actual_count < 0:
            raise ModelIntegrityError("actual_count must be a nonnegative integer")
        if self.baseline_mean is not None and self.baseline_mean < 0:
            raise ModelIntegrityError("baseline_mean must be nonnegative")
        kickoff = _utc(self.kickoff_utc, "kickoff_utc")
        created = _utc(self.forecast_created_utc, "forecast_created_utc")
        if created >= kickoff:
            raise ModelIntegrityError("historical forecast must exist strictly before kickoff")

    @property
    def identity(self) -> tuple[str, str, str]:
        return self.fixture_id, self.player_id, self.head


def _ordered_unique(rows: Iterable[CountForecastObservation]) -> list[CountForecastObservation]:
    out: list[CountForecastObservation] = []
    seen = set()
    for row in rows:
        row.validate()
        if row.identity in seen:
            raise ModelIntegrityError(f"duplicate backtest forecast {row.identity}")
        seen.add(row.identity)
        out.append(row)
    return sorted(out, key=lambda r: (_utc(r.kickoff_utc, "kickoff_utc"), r.fixture_id, r.player_id, r.head))


def poisson_log_pmf(k: int, mean: float) -> float:
    if k < 0 or mean < 0:
        raise ModelIntegrityError("Poisson k/mean must be nonnegative")
    if mean == 0:
        return 0.0 if k == 0 else float("-inf")
    return k * log(mean) - mean - lgamma(k + 1)


def poisson_probability_at_least(threshold: int, mean: float) -> float:
    if threshold <= 0:
        return 1.0
    if mean < 0:
        raise ModelIntegrityError("Poisson mean must be nonnegative")
    cdf = 0.0
    for k in range(threshold):
        value = poisson_log_pmf(k, mean)
        cdf += 0.0 if value == float("-inf") else exp(value)
    return min(1.0, max(0.0, 1.0 - cdf))


def _safe_nll(log_probability: float) -> float:
    # A truly impossible realised event should be punished but must not emit inf
    # into JSON reports. 1e-15 corresponds to ~34.54 nats.
    return -max(log_probability, log(1e-15))


def _calibration_bins(points: Sequence[tuple[float, int]], bin_count: int = 10) -> tuple[list[Dict[str, Any]], float]:
    if bin_count < 2:
        raise ModelIntegrityError("calibration bin_count must be >= 2")
    buckets: list[list[tuple[float, int]]] = [[] for _ in range(bin_count)]
    for probability, outcome in points:
        if not 0.0 <= probability <= 1.0 or outcome not in {0, 1}:
            raise ModelIntegrityError("invalid calibration point")
        index = min(bin_count - 1, int(probability * bin_count))
        buckets[index].append((probability, outcome))
    rows: list[Dict[str, Any]] = []
    total = len(points)
    ece = 0.0
    for index, bucket in enumerate(buckets):
        if not bucket:
            continue
        predicted = sum(item[0] for item in bucket) / len(bucket)
        observed = sum(item[1] for item in bucket) / len(bucket)
        gap = observed - predicted
        if total:
            ece += len(bucket) / total * abs(gap)
        rows.append({
            "bin": index,
            "count": len(bucket),
            "predicted_probability": predicted,
            "observed_rate": observed,
            "calibration_gap": gap,
        })
    return rows, ece


def score_head(rows: Sequence[CountForecastObservation]) -> Dict[str, Any]:
    if not rows:
        raise ModelIntegrityError("cannot score empty head")
    head = rows[0].head
    if any(row.head != head for row in rows):
        raise ModelIntegrityError("score_head received mixed heads")

    thresholds = HEAD_THRESHOLDS[head]
    count = len(rows)
    actual_mean = sum(row.actual_count for row in rows) / count
    predicted_mean = sum(row.mean for row in rows) / count
    mae = sum(abs(row.actual_count - row.mean) for row in rows) / count
    nll = 0.0
    poisson_nll = 0.0
    brier_sum = 0.0
    poisson_brier_sum = 0.0
    points: list[tuple[float, int]] = []
    baseline_nll = 0.0
    baseline_brier_sum = 0.0
    baseline_rows = 0

    for row in rows:
        nll += _safe_nll(negative_binomial_log_pmf(row.actual_count, row.mean, row.dispersion))
        poisson_nll += _safe_nll(poisson_log_pmf(row.actual_count, row.mean))
        for threshold in thresholds:
            outcome = int(row.actual_count >= threshold)
            p = probability_at_least(threshold, row.mean, row.dispersion)
            pp = poisson_probability_at_least(threshold, row.mean)
            brier_sum += (p - outcome) ** 2
            poisson_brier_sum += (pp - outcome) ** 2
            points.append((p, outcome))
        if row.baseline_mean is not None:
            baseline_rows += 1
            baseline_nll += _safe_nll(
                negative_binomial_log_pmf(row.actual_count, row.baseline_mean, row.dispersion)
            )
            for threshold in thresholds:
                outcome = int(row.actual_count >= threshold)
                bp = probability_at_least(threshold, row.baseline_mean, row.dispersion)
                baseline_brier_sum += (bp - outcome) ** 2

    calibration, ece = _calibration_bins(points)
    denominator = count * len(thresholds)
    result: Dict[str, Any] = {
        "head": head,
        "count": count,
        "actual_mean": actual_mean,
        "predicted_mean": predicted_mean,
        "mean_bias": predicted_mean - actual_mean,
        "mean_bias_ratio": (predicted_mean - actual_mean) / max(actual_mean, 0.25),
        "mae": mae,
        "nll": nll / count,
        "poisson_same_mean_nll": poisson_nll / count,
        "milestone_brier": brier_sum / denominator,
        "poisson_same_mean_milestone_brier": poisson_brier_sum / denominator,
        "threshold_ece": ece,
        "calibration_bins": calibration,
        "thresholds": list(thresholds),
        "baseline_coverage_rate": baseline_rows / count,
    }
    if baseline_rows:
        baseline_denominator = baseline_rows * len(thresholds)
        result["baseline_nll"] = baseline_nll / baseline_rows
        result["baseline_milestone_brier"] = baseline_brier_sum / baseline_denominator
        result["nll_improvement_vs_baseline"] = (
            result["baseline_nll"] - result["nll"]
        ) / max(result["baseline_nll"], 1e-12)
        result["brier_improvement_vs_baseline"] = (
            result["baseline_milestone_brier"] - result["milestone_brier"]
        ) / max(result["baseline_milestone_brier"], 1e-12)
    return result


def score_forecasts(rows: Iterable[CountForecastObservation]) -> Dict[str, Any]:
    ordered = _ordered_unique(rows)
    by_head: Dict[str, list[CountForecastObservation]] = {head: [] for head in VALID_HEADS}
    for row in ordered:
        by_head[row.head].append(row)
    reports = {head: score_head(values) for head, values in sorted(by_head.items()) if values}
    return {
        "schema_version": "aleague_player_volume_backtest_v1",
        "rows": len(ordered),
        "heads": reports,
        "first_kickoff_utc": ordered[0].kickoff_utc if ordered else None,
        "last_kickoff_utc": ordered[-1].kickoff_utc if ordered else None,
        "market_data_used": False,
    }


def evaluate_acceptance(
    report: Mapping[str, Any],
    *,
    min_samples: Mapping[str, int] = DEFAULT_MIN_SAMPLES,
    max_threshold_ece: float = DEFAULT_MAX_THRESHOLD_ECE,
    max_abs_mean_bias_ratio: float = DEFAULT_MAX_ABS_MEAN_BIAS_RATIO,
    min_baseline_nll_improvement: float = DEFAULT_MIN_BASELINE_NLL_IMPROVEMENT,
    min_baseline_brier_improvement: float = DEFAULT_MIN_BASELINE_BRIER_IMPROVEMENT,
    max_poisson_relative_regression: float = DEFAULT_MAX_POISSON_RELATIVE_REGRESSION,
    require_baseline: bool = True,
) -> Dict[str, Any]:
    """Apply pre-registered production gates to a backtest report."""
    heads = report.get("heads")
    if not isinstance(heads, Mapping):
        raise ModelIntegrityError("backtest report missing heads")
    results: Dict[str, Any] = {}
    overall_pass = True
    for head in sorted(VALID_HEADS):
        metrics = heads.get(head)
        failures: list[str] = []
        if not isinstance(metrics, Mapping):
            failures.append("HEAD_MISSING")
        else:
            if int(metrics.get("count", 0)) < int(min_samples.get(head, 0)):
                failures.append("INSUFFICIENT_SAMPLE")
            if abs(float(metrics.get("mean_bias_ratio", 999.0))) > max_abs_mean_bias_ratio:
                failures.append("MEAN_BIAS")
            if float(metrics.get("threshold_ece", 999.0)) > max_threshold_ece:
                failures.append("THRESHOLD_CALIBRATION")

            nb_nll = float(metrics.get("nll", 999.0))
            pois_nll = float(metrics.get("poisson_same_mean_nll", 0.0))
            nb_brier = float(metrics.get("milestone_brier", 999.0))
            pois_brier = float(metrics.get("poisson_same_mean_milestone_brier", 0.0))
            if nb_nll > pois_nll * (1.0 + max_poisson_relative_regression):
                failures.append("NB_NLL_WORSE_THAN_POISSON")
            if nb_brier > pois_brier * (1.0 + max_poisson_relative_regression):
                failures.append("NB_BRIER_WORSE_THAN_POISSON")

            if require_baseline:
                if float(metrics.get("baseline_coverage_rate", 0.0)) < 0.999999:
                    failures.append("BASELINE_INCOMPLETE")
                elif "nll_improvement_vs_baseline" not in metrics or "brier_improvement_vs_baseline" not in metrics:
                    failures.append("BASELINE_METRICS_MISSING")
                else:
                    if float(metrics["nll_improvement_vs_baseline"]) < min_baseline_nll_improvement:
                        failures.append("NO_NLL_EDGE_VS_BASELINE")
                    if float(metrics["brier_improvement_vs_baseline"]) < min_baseline_brier_improvement:
                        failures.append("NO_BRIER_EDGE_VS_BASELINE")
        passed = not failures
        overall_pass = overall_pass and passed
        results[head] = {"status": "PASS" if passed else "FAIL", "failures": failures}
    return {
        "schema_version": "aleague_player_volume_backtest_acceptance_v1",
        "status": "PASS" if overall_pass else "FAIL",
        "heads": results,
        "gate_config": {
            "min_samples": dict(min_samples),
            "max_threshold_ece": max_threshold_ece,
            "max_abs_mean_bias_ratio": max_abs_mean_bias_ratio,
            "min_baseline_nll_improvement": min_baseline_nll_improvement,
            "min_baseline_brier_improvement": min_baseline_brier_improvement,
            "max_poisson_relative_regression": max_poisson_relative_regression,
            "require_baseline": require_baseline,
        },
    }


def select_dispersion_holdout(
    rows: Iterable[CountForecastObservation],
    *,
    head: str,
    validation_start_utc: str,
    candidates: Sequence[float],
) -> Dict[str, Any]:
    """Select one dispersion using training data only, then score the holdout.

    Means are treated as already-frozen historical model outputs. The validation
    period can never influence candidate selection.
    """
    if head not in VALID_HEADS:
        raise ModelIntegrityError(f"unsupported dispersion head {head}")
    cutoff = _utc(validation_start_utc, "validation_start_utc")
    candidate_values = sorted({float(value) for value in candidates})
    if not candidate_values or any(value <= 0 for value in candidate_values):
        raise ModelIntegrityError("dispersion candidates must be positive")
    ordered = [row for row in _ordered_unique(rows) if row.head == head]
    train = [row for row in ordered if _utc(row.kickoff_utc, "kickoff_utc") < cutoff]
    validation = [row for row in ordered if _utc(row.kickoff_utc, "kickoff_utc") >= cutoff]
    if not train or not validation:
        raise ModelIntegrityError("dispersion holdout requires non-empty train and validation periods")

    train_scores: Dict[str, float] = {}
    for candidate in candidate_values:
        total = sum(
            _safe_nll(negative_binomial_log_pmf(row.actual_count, row.mean, candidate))
            for row in train
        )
        train_scores[str(candidate)] = total / len(train)
    selected = min(candidate_values, key=lambda value: (train_scores[str(value)], value))
    validation_rows = [replace(row, dispersion=selected) for row in validation]
    validation_report = score_head(validation_rows)
    return {
        "schema_version": "aleague_player_volume_dispersion_holdout_v1",
        "head": head,
        "validation_start_utc": validation_start_utc,
        "train_count": len(train),
        "validation_count": len(validation),
        "candidates": candidate_values,
        "train_nll_by_candidate": train_scores,
        "selected_dispersion": selected,
        "validation": validation_report,
        "selection_used_validation": False,
    }
