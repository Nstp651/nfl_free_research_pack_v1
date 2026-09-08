"""Deterministic quantitative primitives for A-League Player Volume V1.

This module intentionally contains no sportsbook/network code.
Layers 0-2 must remain market blind.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import exp, lgamma, log
from typing import Any, Dict, Iterable, Mapping, Sequence, Tuple


MODEL_VERSION = "ALEAGUE_PLAYER_VOLUME_V1_0.3.0"

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
                raise ModelIntegrityError(f"market-derived field prohibited pre-freeze: {path}.{key}")
            assert_market_blind(value, f"{path}.{key}")
    elif isinstance(payload, (list, tuple)):
        for index, value in enumerate(payload):
            assert_market_blind(value, f"{path}[{index}]")


def negative_binomial_log_pmf(k: int, mean: float, dispersion: float) -> float:
    """NB2 log PMF with Var(Y)=mean + mean^2/dispersion."""
    if k < 0 or int(k) != k:
        raise ModelIntegrityError("k must be a nonnegative integer")
    if mean < 0 or dispersion <= 0:
        raise ModelIntegrityError("mean must be >= 0 and dispersion > 0")
    if mean == 0:
        return 0.0 if k == 0 else float("-inf")
    r = float(dispersion)
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
    if threshold <= 0:
        return 1.0
    cdf = sum(negative_binomial_pmf(k, mean, dispersion) for k in range(threshold))
    return min(1.0, max(0.0, 1.0 - cdf))


def build_at_least_ladder(mean: float, dispersion: float, max_threshold: int) -> Dict[int, float]:
    if max_threshold < 1:
        raise ModelIntegrityError("max_threshold must be >= 1")
    ladder = {k: probability_at_least(k, mean, dispersion) for k in range(1, max_threshold + 1)}
    prior = 1.0
    for threshold in range(1, max_threshold + 1):
        value = ladder[threshold]
        if value > prior + 1e-12:
            raise ModelIntegrityError("at-least probability ladder is not monotone")
        prior = value
    return ladder


def shrink_binomial_rate(
    successes: float,
    trials: float,
    prior_rate: float,
    prior_strength: float,
) -> float:
    if trials < 0 or successes < 0 or successes > trials:
        raise ModelIntegrityError("invalid success/trial counts")
    if not 0 <= prior_rate <= 1 or prior_strength < 0:
        raise ModelIntegrityError("invalid binomial prior")
    denom = trials + prior_strength
    if denom <= 0:
        raise ModelIntegrityError("binomial shrinkage denominator must be > 0")
    return (successes + prior_rate * prior_strength) / denom


@dataclass(frozen=True)
class PlayerShotProjection:
    player_id: str
    minutes_mean: float
    shots_per90_prior: float
    role_multiplier: float = 1.0

    def weight(self) -> float:
        if not self.player_id:
            raise ModelIntegrityError("player_id required")
        if not 0 <= self.minutes_mean <= 90:
            raise ModelIntegrityError("minutes_mean must be in [0, 90]")
        if self.shots_per90_prior < 0 or self.role_multiplier <= 0:
            raise ModelIntegrityError("invalid shot propensity")
        return self.shots_per90_prior * (self.minutes_mean / 90.0) * self.role_multiplier


def allocate_team_shots(
    team_shot_mean: float,
    players: Sequence[PlayerShotProjection],
    unmodelled_weight: float,
) -> Tuple[Dict[str, float], float]:
    """Allocate a team shot mean to player exposure weights + unmodelled bucket."""
    if team_shot_mean < 0 or unmodelled_weight < 0:
        raise ModelIntegrityError("team_shot_mean/unmodelled_weight must be nonnegative")
    ids = [p.player_id for p in players]
    if len(ids) != len(set(ids)):
        raise ModelIntegrityError("duplicate player_id in team shot allocation")
    weights = {p.player_id: p.weight() for p in players}
    denom = sum(weights.values()) + unmodelled_weight
    if denom <= 0:
        raise ModelIntegrityError("shot allocation denominator must be > 0")
    means = {player_id: team_shot_mean * weight / denom for player_id, weight in weights.items()}
    unmodelled = team_shot_mean * unmodelled_weight / denom
    audit_team_allocation(team_shot_mean, means, unmodelled)
    return means, unmodelled


def audit_team_allocation(
    team_shot_mean: float,
    player_means: Mapping[str, float],
    unmodelled_mean: float,
    tolerance: float = 1e-8,
) -> None:
    values = list(player_means.values()) + [unmodelled_mean]
    if any(value < -tolerance for value in values):
        raise ModelIntegrityError("negative allocated shot mean")
    total = sum(values)
    if abs(total - team_shot_mean) > tolerance * max(1.0, abs(team_shot_mean)):
        raise ModelIntegrityError(f"team allocation mismatch: {total} != {team_shot_mean}")


def expected_player_sot(player_shot_mean: float, p_sot_given_shot: float) -> float:
    if player_shot_mean < 0 or not 0 <= p_sot_given_shot <= 1:
        raise ModelIntegrityError("invalid SOT inputs")
    mean = player_shot_mean * p_sot_given_shot
    if mean > player_shot_mean + 1e-12:
        raise ModelIntegrityError("SOT mean exceeds shot mean")
    return mean


def expected_goalkeeper_saves(opponent_sot_mean: float, p_save_given_sot: float, goalkeeper_minutes: float) -> float:
    if opponent_sot_mean < 0 or not 0 <= p_save_given_sot <= 1:
        raise ModelIntegrityError("invalid goalkeeper save inputs")
    if not 0 <= goalkeeper_minutes <= 90:
        raise ModelIntegrityError("goalkeeper_minutes must be in [0,90]")
    return opponent_sot_mean * p_save_given_sot * (goalkeeper_minutes / 90.0)
