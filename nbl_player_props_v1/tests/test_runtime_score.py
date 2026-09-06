from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model"))

from runtime_score import minutes_band_scenarios, projected_minutes_score, score_qbase  # noqa: E402


def artifact():
    return {
        "market_data": False,
        "stat_type": "assists",
        "model_version": "test",
        "feature_schema": "test_schema",
        "selected_model": {
            "family": "poisson",
            "features": ["player_minutes_mean_3", "other"],
            "imputer_medians": [20.0, 2.0],
            "scaler_mean": [20.0, 2.0],
            "scaler_scale": [5.0, 1.0],
            "coefficients": [0.5, 0.1],
            "intercept": math.log(3.0),
        },
    }


def test_serialized_poisson_score_matches_manual_math():
    a = artifact()
    scored = score_qbase(a, {"player_minutes_mean_3": 25.0, "other": 3.0})
    expected = math.exp(math.log(3.0) + 0.5 * 1.0 + 0.1 * 1.0)
    assert scored["mean"] == pytest.approx(expected)
    assert scored["imputed_features"] == []
    assert len(scored["quant_input_receipt_sha256"]) == 64


def test_missing_feature_uses_training_median():
    scored = score_qbase(artifact(), {"player_minutes_mean_3": 20.0})
    assert scored["mean"] == pytest.approx(3.0)
    assert scored["imputed_features"] == ["other"]


def test_projected_minutes_overrides_only_explicit_minutes_features():
    a = artifact()
    base = {"player_minutes_mean_3": 10.0, "other": 2.0, "unused": 99.0}
    scored = projected_minutes_score(a, base, 30.0)
    expected = math.exp(math.log(3.0) + 0.5 * ((30.0 - 20.0) / 5.0))
    assert scored["mean"] == pytest.approx(expected)
    assert scored["resolved_features"]["other"] == 2.0
    assert "unused" not in scored["resolved_features"]


def test_minutes_band_scenarios_are_deterministic_and_weighted():
    rows = minutes_band_scenarios(
        artifact(), {"player_minutes_mean_3": 20.0, "other": 2.0},
        low=20.0, mean=25.0, high=30.0,
    )
    assert [r["id"] for r in rows] == ["minutes_low", "minutes_base", "minutes_high"]
    assert sum(r["weight"] for r in rows) == pytest.approx(1.0)
    assert rows[0]["mean"] < rows[1]["mean"] < rows[2]["mean"]
    assert all(len(r["quant_input_receipt_sha256"]) == 64 for r in rows)


def test_invalid_serialized_model_shape_fails_closed():
    a = artifact()
    a["selected_model"]["coefficients"] = [0.5]
    with pytest.raises(ValueError, match="array lengths"):
        score_qbase(a, {})


def test_market_data_artifact_is_rejected():
    a = artifact(); a["market_data"] = True
    with pytest.raises(ValueError, match="market_data=false"):
        score_qbase(a, {})
