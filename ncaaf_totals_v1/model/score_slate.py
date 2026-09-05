#!/usr/bin/env python3
"""Score published NCAA research slates with the calibrated market-blind QBASE.

This is NOT final P_model. It is the reproducible quantitative baseline used by
Layer 1 triage and Layer 2 before current QB/personnel/weather scenario
translation. No sportsbook data is read.

V0.2 QBASE-slate output supports both integer and half-point totals. NCAA
bookmakers commonly post whole-number totals; those require an explicit push
probability and push-aware fair-price/EV math after freeze.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

import train_qbase as tq

SCHEMA_VERSION = "0.2.0"
# Deliberately wider than normal NCAA market totals so exact post-freeze mapping
# almost never needs a new threshold. Includes BOTH integer and half-point lines.
GRID = [x / 2.0 for x in range(40, 202)]  # 20.0 through 100.5, step 0.5


def finite(v: Any) -> float:
    try:
        x = float(v)
        return x if math.isfinite(x) else math.nan
    except (TypeError, ValueError):
        return math.nan


def profile_summary(profile: dict, state: str) -> dict | None:
    obj = profile.get(state, {}) if isinstance(profile, dict) else {}
    if not obj.get("available", False):
        return None
    s = obj.get("summary", {})
    return s if isinstance(s, dict) and s else None


def feature_row(game: dict, week: int) -> dict[str, float]:
    hp = game.get("home_profile", {})
    ap = game.get("away_profile", {})
    ch = profile_summary(hp, "current")
    ca = profile_summary(ap, "current")
    ph = profile_summary(hp, "prior_season")
    pa = profile_summary(ap, "prior_season")
    fx = game.get("fixture", {})
    st = str(fx.get("season_type", "regular")).lower()
    return tq.build_features(
        ch,
        ca,
        ph,
        pa,
        week,
        bool(fx.get("neutral_site", False)),
        "postseason" in st,
    )


def raw_predict(features: dict[str, float], artifact: dict) -> float:
    names = artifact["features"]
    med = artifact["imputer_medians"]
    mean = artifact["scaler_mean"]
    scale = artifact["scaler_scale"]
    coef = artifact["coefficients"]
    if not (len(names) == len(med) == len(mean) == len(scale) == len(coef)):
        raise ValueError("QBASE artifact vector-length mismatch")
    total = float(artifact["intercept"])
    for i, name in enumerate(names):
        x = finite(features.get(name))
        if not math.isfinite(x):
            x = float(med[i])
        sc = float(scale[i]) or 1.0
        z = (x - float(mean[i])) / sc
        total += float(coef[i]) * z
    return total


def bucket(week: int) -> str:
    return tq.week_bucket(week)


def normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def residual_cdf(r: float, dist: dict) -> float:
    """Calibrated CDF for centered out-of-sample residuals."""
    levels = [float(x) for x in dist["quantile_levels"]]
    bias = float(dist.get("bias_actual_minus_pred", 0.0))
    qs = [float(x) - bias for x in dist["residual_quantiles"]]
    sd = max(1e-6, float(dist["residual_sd"]))
    if r <= qs[0]:
        denom = max(1e-9, normal_cdf(qs[0] / sd))
        p = levels[0] * normal_cdf(r / sd) / denom
        return max(1e-6, min(levels[0], p))
    if r >= qs[-1]:
        denom = max(1e-9, 1.0 - normal_cdf(qs[-1] / sd))
        tail = (1.0 - levels[-1]) * (1.0 - normal_cdf(r / sd)) / denom
        return max(levels[-1], min(1.0 - 1e-6, 1.0 - tail))
    return float(np.interp(r, qs, levels))


def line_probabilities(mu: float, line: float, dist: dict) -> dict[str, float]:
    """Return win/push/loss probabilities for an NCAA total line.

    Final football totals are integer-valued. For a half-point line, the market
    cannot push and the CDF boundary is the line itself. For an integer line n,
    continuity-corrected mass around n is allocated to push:
      Under n = P(T <= n-1) ~= F(n-0.5)
      Push n  = P(T = n)    ~= F(n+0.5)-F(n-0.5)
      Over n  = P(T >= n+1) ~= 1-F(n+0.5)
    """
    is_integer = abs(line - round(line)) < 1e-9
    if is_integer:
        low = residual_cdf((line - 0.5) - mu, dist)
        high = residual_cdf((line + 0.5) - mu, dist)
        under = max(0.0, min(1.0, low))
        push = max(0.0, min(1.0, high - low))
        over = max(0.0, min(1.0, 1.0 - high))
    else:
        under = max(0.0, min(1.0, residual_cdf(line - mu, dist)))
        push = 0.0
        over = max(0.0, min(1.0, 1.0 - under))
    # Round only after the exact components have been constructed.
    return {
        "line": float(line),
        "over": round(over, 8),
        "push": round(push, 8),
        "under": round(under, 8),
    }


def probabilities(mu: float, dist: dict) -> list[dict[str, float]]:
    out = [line_probabilities(mu, line, dist) for line in GRID]

    # Integrity: as the line rises, Over cannot rise and Under cannot fall.
    for a, b in zip(out, out[1:]):
        if b["over"] > a["over"] + 1e-10 or b["under"] < a["under"] - 1e-10:
            raise ValueError("Probability grid is non-monotonic")

    # Every line partitions the integer-valued total into Over/Push/Under.
    if any(abs(x["over"] + x["push"] + x["under"] - 1.0) > 3e-8 for x in out):
        raise ValueError("Probability partition audit failed")

    # Half-point lines cannot push; integer lines must never carry negative mass.
    for x in out:
        if abs(x["line"] - round(x["line"])) >= 1e-9 and abs(x["push"]) > 1e-12:
            raise ValueError("Half-point line has non-zero push probability")
        if x["push"] < -1e-12:
            raise ValueError("Negative push probability")
    return out


def score_pack(pack: dict, artifact: dict) -> dict:
    if pack.get("market_data") is not False or artifact.get("market_data") is not False:
        raise ValueError("Market boundary violation")
    if artifact.get("feature_schema") != tq.TRAINING_FEATURE_SCHEMA:
        raise ValueError("QBASE feature schema mismatch")
    week = int(pack["week"])
    all_dist = artifact["walk_forward"]["residual_distribution"]
    key = bucket(week)
    dist = all_dist.get(key) or all_dist["ALL"]
    bias = float(dist.get("bias_actual_minus_pred", 0.0))
    games = []
    for game in pack.get("games", []):
        feats = feature_row(game, week)
        raw = raw_predict(feats, artifact)
        mu = raw + bias
        missing = sum(
            1 for n in artifact["features"] if not math.isfinite(finite(feats.get(n)))
        )
        games.append(
            {
                "game_id": str(game["game_id"]),
                "home_team": game.get("fixture", {}).get("home_team"),
                "away_team": game.get("fixture", {}).get("away_team"),
                "expected_total_raw": round(raw, 6),
                "oos_bias_calibration": round(bias, 6),
                "expected_total_qbase": round(mu, 6),
                "residual_bucket": key if key in all_dist else "ALL",
                "residual_sd": round(float(dist["residual_sd"]), 6),
                "missing_feature_count_before_imputation": missing,
                "probability_grid": probabilities(mu, dist),
            }
        )
    model_bytes = json.dumps(artifact, sort_keys=True, separators=(",", ":")).encode()
    material = json.dumps(
        {
            "pack_revision": pack["pack_revision"],
            "model_sha256": hashlib.sha256(model_bytes).hexdigest(),
            "probability_schema": SCHEMA_VERSION,
            "games": games,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return {
        "schema_version": SCHEMA_VERSION,
        "market_data": False,
        "slate_id": pack["slate_id"],
        "season": pack["season"],
        "week": week,
        "research_pack_revision": pack["pack_revision"],
        "qbase_model_name": artifact["model_name"],
        "qbase_model_version": artifact["model_version"],
        "qbase_model_sha256": hashlib.sha256(model_bytes).hexdigest(),
        "qbase_revision": hashlib.sha256(material).hexdigest()[:16],
        "supported_total_grid": {"min": GRID[0], "max": GRID[-1], "step": 0.5},
        "integer_line_method": "continuity_corrected_discrete_mass",
        "walk_forward_reference": artifact["walk_forward"]["overall"],
        "games": games,
        "notes": [
            "QBASE is pre-market and not final P_model.",
            "Current live QB/personnel/weather scenario translation occurs after this baseline and before freeze.",
            "Integer totals include explicit push probability; half-point totals have push=0.",
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data")
    ap.add_argument("--artifact", default="model/qbase_v0.1.0.json")
    ap.add_argument("--output-root", default="model/slates")
    args = ap.parse_args()
    root = Path(args.data)
    artifact = json.loads(Path(args.artifact).read_text())
    manifest = json.loads((root / "manifest.json").read_text())
    if artifact.get("market_data") is not False:
        raise SystemExit("QBASE market boundary violation")
    for entry in manifest["slates"]:
        p = root / "slates" / str(entry["season"]) / f"{entry['slate_id']}.json"
        pack = json.loads(p.read_text())
        scored = score_pack(pack, artifact)
        out = Path(args.output_root) / str(entry["season"]) / f"{entry['slate_id']}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(scored, indent=2, sort_keys=True))
        print(
            f"QBASE_SCORE slate={entry['slate_id']} games={len(scored['games'])} "
            f"revision={scored['qbase_revision']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
