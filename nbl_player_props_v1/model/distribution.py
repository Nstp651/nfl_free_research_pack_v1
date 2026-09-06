#!/usr/bin/env python3
"""Discrete probability layer for NBL player assists/rebounds.

The mean comes from the stat-specific quantitative head plus pre-freeze context.
Dispersion is calibrated only from temporal out-of-sample residuals. The shipped
V1 distribution is Negative Binomial when overdispersion is present and converges
to Poisson when alpha is effectively zero.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy.stats import nbinom, poisson


def estimate_nb_alpha(actual: np.ndarray, mean: np.ndarray) -> float:
    y = np.asarray(actual, dtype=float)
    mu = np.maximum(np.asarray(mean, dtype=float), 1e-6)
    mask = np.isfinite(y) & np.isfinite(mu) & (y >= 0)
    y, mu = y[mask], mu[mask]
    if len(y) < 30:
        raise ValueError("Need at least 30 OOS rows for dispersion calibration")
    # NB2: Var(Y|mu) = mu + alpha*mu^2. Aggregate moment estimate avoids
    # unstable per-row ratios for low-count assists.
    numerator = float(np.sum((y - mu) ** 2 - mu))
    denominator = float(np.sum(mu ** 2))
    return max(1e-6, min(5.0, numerator / max(denominator, 1e-9)))


def _nb_params(mu: float, alpha: float) -> tuple[float, float]:
    if mu < 0 or not math.isfinite(mu):
        raise ValueError("mu must be finite and nonnegative")
    if alpha <= 0 or not math.isfinite(alpha):
        raise ValueError("alpha must be finite and positive")
    r = 1.0 / alpha
    p = r / (r + max(mu, 0.0))
    return r, p


def pmf(k: int, mu: float, alpha: float) -> float:
    if k < 0:
        return 0.0
    if alpha <= 1e-5:
        return float(poisson.pmf(k, mu))
    r, p = _nb_params(mu, alpha)
    return float(nbinom.pmf(k, r, p))


def cdf(k: int, mu: float, alpha: float) -> float:
    if k < 0:
        return 0.0
    if alpha <= 1e-5:
        return float(poisson.cdf(k, mu))
    r, p = _nb_params(mu, alpha)
    return float(nbinom.cdf(k, r, p))


def at_least(threshold: int, mu: float, alpha: float) -> float:
    if threshold <= 0:
        return 1.0
    return max(0.0, min(1.0, 1.0 - cdf(threshold - 1, mu, alpha)))


def half_line(line: float, mu: float, alpha: float) -> dict[str, float]:
    """O/U probability for x.5 player-prop line; no push."""
    if abs((line * 2) - round(line * 2)) > 1e-9 or abs(line - round(line)) < 1e-9:
        raise ValueError("half_line requires an x.5 threshold")
    floor = math.floor(line)
    under = cdf(floor, mu, alpha)
    over = 1.0 - under
    return {"line": float(line), "over": float(over), "push": 0.0, "under": float(under)}


def integer_line(line: int, mu: float, alpha: float) -> dict[str, float]:
    """Push-aware integer O/U market, included for adapter optionality."""
    n = int(line)
    under = cdf(n - 1, mu, alpha)
    push = pmf(n, mu, alpha)
    over = max(0.0, 1.0 - under - push)
    return {"line": float(n), "over": float(over), "push": float(push), "under": float(under)}


def probability_grid(mu: float, alpha: float, max_count: int) -> dict[str, Any]:
    if max_count < 5:
        raise ValueError("max_count too small")
    counts = [{"count": k, "probability": pmf(k, mu, alpha)} for k in range(max_count + 1)]
    tail = max(0.0, 1.0 - sum(x["probability"] for x in counts))
    ladders = [{"threshold": k, "at_least": at_least(k, mu, alpha)} for k in range(1, max_count + 1)]
    half_lines = [half_line(k + 0.5, mu, alpha) for k in range(0, max_count)]
    integer_lines = [integer_line(k, mu, alpha) for k in range(1, max_count + 1)]
    # Core numerical audits.
    if any(ladders[i + 1]["at_least"] > ladders[i]["at_least"] + 1e-12 for i in range(len(ladders) - 1)):
        raise ValueError("at-least ladder is non-monotonic")
    for row in half_lines + integer_lines:
        if min(row["over"], row["push"], row["under"]) < -1e-12:
            raise ValueError("negative probability")
        if abs(row["over"] + row["push"] + row["under"] - 1.0) > 1e-9:
            raise ValueError("probability partition failed")
    return {
        "distribution": "negative_binomial_nb2" if alpha > 1e-5 else "poisson",
        "mean": float(mu),
        "alpha": float(alpha),
        "max_count": int(max_count),
        "count_pmf": counts,
        "tail_above_max_count": tail,
        "at_least_ladder": ladders,
        "half_point_grid": half_lines,
        "integer_push_grid": integer_lines,
    }


def brier_at_least(actual: np.ndarray, means: np.ndarray, alpha: float,
                   thresholds: list[int]) -> dict[str, float]:
    y = np.asarray(actual, dtype=float)
    mu = np.asarray(means, dtype=float)
    out: dict[str, float] = {}
    scores = []
    for t in thresholds:
        probs = np.array([at_least(t, float(m), alpha) for m in mu])
        obs = (y >= t).astype(float)
        score = float(np.mean((probs - obs) ** 2))
        out[str(t)] = score
        scores.append(score)
    out["mean"] = float(np.mean(scores)) if scores else math.nan
    return out
