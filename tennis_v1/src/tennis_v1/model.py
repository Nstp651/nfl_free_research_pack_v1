from __future__ import annotations

from dataclasses import dataclass
from math import exp, log
from typing import Literal

Tour = Literal["ATP", "WTA"]
Surface = Literal["hard", "clay", "grass", "indoor_hard", "other"]


def _logit(p: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return log(p / (1 - p))


def _inv_logit(x: float) -> float:
    return 1 / (1 + exp(-x))


@dataclass(frozen=True)
class PlayerState:
    serve_logit_effect: float
    return_logit_effect: float
    serve_uncertainty: float
    return_uncertainty: float
    workload_effect: float = 0.0
    fitness_effect: float = 0.0


@dataclass(frozen=True)
class MatchContext:
    tour: Tour
    surface: Surface
    baseline_serve_point: float
    tournament_pace_logit: float = 0.0
    altitude_logit: float = 0.0
    weather_logit: float = 0.0
    surface_transition_a: float = 0.0
    surface_transition_b: float = 0.0


@dataclass(frozen=True)
class MatchupPointProbabilities:
    p_a_serve_point: float
    p_b_serve_point: float
    p_a_logit_sd: float
    p_b_logit_sd: float


def matchup_point_probabilities(a: PlayerState, b: PlayerState, ctx: MatchContext) -> MatchupPointProbabilities:
    """Combine separately estimated serve and return latent strengths."""
    base = _logit(ctx.baseline_serve_point)
    shared = ctx.tournament_pace_logit + ctx.altitude_logit + ctx.weather_logit
    eta_a = (
        base + a.serve_logit_effect - b.return_logit_effect + shared
        + a.workload_effect + a.fitness_effect + ctx.surface_transition_a
    )
    eta_b = (
        base + b.serve_logit_effect - a.return_logit_effect + shared
        + b.workload_effect + b.fitness_effect + ctx.surface_transition_b
    )
    sd_a = (a.serve_uncertainty**2 + b.return_uncertainty**2) ** 0.5
    sd_b = (b.serve_uncertainty**2 + a.return_uncertainty**2) ** 0.5
    return MatchupPointProbabilities(_inv_logit(eta_a), _inv_logit(eta_b), sd_a, sd_b)
