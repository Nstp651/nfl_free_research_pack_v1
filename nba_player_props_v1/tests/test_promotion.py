from __future__ import annotations

import pytest

from nba_player_props_v1.model.promotion import promote_head


def _metrics(*, brier=0.05, n=1000, bias=0.0, coverage=0.95, nll=1.5):
    return {"brier_over": brier, "n": n, "bias": bias, "coverage_90": coverage,
            "count_nll": nll, "partition_max_error": 1e-14}


def _challenge():
    candidate_folds, baseline_folds = [], []
    for season in (2024, 2025):
        candidate_folds.append({"season": season, "cohorts": {
            "games_0_2": _metrics(brier=0.05), "games_3_7": _metrics(brier=0.051)}})
        baseline_folds.append({"season": season, "cohorts": {
            "games_0_2": _metrics(brier=0.055), "games_3_7": _metrics(brier=0.056)}})
    cohorts = {
        "games_0_2": _metrics(brier=0.052, n=1700, bias=0.1),
        "games_3_7": _metrics(brier=0.053, n=2600, bias=-0.1),
        "team_changers": _metrics(brier=0.055, n=250),
        "starter_changes": _metrics(brier=0.072, n=500),
        "low_history": _metrics(brier=0.048, n=900),
        "role_change_proxy": _metrics(brier=0.058, n=1400),
    }
    return {
        "head": "assists", "market_data": False, "runtime_score_reproduced": True,
        "selected_candidate": "glm_nb", "validation_eligible": ["glm_nb"],
        "candidates": {
            "glm_nb": {"folds": candidate_folds},
            "shrunk_poisson": {"folds": baseline_folds},
        },
        "holdout": {
            "overall": _metrics(brier=0.059, n=28000, bias=-0.05, coverage=0.955, nll=1.8),
            "baseline": _metrics(brier=0.061, n=28000, bias=0.0, coverage=0.94, nll=1.86),
            "cohorts": cohorts,
        },
        "candidate_artifact": {
            "family": "regularized_poisson_glm", "head": "assists", "features": ["minutes_l5"],
            "medians": [24.0], "centers": [24.0], "scales": [8.0], "coefficients": [0.1],
            "intercept": 0.5, "dispersion_alpha": 0.12, "trained_before_season": 2026,
        },
        "receipt_sha256": "a" * 64,
    }


def _source(status="PASS"):
    return {"status": status, "market_data": False, "receipt_sha256": "b" * 64}


def _specialist():
    return {"base_model_permitted": True, "promoted_specialist_features": [],
            "decision": "BASE_V1_WITHOUT_SPECIALIST_METRICS"}


def test_promotes_locked_head_without_reselecting_holdout():
    artifact = promote_head(_challenge(), _source(), _specialist(), model_version="NBA_ASSISTS_QBASE_V1.0.0")
    assert artifact["status"] == "PROMOTED_CORE_V1"
    assert artifact["head"] == "assists"
    assert artifact["holdout_use_rule"] == "PASS_FAIL_REVIEW_ONLY_NO_MODEL_FAMILY_RESELECTION"
    assert "starter_changes" not in artifact["restricted_cohorts"]
    assert len(artifact["promotion_receipt_sha256"]) == 64


def test_rejects_unaccepted_source():
    with pytest.raises(ValueError, match="source acceptance"):
        promote_head(_challenge(), _source("FAIL"), _specialist(), model_version="x")


def test_rejects_holdout_regression_without_reselection():
    challenge = _challenge()
    challenge["holdout"]["overall"]["brier_over"] = 0.07
    with pytest.raises(ValueError, match="holdout Brier regression"):
        promote_head(challenge, _source(), _specialist(), model_version="x")


def test_role_cohort_can_be_restricted_without_rejecting_head():
    challenge = _challenge()
    challenge["holdout"]["cohorts"]["starter_changes"]["brier_over"] = 0.09
    artifact = promote_head(challenge, _source(), _specialist(), model_version="x")
    assert "starter_changes" in artifact["restricted_cohorts"]
