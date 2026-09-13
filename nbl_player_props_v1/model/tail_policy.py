"""Evidence rules for classifying NBL QBASE probability-ladder thresholds."""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any

import numpy as np

from distribution import at_least

DIRECT_CRITERIA = {
    "minimum_observed_events": 250,
    "minimum_predicted_events": 250.0,
    "minimum_brier_skill_vs_constant_prevalence": 0.05,
    "calibration_ratio_minimum": 0.75,
    "calibration_ratio_maximum": 1.35,
}
TAIL_CRITERIA = {
    "minimum_observed_events": 250,
    "minimum_predicted_events": 250.0,
    "minimum_brier_skill_vs_constant_prevalence": 0.0,
    "calibration_ratio_minimum": 0.5,
    "calibration_ratio_maximum": 2.0,
    "maximum_absolute_calibration_error": 0.01,
}


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def wilson_interval(successes: int, trials: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if trials <= 0:
        return (math.nan, math.nan)
    p = successes / trials
    denominator = 1.0 + z * z / trials
    centre = (p + z * z / (2.0 * trials)) / denominator
    radius = z * math.sqrt((p * (1.0 - p) + z * z / (4.0 * trials)) / trials) / denominator
    return (max(0.0, centre - radius), min(1.0, centre + radius))


def expected_calibration_error(observed: np.ndarray, predicted: np.ndarray, bins: int = 10) -> float:
    order = np.argsort(predicted, kind="stable")
    chunks = np.array_split(order, bins)
    return float(sum(
        len(chunk) / len(observed) * abs(float(np.mean(predicted[chunk])) - float(np.mean(observed[chunk])))
        for chunk in chunks if len(chunk)
    ))


def threshold_metrics(actual: np.ndarray, means: np.ndarray, alpha: float, threshold: int) -> dict[str, Any]:
    observed = (actual >= threshold).astype(float)
    predicted = np.asarray([at_least(threshold, float(mean), alpha) for mean in means], dtype=float)
    n = len(observed)
    observed_count = int(np.sum(observed))
    observed_rate = float(np.mean(observed))
    predicted_rate = float(np.mean(predicted))
    brier = float(np.mean((predicted - observed) ** 2))
    null_brier = observed_rate * (1.0 - observed_rate)
    low, high = wilson_interval(observed_count, n)
    return {
        "threshold": int(threshold),
        "oos_n": int(n),
        "observed_count": observed_count,
        "predicted_count": float(np.sum(predicted)),
        "observed_rate": observed_rate,
        "predicted_rate": predicted_rate,
        "calibration_error_predicted_minus_observed": predicted_rate - observed_rate,
        "calibration_ratio_predicted_to_observed": predicted_rate / observed_rate if observed_rate > 0 else None,
        "observed_rate_wilson_95": [low, high],
        "predicted_rate_inside_observed_wilson_95": bool(low <= predicted_rate <= high),
        "brier": brier,
        "null_brier": null_brier,
        "brier_skill_vs_constant_prevalence": 1.0 - brier / null_brier if null_brier > 0 else None,
        "expected_calibration_error_10_equal_count_bins": expected_calibration_error(observed, predicted),
    }


def passes_criteria(metric: dict[str, Any], criteria: dict[str, float | int]) -> bool:
    ratio = metric.get("calibration_ratio_predicted_to_observed")
    skill = metric.get("brier_skill_vs_constant_prevalence")
    if ratio is None or skill is None:
        return False
    if int(metric["observed_count"]) < int(criteria["minimum_observed_events"]):
        return False
    if float(metric["predicted_count"]) < float(criteria["minimum_predicted_events"]):
        return False
    if float(skill) < float(criteria["minimum_brier_skill_vs_constant_prevalence"]):
        return False
    if not float(criteria["calibration_ratio_minimum"]) <= float(ratio) <= float(criteria["calibration_ratio_maximum"]):
        return False
    maximum_error = criteria.get("maximum_absolute_calibration_error")
    return maximum_error is None or abs(float(metric["calibration_error_predicted_minus_observed"])) <= float(maximum_error)


def classify_thresholds(metrics: list[dict[str, Any]], selection_thresholds: list[int]) -> dict[str, Any]:
    by_threshold = {int(row["threshold"]): row for row in metrics}
    selected = sorted(set(int(value) for value in selection_thresholds))
    if not selected or selected != list(range(selected[0], selected[-1] + 1)):
        raise ValueError("selection thresholds must be a non-empty consecutive range")

    direct: list[int] = []
    for threshold in selected:
        if not passes_criteria(by_threshold[threshold], DIRECT_CRITERIA):
            break
        direct.append(threshold)
    if not direct:
        raise ValueError("no directly validated threshold survived the reliability gate")

    lower_supported = [
        threshold for threshold in range(1, selected[0])
        if passes_criteria(by_threshold[threshold], DIRECT_CRITERIA)
    ]
    upper_supported: list[int] = []
    for threshold in range(direct[-1] + 1, max(by_threshold) + 1):
        if not passes_criteria(by_threshold[threshold], TAIL_CRITERIA):
            break
        upper_supported.append(threshold)
    tail_supported = lower_supported + upper_supported
    all_thresholds = sorted(by_threshold)
    extreme = [threshold for threshold in all_thresholds if threshold not in direct and threshold not in tail_supported]
    best_single_eligible = sorted(direct + [
        threshold for threshold in tail_supported if passes_criteria(by_threshold[threshold], DIRECT_CRITERIA)
    ])
    return {
        "schema_version": "nbl_threshold_validation_v1",
        "direct_validated_thresholds": direct,
        "tail_supported_thresholds": tail_supported,
        "extreme_tail_thresholds": extreme,
        "best_single_eligible_thresholds": best_single_eligible,
        "direct_reliability_criteria": DIRECT_CRITERIA,
        "tail_support_criteria": TAIL_CRITERIA,
        "classification_is_consecutive_above_direct_ceiling": True,
    }


def build_tail_audit(actual: np.ndarray, means: np.ndarray, alpha: float,
                     selection_thresholds: list[int], max_count: int) -> dict[str, Any]:
    metrics = [threshold_metrics(actual, means, alpha, threshold) for threshold in range(1, max_count + 1)]
    return {
        "policy": classify_thresholds(metrics, selection_thresholds),
        "threshold_metrics": metrics,
    }
