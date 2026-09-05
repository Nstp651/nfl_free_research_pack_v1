#!/usr/bin/env python3
"""Train Nick NCAA Totals QBASE from market-blind, leak-free historical data.

QBASE is the quantitative baseline used BEFORE live/context research adjustments.
It is deliberately transparent: a regularised linear model on symmetric matchup
features, trained and scored walk-forward by season.  The production artifact is
plain JSON so every weekly prediction can be reproduced without pickle/joblib.

Leakage boundary:
  game in week W may only use current-season team snapshot through W-1.
The final score is target-only and never enters a feature.
No betting-lines dataset is downloaded or referenced.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import build_pack as bp  # noqa: E402

MODEL_VERSION = "0.1.0"
TRAINING_FEATURE_SCHEMA = "qbase_features_v1"

SUMMARY_FIELDS = [
    "valid_games",
    "playsgame_off", "playsgame_def",
    "EPAplay_off", "EPAplay_def",
    "EPAplay_off_pass", "EPAplay_def_pass",
    "EPAplay_off_rush", "EPAplay_def_rush",
    "success_off", "success_def",
    "explosive_off", "explosive_def",
    "havoc_off", "havoc_def",
    "passrate_off", "passrate_def",
    "adj_off_epa", "adj_def_epa", "net_adj_epa",
]

COMPONENTS = [
    "pace_total",
    "adj_epa_matchup_total",
    "raw_epa_matchup_total",
    "pass_epa_matchup_total",
    "rush_epa_matchup_total",
    "success_matchup_total",
    "explosive_matchup_total",
    "havoc_matchup_total",
    "passrate_total",
    "off_epa_sum",
    "def_epa_sum",
]

# Core is deliberately compact; full adds current/prior decomposition so Ridge
# can learn whether the blend is too aggressive in a particular regime.
CORE_FEATURES = [
    "blend4_pace_total",
    "blend4_adj_epa_matchup_total",
    "blend4_raw_epa_matchup_total",
    "blend4_pass_epa_matchup_total",
    "blend4_rush_epa_matchup_total",
    "blend4_success_matchup_total",
    "blend4_explosive_matchup_total",
    "blend4_havoc_matchup_total",
    "blend4_passrate_total",
    "cur_weight",
    "current_available_both",
    "week_sqrt",
    "neutral_site",
    "postseason",
]
FULL_FEATURES = CORE_FEATURES + [
    f"{prefix}_{component}"
    for prefix in ("cur", "prior")
    for component in COMPONENTS
]


def finite(value: Any) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else math.nan
    except (TypeError, ValueError):
        return math.nan


def rid(value: Any) -> str | None:
    return bp.norm_id(value)


@dataclass
class TeamTimeline:
    rows: dict[str, list[tuple[int, dict[str, Any]]]]

    @classmethod
    def from_frame(cls, df: pd.DataFrame, season: int) -> "TeamTimeline":
        if df.empty:
            return cls({})
        team_col = bp.first_col(df, "team_id", "pos_team_id", "id")
        week_col = bp.first_col(df, "through_week", "week")
        if not team_col or not week_col:
            raise ValueError("weekly source missing team_id/through_week")
        work = df.copy()
        if "season" in work.columns:
            work = work[pd.to_numeric(work["season"], errors="coerce") == season]
        rows: dict[str, list[tuple[int, dict[str, Any]]]] = {}
        for _, r in work.iterrows():
            tid = rid(r.get(team_col))
            try:
                w = int(r.get(week_col))
            except Exception:
                continue
            if not tid:
                continue
            d = {k: r.get(k) for k in SUMMARY_FIELDS if k in r.index}
            rows.setdefault(tid, []).append((w, d))
        for tid in rows:
            rows[tid].sort(key=lambda x: x[0])
        return cls(rows)

    def asof(self, team_id: str | None, cutoff: int) -> dict[str, Any] | None:
        if not team_id or cutoff < 0:
            return None
        seq = self.rows.get(team_id, [])
        chosen = None
        for w, row in seq:
            if w <= cutoff:
                chosen = row
            else:
                break
        return chosen

    def final(self, team_id: str | None) -> dict[str, Any] | None:
        seq = self.rows.get(team_id or "", [])
        return seq[-1][1] if seq else None


def v(row: dict[str, Any] | None, key: str) -> float:
    return math.nan if row is None else finite(row.get(key))


def sum_if(*xs: float) -> float:
    return float(sum(xs)) if all(math.isfinite(x) for x in xs) else math.nan


def component_values(home: dict[str, Any] | None, away: dict[str, Any] | None) -> dict[str, float]:
    if home is None or away is None:
        return {c: math.nan for c in COMPONENTS}

    # Each matchup edge is own offense PLUS what opponent defense allows.
    # This matches the direction used in cfbfastR's matchup feature design.
    pace_home = sum_if(v(home, "playsgame_off"), v(away, "playsgame_def"))
    pace_away = sum_if(v(away, "playsgame_off"), v(home, "playsgame_def"))
    pace_total = math.nan if not (math.isfinite(pace_home) and math.isfinite(pace_away)) else 0.5 * (pace_home + pace_away)

    def matchup(off_key: str, def_key: str) -> float:
        return sum_if(v(home, off_key), v(away, def_key), v(away, off_key), v(home, def_key))

    pass_home = sum_if(v(home, "passrate_off"), v(away, "passrate_def"))
    pass_away = sum_if(v(away, "passrate_off"), v(home, "passrate_def"))
    passrate_total = math.nan if not (math.isfinite(pass_home) and math.isfinite(pass_away)) else 0.5 * (pass_home + pass_away)

    return {
        "pace_total": pace_total,
        "adj_epa_matchup_total": matchup("adj_off_epa", "adj_def_epa"),
        "raw_epa_matchup_total": matchup("EPAplay_off", "EPAplay_def"),
        "pass_epa_matchup_total": matchup("EPAplay_off_pass", "EPAplay_def_pass"),
        "rush_epa_matchup_total": matchup("EPAplay_off_rush", "EPAplay_def_rush"),
        "success_matchup_total": matchup("success_off", "success_def"),
        "explosive_matchup_total": matchup("explosive_off", "explosive_def"),
        "havoc_matchup_total": matchup("havoc_off", "havoc_def"),
        "passrate_total": passrate_total,
        "off_epa_sum": sum_if(v(home, "EPAplay_off"), v(away, "EPAplay_off")),
        "def_epa_sum": sum_if(v(home, "EPAplay_def"), v(away, "EPAplay_def")),
    }


def games_min(home: dict[str, Any] | None, away: dict[str, Any] | None) -> float:
    gh, ga = v(home, "valid_games"), v(away, "valid_games")
    if not math.isfinite(gh) or not math.isfinite(ga):
        return math.nan
    return max(0.0, min(gh, ga))


def build_features(current_h: dict[str, Any] | None, current_a: dict[str, Any] | None,
                   prior_h: dict[str, Any] | None, prior_a: dict[str, Any] | None,
                   week: int, neutral: bool, postseason: bool) -> dict[str, float]:
    cur = component_values(current_h, current_a)
    prior = component_values(prior_h, prior_a)
    n = games_min(current_h, current_a)
    current_both = current_h is not None and current_a is not None
    if not math.isfinite(n):
        n = 0.0
    w = n / (n + 4.0) if n > 0 else 0.0
    out: dict[str, float] = {
        "cur_weight": w,
        "current_available_both": 1.0 if current_both else 0.0,
        "week_sqrt": math.sqrt(max(0, week)),
        "neutral_site": 1.0 if neutral else 0.0,
        "postseason": 1.0 if postseason else 0.0,
    }
    for c in COMPONENTS:
        cv, pv = cur[c], prior[c]
        out[f"cur_{c}"] = cv
        out[f"prior_{c}"] = pv
        if math.isfinite(cv) and math.isfinite(pv):
            out[f"blend4_{c}"] = w * cv + (1.0 - w) * pv
        elif math.isfinite(cv):
            out[f"blend4_{c}"] = cv
        else:
            out[f"blend4_{c}"] = pv
    return out


def schedule_games(schedule: pd.DataFrame, season: int) -> pd.DataFrame:
    df = schedule.copy()
    if "season" in df.columns:
        df = df[pd.to_numeric(df["season"], errors="coerce") == season]
    if "fbs_game" not in df.columns:
        raise ValueError(f"{season} schedule missing fbs_game")
    df = df[bp.to_bool(df["fbs_game"])]
    if "completed" in df.columns:
        df = df[bp.to_bool(df["completed"])]
    if "season_type" in df.columns:
        df = df[df["season_type"].astype(str).str.lower().isin({"regular", "postseason", "spring_regular", "spring_postseason"})]
    hp, ap = bp.first_col(df, "home_points"), bp.first_col(df, "away_points")
    if not hp or not ap:
        raise ValueError(f"{season} schedule missing points")
    df = df[pd.to_numeric(df[hp], errors="coerce").notna() & pd.to_numeric(df[ap], errors="coerce").notna()]
    return df


def load_season(season: int, cache: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    cache.mkdir(parents=True, exist_ok=True)
    receipts = {}
    out = []
    for key, tag in (("schedule", "cfb_schedules"), ("weekly", "cfb_team_summaries_weekly")):
        csv_path = cache / f"{tag}_{season}.csv"
        receipt_path = cache / f"{tag}_{season}.receipt.json"
        if csv_path.exists() and receipt_path.exists():
            df = pd.read_csv(csv_path, low_memory=False)
            receipt = json.loads(receipt_path.read_text())
        else:
            df, receipt = bp.download_asset(tag, season)
            df.to_csv(csv_path, index=False)
            receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True))
        receipts[key] = receipt
        out.append(df)
    return out[0], out[1], receipts


def build_frame(start: int, end: int, cache: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    loaded: dict[int, tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]] = {}
    receipts: dict[str, Any] = {}
    for season in range(start - 1, end + 1):
        sched, weekly, rec = load_season(season, cache)
        loaded[season] = (sched, weekly, rec)
        receipts[str(season)] = rec

    rows = []
    for season in range(start, end + 1):
        sched, weekly, _ = loaded[season]
        prior_weekly = loaded[season - 1][1]
        cur_timeline = TeamTimeline.from_frame(weekly, season)
        prior_timeline = TeamTimeline.from_frame(prior_weekly, season - 1)
        games = schedule_games(sched, season)
        for _, g in games.iterrows():
            try:
                week = int(g.get("week"))
            except Exception:
                continue
            hid, aid = rid(g.get("home_id")), rid(g.get("away_id"))
            if not hid or not aid:
                continue
            cutoff = week - 1
            ch, ca = cur_timeline.asof(hid, cutoff), cur_timeline.asof(aid, cutoff)
            ph, pa = prior_timeline.final(hid), prior_timeline.final(aid)
            # Require prior evidence for both teams. This keeps the shipped V1
            # baseline honest; new-to-FBS teams are a live-research / fragility
            # case rather than silently imputed as average.
            if ph is None or pa is None:
                continue
            neutral = bool(bp.to_bool(pd.Series([g.get("neutral_site", False)])).iloc[0])
            st = str(g.get("season_type", "regular")).lower()
            postseason = "postseason" in st
            feat = build_features(ch, ca, ph, pa, week, neutral, postseason)
            hp, ap = finite(g.get("home_points")), finite(g.get("away_points"))
            if not math.isfinite(hp) or not math.isfinite(ap):
                continue
            rows.append({
                "season": season,
                "week": week,
                "game_id": rid(g.get("game_id")) or str(len(rows)),
                "total": hp + ap,
                **feat,
            })
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise RuntimeError("training frame is empty")
    return frame, receipts


def pipeline(alpha: float) -> Pipeline:
    return Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
        ("ridge", Ridge(alpha=alpha)),
    ])


def week_bucket(week: int) -> str:
    if week <= 1:
        return "WEEK_0_1"
    if week <= 4:
        return "WEEK_2_4"
    return "WEEK_5_PLUS"


def metrics(y: np.ndarray, p: np.ndarray) -> dict[str, float | int]:
    e = y - p
    return {
        "n": int(len(y)),
        "mae": float(mean_absolute_error(y, p)),
        "rmse": float(math.sqrt(mean_squared_error(y, p))),
        "bias_actual_minus_pred": float(np.mean(e)),
        "residual_sd": float(np.std(e, ddof=1)) if len(e) > 1 else 0.0,
    }


def walk_forward(frame: pd.DataFrame, features: list[str], alpha: float, min_train_seasons: int = 3) -> pd.DataFrame:
    seasons = sorted(frame["season"].unique())
    preds = []
    for i, test_season in enumerate(seasons):
        train_seasons = seasons[:i]
        if len(train_seasons) < min_train_seasons:
            continue
        tr = frame[frame["season"].isin(train_seasons)]
        te = frame[frame["season"] == test_season]
        if tr.empty or te.empty:
            continue
        m = pipeline(alpha)
        m.fit(tr[features], tr["total"])
        pp = m.predict(te[features])
        for (_, row), pred in zip(te.iterrows(), pp):
            preds.append({
                "season": int(test_season), "week": int(row["week"]),
                "game_id": row["game_id"], "actual": float(row["total"]),
                "pred": float(pred), "residual": float(row["total"] - pred),
            })
    return pd.DataFrame(preds)


def residual_distribution(preds: pd.DataFrame) -> dict[str, Any]:
    levels = np.round(np.arange(0.01, 1.00, 0.01), 2)
    out = {}
    groups = {"ALL": preds}
    for bucket in ("WEEK_0_1", "WEEK_2_4", "WEEK_5_PLUS"):
        groups[bucket] = preds[preds["week"].map(week_bucket) == bucket]
    for key, g in groups.items():
        r = g["residual"].to_numpy(float)
        if len(r) < 30:
            continue
        q = np.quantile(r, levels)
        out[key] = {
            **metrics(g["actual"].to_numpy(float), g["pred"].to_numpy(float)),
            "quantile_levels": [float(x) for x in levels],
            "residual_quantiles": [round(float(x), 5) for x in q],
        }
    return out


def export_model(fitted: Pipeline, features: list[str], alpha: float, frame: pd.DataFrame,
                 preds: pd.DataFrame, receipts: dict[str, Any], out: Path,
                 candidate_results: list[dict[str, Any]]) -> dict[str, Any]:
    imp: SimpleImputer = fitted.named_steps["imputer"]
    sc: StandardScaler = fitted.named_steps["scale"]
    rg: Ridge = fitted.named_steps["ridge"]
    source_digest = hashlib.sha256(json.dumps(receipts, sort_keys=True).encode()).hexdigest()
    artifact = {
        "model_name": "Nick NCAA Totals QBASE",
        "model_version": MODEL_VERSION,
        "feature_schema": TRAINING_FEATURE_SCHEMA,
        "market_data": False,
        "training_seasons": [int(frame["season"].min()), int(frame["season"].max())],
        "training_games": int(len(frame)),
        "selected_family": "ridge_full" if features == FULL_FEATURES else "ridge_core",
        "alpha": float(alpha),
        "features": features,
        "imputer_medians": [float(x) for x in imp.statistics_],
        "scaler_mean": [float(x) for x in sc.mean_],
        "scaler_scale": [float(x if x != 0 else 1.0) for x in sc.scale_],
        "coefficients": [float(x) for x in rg.coef_],
        "intercept": float(rg.intercept_),
        "walk_forward": {
            "first_scored_season": int(preds["season"].min()),
            "last_scored_season": int(preds["season"].max()),
            "overall": metrics(preds["actual"].to_numpy(float), preds["pred"].to_numpy(float)),
            "residual_distribution": residual_distribution(preds),
            "candidate_results": candidate_results,
        },
        "source_receipt_sha256": source_digest,
        "notes": [
            "Training is market-blind; no odds/lines/consensus features are used.",
            "A game in week W only uses current-season features through W-1.",
            "Week 0/1 therefore rests on prior-season structured evidence before live contextual translation.",
            "Residual quantiles are from temporal walk-forward predictions, not in-sample residuals.",
            "This is a quantitative baseline; material current QB/personnel/weather context belongs in Layer 1C/Layer 2 scenarios.",
        ],
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, indent=2, sort_keys=True))
    return artifact


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=2016)
    ap.add_argument("--end", type=int, default=2025)
    ap.add_argument("--cache", default="/tmp/ncaaf-qbase-cache")
    ap.add_argument("--output", default=str(ROOT / "model" / "qbase_v0.1.0.json"))
    ap.add_argument("--report", default=str(ROOT / "model" / "QBASE_BACKTEST.md"))
    args = ap.parse_args()

    frame, receipts = build_frame(args.start, args.end, Path(args.cache))
    print(f"TRAINING_FRAME games={len(frame)} seasons={frame.season.min()}-{frame.season.max()}")
    print("games_by_season=", frame.groupby("season").size().to_dict())

    candidate_results = []
    best = None
    for family, feats in (("ridge_core", CORE_FEATURES), ("ridge_full", FULL_FEATURES)):
        for alpha in (0.1, 1.0, 10.0, 100.0):
            pred = walk_forward(frame, feats, alpha)
            m = metrics(pred["actual"].to_numpy(float), pred["pred"].to_numpy(float))
            result = {"family": family, "alpha": alpha, **m}
            candidate_results.append(result)
            print("CANDIDATE", json.dumps(result, sort_keys=True))
            key = (m["mae"], m["rmse"], len(feats), alpha)
            if best is None or key < best[0]:
                best = (key, family, feats, alpha, pred)

    assert best is not None
    _, family, features, alpha, preds = best
    fitted = pipeline(alpha)
    fitted.fit(frame[features], frame["total"])
    artifact = export_model(fitted, features, alpha, frame, preds, receipts, Path(args.output), candidate_results)

    # Human-readable audit report, generated from executed results.
    dist = artifact["walk_forward"]["residual_distribution"]
    lines = [
        "# NCAA Totals QBASE V0.1.0 — Walk-forward Backtest",
        "",
        f"Selected: **{family}**, alpha **{alpha}**",
        f"Training frame: **{len(frame)}** FBS-v-FBS games, {args.start}-{args.end}.",
        "",
        "## Candidate results",
        "",
        "| Family | Alpha | N | MAE | RMSE | Bias | Residual SD |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in sorted(candidate_results, key=lambda x: (x["mae"], x["rmse"])):
        lines.append(f"| {r['family']} | {r['alpha']} | {r['n']} | {r['mae']:.3f} | {r['rmse']:.3f} | {r['bias_actual_minus_pred']:.3f} | {r['residual_sd']:.3f} |")
    lines += ["", "## Selected model residual calibration", "", "| Bucket | N | MAE | RMSE | Bias | Residual SD |", "|---|---:|---:|---:|---:|---:|"]
    for k, d in dist.items():
        lines.append(f"| {k} | {d['n']} | {d['mae']:.3f} | {d['rmse']:.3f} | {d['bias_actual_minus_pred']:.3f} | {d['residual_sd']:.3f} |")
    lines += [
        "",
        "## Integrity",
        "",
        "- Market data used: **NO**",
        "- Current-season cutoff: **week W uses through W-1**",
        "- Model selection: temporal walk-forward by season",
        "- Residual calibration: temporal out-of-sample residuals",
        "- Current injuries/QB/weather: intentionally outside QBASE",
        "",
    ]
    Path(args.report).write_text("\n".join(lines))
    print("SELECTED", family, alpha)
    print("OVERALL", json.dumps(artifact["walk_forward"]["overall"], sort_keys=True))
    print("WROTE", args.output)
    print("WROTE", args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
