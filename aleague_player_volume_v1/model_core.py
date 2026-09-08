"""Deterministic quantitative primitives for A-League Player Volume V1.

This module intentionally contains no sportsbook/network code.
Layers 0-2 must remain market blind.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import exp, lgamma, log
from typing import Any, Dict, Iterable, Mapping


MODEL_VERSION = "ALEAGUE_PLAYER_VOLUME_V1_0.1.0"

PROHIBITED_MARKET_KEYS = {
    "odds",
    "price",
    "decimal_price",
    "american_price",
    "implied_probability",
    "sportsbook",
    "bookmaker",
    "market_line",
    "consensus_line",
    "bet365",
    "sportsbet",
    "tab",
    "ladbrokes",
    "unibet",
}


class ModelIntegrityError(ValueError):
    pass


def assert_market_blind(payload: Any, path: str = "root") -> None:
    """Reject market-like fields anywhere inside a pre-market payload."""
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            normalized = str(key).strip().lower()
            if normalized in PROHIBITED_MARKET_KEYS:
                raise ModelIntegrityError(f"market-derived field prohibited at {path}.{key}")
            assert_market_blind(value, f"{path}.{key}")
    elif isinstance(payload, (list, tuple)):
        for idx, value in enumerate(payload):
            assert_market_blind(value, f"{path}[{idx}]")


def _validate_nonnegative(name: str, value: float) -> None:
    if value < 0:
        raise ModelIntegrityError(f"{name} must be >= 0")


def _validate_probability(name: str, value: float) -> None:
    if not 0.0 <= value <= 1.0:
        raise ModelIntegrityError(f"{name} must be within [0, 1]")


def shrink_binomial_rate(
    successes: float,
    trials: float,
    prior_rate: float,
    prior_strength: float,
) -> float:
    """Beta-binomial posterior mean using a rate/strength prior."""
    _validate_nonnegative("successes", successes)
    _validate_nonnegative("trials", trials)
    _validate_probability("prior_rate", prior_rate)
    _validate_nonnegative("prior_strength", prior_strength)
    if successes > trials:
        raise ModelIntegrityError("successes cannot exceed trials")
    denom = trials + prior_strength
    if denom <= 0:
        raise ModelIntegrityError("trials + prior_strength must be > 0")
    return (successes + prior_rate * prior_strength) / denom


def negative_binomial_log_pmf(k: int, mean: float, dispersion: float) -> float:
    """NB2 log-PMF with Var[X] = mean + mean^2 / dispersion."""
    if k < 0:
        raise ModelIntegrityError("k must be >= 0")
    _validate_nonnegative("mean", mean)
    if dispersion <= 0:
        raise ModelIntegrityError("dispersion must be > 0")
    if mean == 0:
        return 0.0 if k == 0 else float("-inf")
    r = dispersion
    p = r / (r + mean)
    return (
        lgamma(k + r)
        - lgamma(r)
        - lgamma(k + 1)
        + r * log(p)
        + k * log(1.0 - p)
    )


def negative_binomial_pmf(k: int, mean: float, dispersion: float) -> float:
    value = negative_binomial_log_pmf(k, mean, dispersion)
    return 0.0 if value == float("-inf") else exp(value)


def probability_at_least(threshold: int, mean: float, dispersion: float) -> float:
    """P(X >= threshold) for an NB2 count variable."""
    if threshold <= 0:
        return 1.0
    _validate_nonnegative("mean", mean)
    if dispersion <= 0:
        raise ModelIntegrityError("dispersion must be > 0")
    cdf = sum(negative_binomial_pmf(k, mean, dispersion) for k in range(threshold))
    return min(1.0, max(0.0, 1.0 - cdf))


def build_at_least_ladder(mean: float, dispersion: float, max_threshold: int = 8) -> Dict[int, float]:
    if max_threshold < 1:
        raise ModelIntegrityError("max_threshold must be >= 1")
    ladder = {
        threshold: probability_at_least(threshold, mean, dispersion)
        for threshold in range(1, max_threshold + 1)
    }
    previous = 1.0
    for threshold in sorted(ladder):
        value = ladder[threshold]
        if value > previous + 1e-12:
            raise ModelIntegrityError("ladder monotonicity failure")
        previous = value
    return ladder


@dataclass(frozen=True)
class PlayerShotProjection:
    player_id: str
    minutes_mean: float
    normalized_shot_share: float
    role_multiplier: float = 1.0

    def validate(self) -> None:
        if not self.player_id:
            raise ModelIntegrityError("player_id required")
        if not 0 <= self.minutes_mean <= 130:
            raise ModelIntegrityError("minutes_mean outside supported football range")
        if not 0 <= self.normalized_shot_share <= 1:
            raise ModelIntegrityError("normalized_shot_share must be within [0, 1]")
        if not 0 < self.role_multiplier <= 2.0:
            raise ModelIntegrityError("role_multiplier outside hard V1 bound (0, 2]")


def expected_player_shots(team_shot_mean: float, projection: PlayerShotProjection) -> float:
    """Allocate a team 90-minute shot environment to a projected player."""
    _validate_nonnegative("team_shot_mean", team_shot_mean)
    projection.validate()
    return (
        team_shot_mean
        * projection.normalized_shot_share
        * (projection.minutes_mean / 90.0)
        * projection.role_multiplier
    )


def expected_player_sot(player_shot_mean: float, p_sot_given_shot: float) -> float:
    _validate_nonnegative("player_shot_mean", player_shot_mean)
    _validate_probability("p_sot_given_shot", p_sot_given_shot)
    return player_shot_mean * p_sot_given_shot


def expected_goalkeeper_saves(
    opponent_sot_mean_90: float,
    p_save_given_sot: float,
    minutes_mean: float,
) -> float:
    _validate_nonnegative("opponent_sot_mean_90", opponent_sot_mean_90)
    _validate_probability("p_save_given_sot", p_save_given_sot)
    if not 0 <= minutes_mean <= 130:
        raise ModelIntegrityError("goalkeeper minutes_mean outside supported football range")
    return opponent_sot_mean_90 * p_save_given_sot * (minutes_mean / 90.0)


def allocation_audit(
    team_shot_mean: float,
    player_means: Iterable[float],
    unmodelled_mean: float,
    tolerance: float = 1e-6,
) -> None:
    _validate_nonnegative("team_shot_mean", team_shot_mean)
    _validate_nonnegative("unmodelled_mean", unmodelled_mean)
    total = unmodelled_mean
    for value in player_means:
        _validate_nonnegative("player_mean", value)
        total += value
    if abs(total - team_shot_mean) > tolerance:
        raise ModelIntegrityError(
            f"shot allocation mismatch: allocated={total:.8f}, team_mean={team_shot_mean:.8f}"
        )
