#!/usr/bin/env python3
"""Pure-Python inference for serialized NBL QBASE head artifacts.

Training exports transparent scaler/imputer/linear-model parameters so production
runtime does not depend on sklearn or pickle. This module reproduces the selected
model exactly and supports deterministic projected-minutes recomputation before
P_model freeze.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _finite_or_none(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def validate_serialized_qbase(artifact: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(artifact, dict) or artifact.get("market_data") is not False:
        raise ValueError("QBASE artifact must declare market_data=false")
    selected = artifact.get("selected_model")
    if not isinstance(selected, dict):
        raise ValueError("QBASE selected_model required")
    family = str(selected.get("family") or "")
    if family not in {"poisson", "ridge_log1p"}:
        raise ValueError(f"unsupported serialized family {family}")
    features = selected.get("features")
    medians = selected.get("imputer_medians")
    means = selected.get("scaler_mean")
    scales = selected.get("scaler_scale")
    coefs = selected.get("coefficients")
    arrays = (features, medians, means, scales, coefs)
    if not all(isinstance(x, list) for x in arrays):
        raise ValueError("serialized model arrays required")
    n = len(features)
    if n == 0 or any(len(x) != n for x in arrays[1:]):
        raise ValueError("serialized model array lengths must match")
    if len(set(map(str, features))) != n:
        raise ValueError("serialized feature names must be unique")
    try:
        float(selected["intercept"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("serialized model intercept required") from exc
    for idx, scale in enumerate(scales):
        value = _finite_or_none(scale)
        if value is None or value == 0:
            raise ValueError(f"invalid scaler_scale[{idx}]")
    return artifact


def score_qbase(artifact: dict[str, Any], feature_values: dict[str, Any]) -> dict[str, Any]:
    """Score one exact feature vector and return a reproducibility receipt."""
    validate_serialized_qbase(artifact)
    if not isinstance(feature_values, dict):
        raise ValueError("feature_values must be an object")
    selected = artifact["selected_model"]
    names = [str(x) for x in selected["features"]]
    medians = [float(x) for x in selected["imputer_medians"]]
    centers = [float(x) for x in selected["scaler_mean"]]
    scales = [float(x) for x in selected["scaler_scale"]]
    coefs = [float(x) for x in selected["coefficients"]]
    resolved: dict[str, float] = {}
    imputed: list[str] = []
    eta = float(selected["intercept"])
    for idx, name in enumerate(names):
        value = _finite_or_none(feature_values.get(name))
        if value is None:
            value = medians[idx]
            imputed.append(name)
        resolved[name] = value
        z = (value - centers[idx]) / scales[idx]
        eta += coefs[idx] * z
    family = selected["family"]
    if family == "poisson":
        # Keep the same runtime protection used by training prediction.
        eta = min(eta, math.log(40.0))
        raw_mean = math.exp(eta)
    else:
        eta = min(eta, math.log1p(40.0))
        raw_mean = math.expm1(eta)
    mean = min(40.0, max(0.02, raw_mean))
    receipt_input = {
        "stat_type": artifact.get("stat_type"),
        "model_version": artifact.get("model_version"),
        "feature_schema": artifact.get("feature_schema"),
        "selected_model_sha256": sha256_json(selected),
        "resolved_features": resolved,
    }
    return {
        "mean": float(mean),
        "linear_predictor": float(eta),
        "imputed_features": imputed,
        "resolved_features": resolved,
        "quant_input_receipt_sha256": sha256_json(receipt_input),
    }


def projected_minutes_score(
    artifact: dict[str, Any],
    base_features: dict[str, Any],
    projected_minutes: float,
    *,
    starter_probability: float | None = None,
) -> dict[str, Any]:
    """Recompute QBASE under a researched minutes/starter scenario.

    Only the model's explicit minutes/start features are changed. No arbitrary
    assists/rebounds multiplier is introduced. Stat-specific role changes that
    cannot be represented by these model inputs require a separately documented
    empirical-role or prior-competition scenario in the freeze ledger.
    """
    minutes = float(projected_minutes)
    if not math.isfinite(minutes) or minutes < 0 or minutes > 50:
        raise ValueError("projected_minutes must be finite in [0, 50]")
    values = dict(base_features)
    for name in ("player_minutes_mean_3", "player_minutes_mean_5", "player_minutes_mean_10"):
        if name in artifact.get("selected_model", {}).get("features", []):
            values[name] = minutes
    if starter_probability is not None:
        starter = float(starter_probability)
        if not math.isfinite(starter) or not 0 <= starter <= 1:
            raise ValueError("starter_probability must be in [0, 1]")
        for name in ("player_start_rate_5", "player_start_rate_10"):
            if name in artifact.get("selected_model", {}).get("features", []):
                values[name] = starter
    result = score_qbase(artifact, values)
    return {
        **result,
        "projected_minutes": minutes,
        "starter_probability": starter_probability,
        "method": "QBASE_MINUTES_RECOMPUTE",
    }


def minutes_band_scenarios(
    artifact: dict[str, Any],
    base_features: dict[str, Any],
    *,
    low: float,
    mean: float,
    high: float,
    weights: tuple[float, float, float] = (0.2, 0.6, 0.2),
    starter_probability: float | None = None,
) -> list[dict[str, Any]]:
    """Create low/base/high deterministic QBASE minute scenarios.

    The caller owns the research basis for the minute band and scenario weights;
    this function only executes the quantitative model and emits receipts.
    """
    lo, mid, hi = float(low), float(mean), float(high)
    if not 0 <= lo <= mid <= hi <= 50:
        raise ValueError("minutes band must satisfy 0<=low<=mean<=high<=50")
    if len(weights) != 3:
        raise ValueError("weights must contain low/base/high")
    ww = tuple(float(x) for x in weights)
    if any(not math.isfinite(x) or x <= 0 for x in ww) or abs(sum(ww) - 1.0) > 1e-9:
        raise ValueError("scenario weights must be positive and sum to 1")
    rows = []
    for sid, minutes, weight in zip(("minutes_low", "minutes_base", "minutes_high"), (lo, mid, hi), ww):
        score = projected_minutes_score(
            artifact, base_features, minutes, starter_probability=starter_probability,
        )
        rows.append({
            "id": sid,
            "weight": weight,
            "mean": score["mean"],
            "method": "QBASE_MINUTES_RECOMPUTE",
            "quant_input_receipt_sha256": score["quant_input_receipt_sha256"],
        })
    return rows
