#!/usr/bin/env python3
"""Train separate market-blind NBL ASSISTS and REBOUNDS quantitative heads.

Design goals:
- one shared leak-safe pregame feature frame;
- separate stat models and probability calibration;
- season-by-season temporal walk-forward only;
- transparent JSON artifacts reproducible in a Worker (no pickle dependency);
- model selection rewards out-of-sample threshold calibration, then count error.

The baseline is conditional on the player taking the court. Availability and
projected role/minutes are rebuilt by live research before P_model freeze.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import PoissonRegressor, Ridge
from sklearn.metrics import mean_absolute_error, mean_poisson_deviance, mean_squared_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
from distribution import brier_at_least, estimate_nb_alpha  # noqa: E402
from features import build_feature_frame, feature_columns  # noqa: E402

MODEL_VERSION = "0.1.0"
FEATURE_SCHEMA = "nbl_player_pregame_v1"
HEAD_CONFIG = {
    "assists": {"thresholds": list(range(2, 11)), "max_count": 20},
    "rebounds": {"thresholds": list(range(3, 16)), "max_count": 30},
}


def season_start(value: Any) -> int | None:
    m = re.search(r"(?:19|20)\d{2}", str(value or ""))
    return int(m.group(0)) if m else None


def model_pipeline(family: str, alpha: float) -> Pipeline:
    if family == "poisson":
        estimator = PoissonRegressor(alpha=alpha, max_iter=2000, tol=1e-8)
    elif family == "ridge_log1p":
        estimator = Ridge(alpha=alpha)
    else:
        raise ValueError(f"unknown family {family}")
    return Pipeline([
        ("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
        ("scale", StandardScaler()),
        ("model", estimator),
    ])


def fit_model(family: str, alpha: float, x: pd.DataFrame, y: pd.Series) -> Pipeline:
    model = model_pipeline(family, alpha)
    target = np.log1p(y.to_numpy(float)) if family == "ridge_log1p" else y.to_numpy(float)
    model.fit(x, target)
    return model


def predict_model(model: Pipeline, family: str, x: pd.DataFrame) -> np.ndarray:
    raw = np.asarray(model.predict(x), dtype=float)
    pred = np.expm1(raw) if family == "ridge_log1p" else raw
    return np.clip(pred, 0.02, 40.0)


def eligible_frame(raw: pd.DataFrame, head: str) -> pd.DataFrame:
    df = build_feature_frame(raw)
    target = head
    df["season_start"] = df["season"].map(season_start)
    df = df[
        df["season_start"].notna()
        & df[target].notna()
        & (df[target] >= 0)
        & df["minutes"].notna()
        & (df["minutes"] > 0)
        & (df["player_games_prior"] >= 3)
        & df["player_minutes_mean_3"].notna()
    ].copy()
    if df.empty:
        raise RuntimeError(f"No eligible {head} rows")
    return df


def count_metrics(actual: np.ndarray, pred: np.ndarray) -> dict[str, float | int]:
    actual = np.asarray(actual, dtype=float)
    pred = np.maximum(np.asarray(pred, dtype=float), 0.02)
    return {
        "n": int(len(actual)),
        "mae": float(mean_absolute_error(actual, pred)),
        "rmse": float(math.sqrt(mean_squared_error(actual, pred))),
        "bias_actual_minus_pred": float(np.mean(actual - pred)),
        "poisson_deviance": float(mean_poisson_deviance(actual, pred)),
    }


def walk_forward(df: pd.DataFrame, head: str, family: str, alpha: float,
                 min_train_seasons: int = 3) -> pd.DataFrame:
    feats = feature_columns(head)
    seasons = sorted(int(s) for s in df["season_start"].dropna().unique())
    rows: list[dict[str, Any]] = []
    for i, test_season in enumerate(seasons):
        train_seasons = seasons[:i]
        if len(train_seasons) < min_train_seasons:
            continue
        tr = df[df["season_start"].isin(train_seasons)]
        te = df[df["season_start"] == test_season]
        if len(tr) < 500 or len(te) < 50:
            continue
        m = fit_model(family, alpha, tr[feats], tr[head])
        pp = predict_model(m, family, te[feats])
        for (_, r), p in zip(te.iterrows(), pp):
            rows.append({
                "season_start": int(test_season),
                "season": str(r["season"]),
                "match_id": str(r["match_id"]),
                "player_key": str(r["player_key"]),
                "actual": float(r[head]),
                "pred": float(p),
                "player_season_games_prior": float(r["player_season_games_prior"]),
            })
    out = pd.DataFrame(rows)
    if out.empty:
        raise RuntimeError(f"No walk-forward predictions for {head} {family} alpha={alpha}")
    return out


def score_candidate(preds: pd.DataFrame, head: str, family: str, alpha: float) -> dict[str, Any]:
    y = preds["actual"].to_numpy(float)
    mu = preds["pred"].to_numpy(float)
    dispersion = estimate_nb_alpha(y, mu)
    brier = brier_at_least(y, mu, dispersion, HEAD_CONFIG[head]["thresholds"])
    return {
        "family": family,
        "regularization_alpha": float(alpha),
        **count_metrics(y, mu),
        "nb2_alpha_oos": float(dispersion),
        "brier_at_least": brier,
    }


def serialize_pipeline(model: Pipeline, family: str, alpha: float, features: list[str]) -> dict[str, Any]:
    imp: SimpleImputer = model.named_steps["imputer"]
    sc: StandardScaler = model.named_steps["scale"]
    estimator = model.named_steps["model"]
    coef = np.asarray(estimator.coef_, dtype=float).ravel()
    return {
        "family": family,
        "regularization_alpha": float(alpha),
        "link": "log" if family == "poisson" else "log1p_target_then_expm1",
        "features": list(features),
        "imputer_medians": [float(x) if math.isfinite(float(x)) else 0.0 for x in imp.statistics_],
        "scaler_mean": [float(x) for x in sc.mean_],
        "scaler_scale": [float(x if x != 0 else 1.0) for x in sc.scale_],
        "coefficients": [float(x) for x in coef],
        "intercept": float(estimator.intercept_),
    }


def early_late_metrics(preds: pd.DataFrame) -> dict[str, Any]:
    # `player_season_games_prior` is a stronger player-prop early-season regime
    # marker than calendar round because NBL schedules are uneven.
    out: dict[str, Any] = {}
    groups = {
        "SEASON_GAMES_0_2": preds[preds["player_season_games_prior"] <= 2],
        "SEASON_GAMES_3_7": preds[(preds["player_season_games_prior"] >= 3) & (preds["player_season_games_prior"] <= 7)],
        "SEASON_GAMES_8_PLUS": preds[preds["player_season_games_prior"] >= 8],
    }
    for name, g in groups.items():
        if len(g) >= 30:
            out[name] = count_metrics(g["actual"].to_numpy(float), g["pred"].to_numpy(float))
    return out


def train_head(raw: pd.DataFrame, head: str, source_receipt: dict[str, Any] | None = None) -> tuple[dict[str, Any], str]:
    df = eligible_frame(raw, head)
    features = feature_columns(head)
    candidates: list[dict[str, Any]] = []
    candidate_preds: dict[tuple[str, float], pd.DataFrame] = {}
    for family, alphas in (("poisson", (0.01, 0.1, 1.0, 10.0)), ("ridge_log1p", (1.0, 10.0, 100.0))):
        for alpha in alphas:
            preds = walk_forward(df, head, family, alpha)
            result = score_candidate(preds, head, family, alpha)
            candidates.append(result)
            candidate_preds[(family, float(alpha))] = preds
            print("CANDIDATE", head, json.dumps(result, sort_keys=True))

    # Probability calibration is the primary betting criterion. Count error then
    # breaks close candidates. Complexity is intentionally identical enough that
    # no narrative preference is used.
    best = min(candidates, key=lambda r: (
        r["brier_at_least"]["mean"], r["mae"], r["rmse"],
        0 if r["family"] == "poisson" else 1, r["regularization_alpha"],
    ))
    family, alpha = best["family"], float(best["regularization_alpha"])
    preds = candidate_preds[(family, alpha)]
    fitted = fit_model(family, alpha, df[features], df[head])
    serialized = serialize_pipeline(fitted, family, alpha, features)

    source_hash = None
    if source_receipt is not None:
        source_hash = hashlib.sha256(json.dumps(source_receipt, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    artifact = {
        "model_name": f"Nick NBL {head.upper()} QBASE",
        "model_version": MODEL_VERSION,
        "feature_schema": FEATURE_SCHEMA,
        "stat_type": head,
        "market_data": False,
        "conditional_on_player_taking_court": True,
        "training_rows": int(len(df)),
        "training_seasons": [int(df["season_start"].min()), int(df["season_start"].max())],
        "player_games_minimum_prior": 3,
        "selected_model": serialized,
        "walk_forward": {
            "first_scored_season": int(preds["season_start"].min()),
            "last_scored_season": int(preds["season_start"].max()),
            "overall": count_metrics(preds["actual"].to_numpy(float), preds["pred"].to_numpy(float)),
            "early_late": early_late_metrics(preds),
            "nb2_alpha_oos": float(best["nb2_alpha_oos"]),
            "brier_at_least": best["brier_at_least"],
            "candidate_results": candidates,
        },
        "probability_contract": {
            "distribution": "NB2 calibrated on temporal OOS predictions",
            "max_count": HEAD_CONFIG[head]["max_count"],
            "thresholds_used_for_selection": HEAD_CONFIG[head]["thresholds"],
            "half_point_props": "no push",
            "integer_props": "explicit exact-count push probability",
            "at_least_ladders": True,
        },
        "source_receipt_sha256": source_hash,
        "notes": [
            "No sportsbook odds/lines/prices/consensus are training features.",
            "All rolling player/team/opponent predictors use shift(1) and are pregame-only.",
            "Model selection is temporal walk-forward by NBL season.",
            "Probability dispersion and Brier scores use temporal OOS predictions only.",
            "This is QBASE, not final P_model: current availability, projected minutes, role, imports, lineup and coaching context are translated before freeze.",
            "New-to-NBL players without sufficient NBL history require prior-competition translation rather than average-value imputation as a final model.",
        ],
    }
    report = render_report(artifact)
    return artifact, report


def render_report(artifact: dict[str, Any]) -> str:
    wf = artifact["walk_forward"]
    selected = artifact["selected_model"]
    lines = [
        f"# {artifact['model_name']} V{artifact['model_version']} — Walk-forward Backtest",
        "",
        f"Selected: **{selected['family']}**, regularization **{selected['regularization_alpha']}**",
        f"Training rows: **{artifact['training_rows']}**, seasons {artifact['training_seasons'][0]}-{artifact['training_seasons'][1]}",
        f"OOS seasons: **{wf['first_scored_season']}-{wf['last_scored_season']}**",
        "",
        "## Candidate results",
        "",
        "| Family | Alpha | N | MAE | RMSE | Poisson deviance | NB2 alpha | Mean threshold Brier |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in sorted(wf["candidate_results"], key=lambda x: (x["brier_at_least"]["mean"], x["mae"])):
        lines.append(
            f"| {r['family']} | {r['regularization_alpha']} | {r['n']} | {r['mae']:.4f} | {r['rmse']:.4f} | "
            f"{r['poisson_deviance']:.4f} | {r['nb2_alpha_oos']:.5f} | {r['brier_at_least']['mean']:.5f} |"
        )
    lines += ["", "## Early / later player-season performance", "", "| Regime | N | MAE | RMSE | Bias |", "|---|---:|---:|---:|---:|"]
    for name, m in wf["early_late"].items():
        lines.append(f"| {name} | {m['n']} | {m['mae']:.4f} | {m['rmse']:.4f} | {m['bias_actual_minus_pred']:.4f} |")
    lines += [
        "",
        "## Integrity",
        "",
        "- Market data used: **NO**",
        "- Pregame rolling features: **shift(1) enforced**",
        "- Validation: **season-by-season temporal walk-forward**",
        "- Dispersion/calibration: **temporal OOS only**",
        "- QBASE condition: player takes the court; live availability/minutes/role research remains mandatory",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--source-receipt")
    ap.add_argument("--output-dir", default=str(HERE / "artifacts"))
    ap.add_argument("--report-dir", default=str(HERE))
    args = ap.parse_args()
    raw = pd.read_csv(args.data, low_memory=False)
    source_receipt = json.loads(Path(args.source_receipt).read_text()) if args.source_receipt else None
    outdir = Path(args.output_dir); outdir.mkdir(parents=True, exist_ok=True)
    reportdir = Path(args.report_dir); reportdir.mkdir(parents=True, exist_ok=True)
    summary = {}
    for head in ("assists", "rebounds"):
        artifact, report = train_head(raw, head, source_receipt)
        artifact_path = outdir / f"qbase_{head}_v{MODEL_VERSION}.json"
        report_path = reportdir / f"QBASE_{head.upper()}_BACKTEST.md"
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")
        report_path.write_text(report, encoding="utf-8")
        summary[head] = {
            "selected": artifact["selected_model"]["family"],
            "alpha": artifact["selected_model"]["regularization_alpha"],
            "oos": artifact["walk_forward"]["overall"],
            "brier": artifact["walk_forward"]["brier_at_least"]["mean"],
            "nb2_alpha": artifact["walk_forward"]["nb2_alpha_oos"],
        }
        print("SELECTED", head, json.dumps(summary[head], sort_keys=True))
    print("NBL_DUAL_HEAD_TRAINING=PASS", json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
