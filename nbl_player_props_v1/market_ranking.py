"""Deterministic NBL threshold classification, grading and BEST SINGLE policy."""
from __future__ import annotations

import math
import re
from typing import Any

VALID_STATES = {"DIRECT_VALIDATED", "TAIL_SUPPORTED", "EXTREME_TAIL"}
GRADE_ORDER = ["A+", "A", "B+", "B", "C+", "PASS"]
LEGACY_QBASE_POLICIES = {
    "8e714c693f0a1eddfd3989c6717f120079ec3fa0e1c42e1eaf5c1d670d265eab": {
        "schema_version": "nbl_threshold_validation_v1",
        "direct_validated_thresholds": list(range(2, 10)),
        "tail_supported_thresholds": [1],
        "extreme_tail_thresholds": list(range(10, 21)),
        "best_single_eligible_thresholds": list(range(1, 10)),
        "evidence_sha256": "a77126faacc0304962060b76caae79a358de2723d10210c2be3ff67adcd0d446",
    },
    "61e8e4792e7376f6d0f70b832e1ea7e3bea928c6e4e7acf512851185a1d7086f": {
        "schema_version": "nbl_threshold_validation_v1",
        "direct_validated_thresholds": list(range(3, 13)),
        "tail_supported_thresholds": [1, 2, 13],
        "extreme_tail_thresholds": list(range(14, 31)),
        "best_single_eligible_thresholds": list(range(1, 13)),
        "evidence_sha256": "2c00c2a254a53695565a92348eee25057adb56024e263313ea443e947dae9357",
    },
}


def _integer_list(value: Any, label: str) -> list[int]:
    if not isinstance(value, list) or any(not isinstance(item, int) or item < 1 for item in value):
        raise ValueError(f"{label} must contain positive integers")
    if len(value) != len(set(value)):
        raise ValueError(f"{label} contains duplicates")
    return sorted(value)


def validate_threshold_policy(value: Any, max_count: int) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema_version") != "nbl_threshold_validation_v1":
        raise ValueError("threshold validation policy unavailable")
    direct = _integer_list(value.get("direct_validated_thresholds"), "direct thresholds")
    supported = _integer_list(value.get("tail_supported_thresholds"), "tail-supported thresholds")
    extreme = _integer_list(value.get("extreme_tail_thresholds"), "extreme-tail thresholds")
    eligible = _integer_list(value.get("best_single_eligible_thresholds"), "BEST SINGLE thresholds")
    if not direct:
        raise ValueError("direct threshold range empty")
    if set(direct) & set(supported) or set(direct) & set(extreme) or set(supported) & set(extreme):
        raise ValueError("threshold validation classes overlap")
    if sorted(direct + supported + extreme) != list(range(1, max_count + 1)):
        raise ValueError("threshold validation classes must partition the probability grid")
    if not set(eligible).issubset(set(direct + supported)):
        raise ValueError("BEST SINGLE thresholds must be validated or supported")
    if not re.fullmatch(r"[0-9a-f]{64}", str(value.get("evidence_sha256") or "")):
        raise ValueError("threshold validation evidence receipt invalid")
    return {
        **value,
        "direct_validated_thresholds": direct,
        "tail_supported_thresholds": supported,
        "extreme_tail_thresholds": extreme,
        "best_single_eligible_thresholds": eligible,
    }


def policy_for_head(head: dict[str, Any]) -> dict[str, Any]:
    anchor = head.get("qbase_anchor") or {}
    max_count = int(anchor.get("max_count") or (head.get("probability_grid") or {}).get("max_count") or 0)
    embedded = anchor.get("threshold_validation_policy")
    if embedded is None:
        embedded = LEGACY_QBASE_POLICIES.get(str(anchor.get("qbase_sha256") or ""))
    return validate_threshold_policy(embedded, max_count)


def event_thresholds_for_line(line: float) -> list[int]:
    value = float(line)
    if abs(value * 2.0 - round(value * 2.0)) > 1e-9:
        raise ValueError("market threshold must be integer/half-point")
    if abs(value - round(value)) <= 1e-9:
        threshold = int(round(value))
        return [max(1, threshold), threshold + 1]
    return [math.floor(value) + 1]


def classify_market_threshold(head: dict[str, Any], line: float) -> dict[str, Any]:
    policy = policy_for_head(head)
    event_thresholds = event_thresholds_for_line(line)
    direct = set(policy["direct_validated_thresholds"])
    supported = set(policy["tail_supported_thresholds"])
    eligible = set(policy["best_single_eligible_thresholds"])
    states = ["DIRECT_VALIDATED" if threshold in direct else "TAIL_SUPPORTED" if threshold in supported else "EXTREME_TAIL" for threshold in event_thresholds]
    state = max(states, key={"DIRECT_VALIDATED": 0, "TAIL_SUPPORTED": 1, "EXTREME_TAIL": 2}.get)
    return {
        "threshold_validation": state,
        "validation_event_thresholds": event_thresholds,
        "threshold_best_single_supported": all(threshold in eligible for threshold in event_thresholds),
        "threshold_validation_evidence_sha256": policy["evidence_sha256"],
    }


def _grade_cap(base: str, ceiling: str) -> str:
    return GRADE_ORDER[max(GRADE_ORDER.index(base), GRADE_ORDER.index(ceiling))]


def deterministic_grade(ev: float, confidence: str, fragility: str, threshold: dict[str, Any]) -> str:
    if ev >= 0.25:
        grade = "A+"
    elif ev >= 0.15:
        grade = "A"
    elif ev >= 0.10:
        grade = "B+"
    elif ev >= 0.05:
        grade = "B"
    elif ev >= 0.02:
        grade = "C+"
    else:
        grade = "PASS"
    quality_ceiling = {
        ("A", "LOW"): "A+", ("A", "MEDIUM"): "A", ("A", "HIGH"): "B",
        ("B", "LOW"): "A", ("B", "MEDIUM"): "B+", ("B", "HIGH"): "C+",
        ("C", "LOW"): "B", ("C", "MEDIUM"): "C+", ("C", "HIGH"): "PASS",
    }.get((confidence, fragility), "PASS")
    tail_ceiling = {
        "DIRECT_VALIDATED": "A+",
        "TAIL_SUPPORTED": "A" if threshold["threshold_best_single_supported"] else "B",
        "EXTREME_TAIL": "C+",
    }[threshold["threshold_validation"]]
    return _grade_cap(_grade_cap(grade, quality_ceiling), tail_ceiling)


def rank_guardrails(ev: float, confidence: str, fragility: str, threshold: dict[str, Any]) -> dict[str, Any]:
    grade = deterministic_grade(ev, confidence, fragility, threshold)
    reason = None
    if ev <= 0:
        reason = "NON_POSITIVE_EV"
    elif threshold["threshold_validation"] == "EXTREME_TAIL":
        reason = "EXTREME_TAIL"
    elif not threshold["threshold_best_single_supported"]:
        reason = "THRESHOLD_VALIDATION_NOT_BEST_SINGLE_ELIGIBLE"
    elif confidence == "C":
        reason = "CONFIDENCE_C"
    elif fragility == "HIGH":
        reason = "FRAGILITY_HIGH"
    elif grade in {"C+", "PASS"}:
        reason = "GRADE_BELOW_BEST_SINGLE_MINIMUM"
    return {
        **threshold,
        "grade": grade,
        "best_single_eligible": reason is None,
        "best_single_exclusion_reason": reason,
    }
