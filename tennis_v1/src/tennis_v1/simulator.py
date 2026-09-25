from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from math import exp, log
from random import Random
from typing import Dict, Literal, Optional

Player = Literal["A", "B"]


def _clip(p: float, lo: float = 1e-6, hi: float = 1 - 1e-6) -> float:
    return min(max(p, lo), hi)


def _logit(p: float) -> float:
    p = _clip(p)
    return log(p / (1 - p))


def _inv_logit(x: float) -> float:
    if x >= 0:
        z = exp(-x)
        return 1 / (1 + z)
    z = exp(x)
    return z / (1 + z)


def hold_probability(p: float) -> float:
    """Exact probability the server holds a standard advantage game."""
    p = _clip(p)
    q = 1 - p
    pre_deuce = p**4 * (1 + 4 * q + 10 * q**2)
    reach_deuce = 20 * (p**3) * (q**3)
    win_from_deuce = p**2 / (p**2 + q**2)
    return pre_deuce + reach_deuce * win_from_deuce


@dataclass(frozen=True)
class MatchRules:
    best_of: int
    regular_tiebreak_at: Optional[int] = 6
    regular_tiebreak_points: int = 7
    final_set_tiebreak_at: Optional[int] = 6
    final_set_tiebreak_points: int = 7

    def __post_init__(self) -> None:
        if self.best_of not in (3, 5):
            raise ValueError("best_of must be 3 or 5")
        if self.regular_tiebreak_points < 2 or self.final_set_tiebreak_points < 2:
            raise ValueError("tiebreak points must be >= 2")

    @property
    def sets_to_win(self) -> int:
        return self.best_of // 2 + 1

    def set_tiebreak_rule(self, set_number: int) -> tuple[Optional[int], int]:
        if set_number == self.best_of:
            return self.final_set_tiebreak_at, self.final_set_tiebreak_points
        return self.regular_tiebreak_at, self.regular_tiebreak_points


@dataclass(frozen=True)
class MatchInputs:
    p_a_serve_point: float
    p_b_serve_point: float
    rules: MatchRules
    p_a_logit_sd: float = 0.0
    p_b_logit_sd: float = 0.0
    initial_server: Optional[Player] = None

    def __post_init__(self) -> None:
        for name, p in (("p_a_serve_point", self.p_a_serve_point), ("p_b_serve_point", self.p_b_serve_point)):
            if not (0 < p < 1):
                raise ValueError(f"{name} must be in (0,1)")
        if self.p_a_logit_sd < 0 or self.p_b_logit_sd < 0:
            raise ValueError("logit uncertainty must be non-negative")
        if self.initial_server not in (None, "A", "B"):
            raise ValueError("initial_server must be A, B or None")


@dataclass(frozen=True)
class MatchSample:
    winner: Player
    total_games: int
    game_margin_a: int
    set_score_a: int
    set_score_b: int


@dataclass
class SimulationDistribution:
    n: int
    p_a_match: float
    total_games: Dict[int, float]
    game_margin_a: Dict[int, float]
    set_scores: Dict[str, float]

    def h2h(self, player: Player) -> float:
        return self.p_a_match if player == "A" else 1 - self.p_a_match

    def total(self, line: float, side: Literal["over", "under"]) -> dict[str, float]:
        win = push = loss = 0.0
        for games, prob in self.total_games.items():
            diff = games - line
            if side == "under":
                diff = -diff
            if diff > 0:
                win += prob
            elif diff == 0:
                push += prob
            else:
                loss += prob
        return {"win": win, "push": push, "loss": loss}

    def spread(self, player: Player, handicap: float) -> dict[str, float]:
        win = push = loss = 0.0
        for margin_a, prob in self.game_margin_a.items():
            margin = margin_a if player == "A" else -margin_a
            settled = margin + handicap
            if settled > 0:
                win += prob
            elif settled == 0:
                push += prob
            else:
                loss += prob
        return {"win": win, "push": push, "loss": loss}


class TennisMatchSimulator:
    def __init__(self, seed: int = 20260925):
        self.seed = seed

    @staticmethod
    def _other(player: Player) -> Player:
        return "B" if player == "A" else "A"

    @staticmethod
    def _draw_point_probs(inputs: MatchInputs, rng: Random) -> tuple[float, float]:
        a = inputs.p_a_serve_point
        b = inputs.p_b_serve_point
        if inputs.p_a_logit_sd:
            a = _inv_logit(rng.gauss(_logit(a), inputs.p_a_logit_sd))
        if inputs.p_b_logit_sd:
            b = _inv_logit(rng.gauss(_logit(b), inputs.p_b_logit_sd))
        return _clip(a), _clip(b)

    def _simulate_tiebreak(self, p_a: float, p_b: float, first_server: Player, target: int, rng: Random) -> Player:
        a = b = 0
        point_index = 0
        while True:
            if point_index == 0:
                server = first_server
            else:
                block = (point_index - 1) // 2
                server = self._other(first_server) if block % 2 == 0 else first_server
            p_server = p_a if server == "A" else p_b
            server_wins = rng.random() < p_server
            winner: Player = server if server_wins else self._other(server)
            if winner == "A":
                a += 1
            else:
                b += 1
            if max(a, b) >= target and abs(a - b) >= 2:
                return "A" if a > b else "B"
            point_index += 1

    def _simulate_set(self, p_a: float, p_b: float, first_server: Player, set_number: int, rules: MatchRules, rng: Random) -> tuple[Player, int, int, Player]:
        games_a = games_b = 0
        server = first_server
        tb_at, tb_points = rules.set_tiebreak_rule(set_number)

        while True:
            if tb_at is not None and games_a == tb_at and games_b == tb_at:
                winner = self._simulate_tiebreak(p_a, p_b, server, tb_points, rng)
                if winner == "A":
                    games_a += 1
                else:
                    games_b += 1
                return winner, games_a, games_b, self._other(server)

            p_hold = hold_probability(p_a if server == "A" else p_b)
            server_holds = rng.random() < p_hold
            game_winner: Player = server if server_holds else self._other(server)
            if game_winner == "A":
                games_a += 1
            else:
                games_b += 1
            server = self._other(server)

            if max(games_a, games_b) >= 6 and abs(games_a - games_b) >= 2:
                winner = "A" if games_a > games_b else "B"
                return winner, games_a, games_b, server

    def simulate_once(self, inputs: MatchInputs, rng: Random) -> MatchSample:
        p_a, p_b = self._draw_point_probs(inputs, rng)
        first_server: Player = inputs.initial_server or ("A" if rng.random() < 0.5 else "B")
        sets_a = sets_b = 0
        total_games = 0
        margin_a = 0
        set_number = 1
        next_server = first_server

        while sets_a < inputs.rules.sets_to_win and sets_b < inputs.rules.sets_to_win:
            winner, games_a, games_b, next_server = self._simulate_set(
                p_a, p_b, next_server, set_number, inputs.rules, rng
            )
            total_games += games_a + games_b
            margin_a += games_a - games_b
            if winner == "A":
                sets_a += 1
            else:
                sets_b += 1
            set_number += 1

        return MatchSample(
            winner="A" if sets_a > sets_b else "B",
            total_games=total_games,
            game_margin_a=margin_a,
            set_score_a=sets_a,
            set_score_b=sets_b,
        )

    def simulate(self, inputs: MatchInputs, n: int = 250_000) -> SimulationDistribution:
        if n < 1:
            raise ValueError("n must be positive")
        rng = Random(self.seed)
        winners = Counter()
        totals = Counter()
        margins = Counter()
        set_scores = Counter()

        for _ in range(n):
            sample = self.simulate_once(inputs, rng)
            winners[sample.winner] += 1
            totals[sample.total_games] += 1
            margins[sample.game_margin_a] += 1
            set_scores[f"{sample.set_score_a}-{sample.set_score_b}"] += 1

        return SimulationDistribution(
            n=n,
            p_a_match=winners["A"] / n,
            total_games={k: v / n for k, v in sorted(totals.items())},
            game_margin_a={k: v / n for k, v in sorted(margins.items())},
            set_scores={k: v / n for k, v in sorted(set_scores.items())},
        )


def break_even_decimal(win: float, push: float = 0.0, loss: Optional[float] = None) -> float:
    if loss is None:
        loss = max(0.0, 1 - win - push)
    if win <= 0:
        return float("inf")
    return 1 + loss / win


def expected_value_decimal(odds: float, win: float, push: float = 0.0, loss: Optional[float] = None) -> float:
    if odds <= 1:
        raise ValueError("decimal odds must be > 1")
    if loss is None:
        loss = max(0.0, 1 - win - push)
    return win * (odds - 1) - loss
