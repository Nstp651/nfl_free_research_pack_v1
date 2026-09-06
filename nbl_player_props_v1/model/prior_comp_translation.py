#!/usr/bin/env python3
"""Evidence-preserving prior-competition translation for new-to-NBL players.

V1 intentionally does not invent a Europe/NCAA/G-League -> NBL multiplier. The
neutral mean is the player's observed count-per-minute rate in a documented,
role-comparable prior sample multiplied by researched NBL minutes. Sampling
uncertainty and prior-game overdispersion are reported explicitly so the frozen
NBL distribution can be at least as wide as its validated QBASE dispersion.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any

VALID_STATS = {"assists", "rebounds"}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _num(value: Any, field: str) -> float:
    try:
        x = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not math.isfinite(x):
        raise ValueError(f"{field} must be finite")
    return x


def _quantile(values: list[float], q: float) -> float:
    if not values:
        raise ValueError("quantile requires values")
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    pos = (len(xs) - 1) * q
    lo = int(math.floor(pos)); hi = int(math.ceil(pos))
    if lo == hi:
        return xs[lo]
    w = pos - lo
    return xs[lo] * (1.0 - w) + xs[hi] * w


def estimate_prior_comp_alpha(counts: list[float], minutes: list[float], rate: float) -> float:
    """NB2 moment alpha after accounting for game-level minutes exposure."""
    mus = [max(1e-9, rate * m) for m in minutes]
    numerator = sum((y - mu) ** 2 - mu for y, mu in zip(counts, mus))
    denominator = sum(mu ** 2 for mu in mus)
    if denominator <= 0:
        return 0.0
    return max(0.0, min(5.0, numerator / denominator))


def translate_prior_comp(
    stat_type: str,
    game_rows: list[dict[str, Any]],
    *,
    competition: str,
    projected_minutes: dict[str, Any],
    evidence_source_ids: list[str],
    sample_filter_description: str,
    min_games: int = 3,
    min_total_minutes: float = 30.0,
) -> dict[str, Any]:
    """Translate a documented prior-competition sample without a league multiplier."""
    stat = str(stat_type).strip().lower()
    if stat not in VALID_STATS:
        raise ValueError(f"unsupported stat_type {stat_type}")
    competition = str(competition or "").strip()
    sample_filter_description = str(sample_filter_description or "").strip()
    if not competition or not sample_filter_description:
        raise ValueError("competition and sample_filter_description required")
    sources = [str(x).strip() for x in evidence_source_ids if str(x).strip()]
    if not sources:
        raise ValueError("evidence_source_ids required")
    if not isinstance(game_rows, list) or len(game_rows) < min_games:
        raise ValueError(f"prior competition sample needs at least {min_games} games")

    clean = []
    for idx, row in enumerate(game_rows):
        if not isinstance(row, dict):
            raise ValueError(f"game_rows[{idx}] must be an object")
        minutes = _num(row.get("minutes"), f"game_rows[{idx}].minutes")
        count = _num(row.get(stat), f"game_rows[{idx}].{stat}")
        if minutes <= 0 or minutes > 60:
            raise ValueError(f"game_rows[{idx}].minutes must be in (0,60]")
        if count < 0 or count > 50 or abs(count - round(count)) > 1e-9:
            raise ValueError(f"game_rows[{idx}].{stat} must be a nonnegative count")
        clean.append({
            "minutes": minutes,
            stat: int(round(count)),
            "date": str(row.get("date") or "").strip() or None,
            "starter": row.get("starter"),
        })

    total_minutes = sum(r["minutes"] for r in clean)
    if total_minutes < float(min_total_minutes):
        raise ValueError(f"prior competition sample needs at least {min_total_minutes} total minutes")
    counts = [float(r[stat]) for r in clean]
    minutes = [float(r["minutes"]) for r in clean]
    total_count = sum(counts)
    rate = total_count / total_minutes
    per_minute = [y / m for y, m in zip(counts, minutes)]
    p25_rate = _quantile(per_minute, 0.25)
    p75_rate = _quantile(per_minute, 0.75)
    alpha = estimate_prior_comp_alpha(counts, minutes, rate)

    if not isinstance(projected_minutes, dict):
        raise ValueError("projected_minutes must be an object")
    low = _num(projected_minutes.get("low"), "projected_minutes.low")
    mean = _num(projected_minutes.get("mean"), "projected_minutes.mean")
    high = _num(projected_minutes.get("high"), "projected_minutes.high")
    if not 0 <= low <= mean <= high <= 50:
        raise ValueError("projected_minutes must satisfy 0<=low<=mean<=high<=50")

    base_mean = rate * mean
    envelope_low = min(base_mean, p25_rate * low)
    envelope_high = max(base_mean, p75_rate * high)
    receipt_input = {
        "stat_type": stat,
        "competition": competition,
        "sample_filter_description": sample_filter_description,
        "evidence_source_ids": sources,
        "game_rows": clean,
        "projected_minutes": {"low": low, "mean": mean, "high": high},
        "method": "NO_UNVALIDATED_LEAGUE_MULTIPLIER",
    }
    receipt = sha256_json(receipt_input)
    return {
        "stat_type": stat,
        "method": "PRIOR_COMP_TRANSLATION",
        "competition": competition,
        "sample_filter_description": sample_filter_description,
        "evidence_source_ids": sources,
        "sample": {
            "games": len(clean),
            "total_minutes": total_minutes,
            "total_count": int(total_count),
            "count_per_minute_mle": rate,
            "per_minute_p25": p25_rate,
            "per_minute_p75": p75_rate,
            "prior_comp_nb2_alpha": alpha,
        },
        "projected_minutes": {"low": low, "mean": mean, "high": high},
        "base_mean": base_mean,
        "uncertainty_envelope": {"low_mean": envelope_low, "high_mean": envelope_high},
        "league_multiplier": None,
        "league_multiplier_status": "NOT_USED_UNLESS_EMPIRICALLY_VALIDATED",
        "translation_receipt_sha256": receipt,
        "freeze_scenario": {
            "id": f"prior_comp_{stat}",
            "weight": 1.0,
            "mean": base_mean,
            "method": "PRIOR_COMP_TRANSLATION",
            "evidence_source_ids": sources,
            "assumptions": [
                "Prior sample is role-comparable as documented",
                "No unvalidated league-to-NBL multiplier applied",
                "Current NBL minutes come from pre-market research",
            ],
            "quant_input_receipt_sha256": receipt,
        },
    }
