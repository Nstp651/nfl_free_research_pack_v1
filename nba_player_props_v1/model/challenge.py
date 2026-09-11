"""Independent temporal count-model challenge. Emits evidence, never auto-promotes.

2024/2025 are expanding-window validation folds; 2026 is untouched holdout.
Thresholds are a fixed count grid, never sourced from sportsbook data.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform

# The fitted GLM is an offline promotion input, so its floating-point execution must be
# portable across GitHub runner CPU models. Force one OpenBLAS dynamic-arch kernel on
# x86_64 and one numerical thread BEFORE NumPy/SciPy are imported. Runtime scoring is
# JS and does not depend on this training-only environment contract.
for _thread_env in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_thread_env] = "1"
if platform.machine().lower() in {"x86_64", "amd64"}:
    os.environ["OPENBLAS_CORETYPE"] = "Haswell"

import numpy as np
import pandas as pd
import scipy
from scipy.stats import nbinom, poisson
from sklearn import __version__ as sklearn_version
from sklearn.impute import SimpleImputer
from sklearn.linear_model import PoissonRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from nba_player_props_v1.model.features import build_pregame_features, head_feature_columns
from nba_player_props_v1.source_receipt import canonical_json, sha256_bytes, sha256_file

# Numerical values far below this precision have no betting meaning. Nine decimals is
# retained as an extra serialization guard; the primary portability control is the
# fixed single-thread OpenBLAS execution contract above.
NUMERIC_DECIMALS = 9


def _q(value: float) -> float:
    return round(float(value), NUMERIC_DECIMALS)


def _q_list(values) -> list[float]:
    return [_q(v) for v in values]


def _quantize_report(value):
    if isinstance(value, dict):
        return {k: _quantize_report(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_quantize_report(v) for v in value]
    if isinstance(value, (np.floating, float)):
        if not np.isfinite(float(value)):
            raise ValueError("non-finite challenge value")
        return _q(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.bool_):
        return bool(value)
    return value


def distribution(mean, alpha):
    mean = np.asarray(mean, dtype=float)
    if not np.isfinite(mean).all() or (mean <= 0).any() or not np.isfinite(alpha) or alpha < 0:
        raise ValueError("invalid count distribution parameters")
    return poisson(mean) if alpha == 0 else nbinom(1 / alpha, 1 / (1 + alpha * mean))


def probability_metrics(y, mean, alpha, thresholds):
    y, mean = np.asarray(y), np.asarray(mean)
    if len(y) == 0:
        return {"n": 0, "status": "NO_SAMPLE"}
    d = distribution(mean, alpha)
    probs = np.stack([d.sf(k) for k in thresholds], axis=1)
    truth = y[:, None] > np.asarray(thresholds)[None, :]
    push = np.stack([d.pmf(k) for k in thresholds], axis=1)
    push_truth = y[:, None] == np.asarray(thresholds)[None, :]
    bins = []
    for lower in np.arange(0, 1, .1):
        mask = (probs >= lower) & (probs < lower + .1 if lower < .9 else probs <= 1)
        if mask.any():
            bins.append({"lower": round(float(lower), 1), "n": int(mask.sum()),
                "predicted": float(probs[mask].mean()), "observed": float(truth[mask].mean())})
    partition_error = max(float(np.max(np.abs(d.cdf(k - 1) + d.pmf(k) + d.sf(k) - 1))) for k in thresholds)
    return {"n": len(y), "count_nll": float(-d.logpmf(y).mean()),
        "brier_over": float(np.mean((probs - truth) ** 2)),
        "integer_push_brier": float(np.mean((push - push_truth) ** 2)),
        "integer_push_bias": float(np.mean(push - push_truth)),
        "half_point_brier": float(np.mean((probs - truth) ** 2)),
        "bias": float(np.mean(mean - y)), "mae": float(np.mean(abs(mean - y))),
        "rmse": float(np.sqrt(np.mean((mean - y) ** 2))),
        "coverage_90": float(np.mean((y >= d.ppf(.05)) & (y <= d.ppf(.95)))),
        "partition_max_error": partition_error, "calibration_bins": bins}


def cohorts(frame):
    n = frame.season_games_before
    return {"games_0_2": n <= 2, "games_3_7": (n >= 3) & (n <= 7), "games_8_plus": n >= 8,
        "team_changers": frame.team_changed_since_last_game == 1,
        # Outcome starter status is used for retrospective slicing ONLY, never features.
        "starter_changes": frame.starter_prev.notna() & (frame.starter_prev != frame.starter.astype(int)),
        "low_history": frame.career_games_before < 10,
        "role_change_proxy": frame.start_rate_l5.notna() & frame.start_rate_l10.notna() &
            ((frame.start_rate_l5 - frame.start_rate_l10).abs() >= .3)}


def _score_glm_artifact(model, rows):
    x = rows[model["features"]].to_numpy(float)
    x = np.where(np.isnan(x), np.asarray(model["medians"], dtype=float), x)
    z = (x - np.asarray(model["centers"], dtype=float)) / np.asarray(model["scales"], dtype=float)
    coefficients = np.asarray(model["coefficients"], dtype=float)
    # Deliberately avoid BLAS matrix multiplication here. The elementwise sum uses the
    # exact exported, quantized parameters and is the runtime portability authority.
    eta = np.sum(z * coefficients[None, :], axis=1) + float(model["intercept"])
    return np.maximum(np.exp(eta), .01)


def fit_candidate(train, head, kind):
    cols = list(head_feature_columns(head))
    y = train[head].to_numpy(float)
    if kind.startswith("shrunk"):
        prior = _q(y.mean())
        model = {"family": "shrunk_count", "prior": prior, "prior_weight": 5}
        def predict(rows):
            history = np.minimum(rows.career_games_before.to_numpy(float), 10)
            recent = rows[f"{head}_l10"].fillna(prior).to_numpy(float)
            return np.maximum((recent * history + prior * 5) / (history + 5), .01)
    else:
        estimator = make_pipeline(SimpleImputer(strategy="median", keep_empty_features=True),
            StandardScaler(), PoissonRegressor(alpha=1.0, max_iter=500, tol=1e-9))
        estimator.fit(train[cols], y)
        imputer, scaler, reg = estimator.steps[0][1], estimator.steps[1][1], estimator.steps[2][1]
        model = {"family": "regularized_poisson_glm", "features": cols,
            "medians": _q_list(imputer.statistics_), "centers": _q_list(scaler.mean_),
            "scales": _q_list(scaler.scale_), "coefficients": _q_list(reg.coef_),
            "intercept": _q(reg.intercept_), "numeric_precision_decimals": NUMERIC_DECIMALS}
        def predict(rows):
            return _score_glm_artifact(model, rows)
    mu = predict(train)
    # Training residual moment estimate only; never refit dispersion on a held-out fold.
    alpha = max(float(np.sum((y - mu) ** 2 - mu) / np.sum(mu ** 2)), 1e-8) if kind.endswith("nb") else 0.0
    model["dispersion_alpha"] = _q(alpha)
    return predict, model


def score_artifact(model, rows, head):
    """Portable deterministic score; used to verify exported numeric parameters."""
    if model["family"] == "shrunk_count":
        history = np.minimum(rows.career_games_before.to_numpy(float), 10)
        recent = rows[f"{head}_l10"].fillna(model["prior"]).to_numpy(float)
        return np.maximum((recent * history + model["prior"] * 5) / (history + 5), .01)
    return _score_glm_artifact(model, rows)


def run_challenge(frame, head, *, validation_seasons=(2024, 2025), holdout=2026):
    kinds = ("shrunk_poisson", "shrunk_nb", "glm_poisson", "glm_nb")
    thresholds = list(range(0, 16 if head == "assists" else 26))
    reports = {}
    for kind in kinds:
        folds = []
        for season in validation_seasons:
            test = frame[frame.season == season]
            train = frame[(frame.season < season) & (frame.game_start_utc < test.game_start_utc.min())]
            if len(train) < 1000 or len(test) < 1000:
                raise ValueError("insufficient temporal fold sample")
            predict, model = fit_candidate(train, head, kind)
            mu = predict(test)
            if not np.allclose(mu, score_artifact(model, test, head), rtol=1e-12, atol=1e-12):
                raise ValueError("runtime score mismatch")
            folds.append({"season": season, "train_rows": len(train),
                "train_max_utc": train.game_start_utc.max().isoformat(),
                "test_min_utc": test.game_start_utc.min().isoformat(),
                "overall": probability_metrics(test[head], mu, model["dispersion_alpha"], thresholds),
                "cohorts": {name: probability_metrics(test.loc[mask, head], mu[mask], model["dispersion_alpha"], thresholds)
                            for name, mask in cohorts(test).items()}})
        folds = _quantize_report(folds)
        reports[kind] = {"folds": folds, "validation_brier": _q(np.mean([f["overall"]["brier_over"] for f in folds]))}
    baseline = reports["shrunk_poisson"]
    eligible = [k for k in kinds if all(
        reports[k]["folds"][i]["cohorts"][c]["brier_over"] <= baseline["folds"][i]["cohorts"][c]["brier_over"]
        for i in range(len(validation_seasons)) for c in ("games_0_2", "games_3_7"))]
    selected = min(eligible, key=lambda k: (reports[k]["validation_brier"], kinds.index(k)))
    test = frame[frame.season == holdout]
    train = frame[(frame.season < holdout) & (frame.game_start_utc < test.game_start_utc.min())]
    if len(test) < 1000:
        raise ValueError("insufficient untouched holdout")
    predict, model = fit_candidate(train, head, selected)
    mu = predict(test)
    baseline_predict, _ = fit_candidate(train, head, "shrunk_poisson")
    holdout_report = {"season": holdout,
        "overall": probability_metrics(test[head], mu, model["dispersion_alpha"], thresholds),
        "baseline": probability_metrics(test[head], baseline_predict(test), 0, thresholds),
        "cohorts": {name: probability_metrics(test.loc[mask, head], mu[mask], model["dispersion_alpha"], thresholds)
                    for name, mask in cohorts(test).items()}}
    model["head"] = head
    model["trained_before_season"] = holdout
    report = {"head": head, "status": "EXPERIMENTAL_NOT_PROMOTED", "market_data": False,
        "selection_rule": "lowest_validation_brier_without_early_cohort_regression_vs_shrunk_poisson",
        "numeric_precision_decimals": NUMERIC_DECIMALS,
        "threshold_grid": thresholds, "half_point_interpretation": "P(X > k+0.5) = P(X > k)",
        "candidates": reports, "validation_eligible": eligible, "selected_candidate": selected,
        "holdout": holdout_report, "runtime_score_reproduced": bool(np.allclose(mu, score_artifact(model, test, head), rtol=1e-12, atol=1e-12)),
        "candidate_artifact": model,
        "remaining_gates": ["source_acceptance", "specialist_feature_challenge", "holdout_cohort_promotion_review",
            "live_current_role_translation", "prior_competition_translation", "runtime_distribution_acceptance"]}
    return _quantize_report(report)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--history", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    source = pd.read_csv(args.history, dtype={c: str for c in (
        "game_id_espn", "player_id_espn", "team_id_espn", "opponent_team_id_espn")})
    frame = build_pregame_features(source)
    frame = frame.sort_values(["game_start_utc", "game_id_espn", "player_id_espn"])
    frame["career_games_before"] = frame.groupby("player_id_espn").cumcount()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    for head in ("assists", "rebounds"):
        report = run_challenge(frame, head)
        report["normalized_history_sha256"] = sha256_file(args.history)
        report["environment"] = {"python": platform.python_version(), "numpy": np.__version__,
            "pandas": pd.__version__, "scipy": scipy.__version__, "sklearn": sklearn_version,
            "openblas_coretype": os.environ.get("OPENBLAS_CORETYPE"), "numeric_threads": 1}
        report["receipt_sha256"] = sha256_bytes(canonical_json(report))
        (out / f"{head}_temporal_challenge.json").write_bytes(canonical_json(report) + b"\n")
        print(head, report["selected_candidate"], report["holdout"]["overall"], flush=True)


if __name__ == "__main__":
    main()
