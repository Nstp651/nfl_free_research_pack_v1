"""Leakage-safe rolling QBASE builders for A-League Player Volume V1.

These builders consume already-normalized canonical rows. They do not fetch data.
Each emitted snapshot is computed before the target row is added to state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

from .model_core import ModelIntegrityError, shrink_binomial_rate


@dataclass(frozen=True)
class PlayerMatchShooting:
    fixture_id: str
    kickoff_utc: str
    season: str
    player_id: str
    team_id: str
    opponent_id: str
    minutes: float
    started: bool
    shots: int
    shots_on_target: int

    def validate(self) -> None:
        if not all([self.fixture_id, self.kickoff_utc, self.player_id, self.team_id, self.opponent_id]):
            raise ModelIntegrityError("player match identity fields are required")
        if self.minutes < 0 or self.shots < 0 or self.shots_on_target < 0:
            raise ModelIntegrityError("player match counts/minutes must be nonnegative")
        if self.shots_on_target > self.shots:
            raise ModelIntegrityError("shots_on_target cannot exceed shots")


@dataclass(frozen=True)
class GoalkeeperMatch:
    fixture_id: str
    kickoff_utc: str
    season: str
    player_id: str
    team_id: str
    opponent_id: str
    minutes: float
    shots_on_target_faced: int
    saves: int
    goals_allowed: int

    def validate(self) -> None:
        if not all([self.fixture_id, self.kickoff_utc, self.player_id, self.team_id, self.opponent_id]):
            raise ModelIntegrityError("goalkeeper match identity fields are required")
        values = [self.minutes, self.shots_on_target_faced, self.saves, self.goals_allowed]
        if any(value < 0 for value in values):
            raise ModelIntegrityError("goalkeeper counts/minutes must be nonnegative")
        if self.saves > self.shots_on_target_faced:
            raise ModelIntegrityError("saves cannot exceed shots_on_target_faced")
        if self.goals_allowed > self.shots_on_target_faced:
            raise ModelIntegrityError("goals_allowed cannot exceed shots_on_target_faced")


@dataclass(frozen=True)
class TeamMatchShooting:
    fixture_id: str
    kickoff_utc: str
    season: str
    team_id: str
    opponent_id: str
    is_home: bool
    shots_for: int
    sot_for: int
    shots_against: int
    sot_against: int

    def validate(self) -> None:
        if not all([self.fixture_id, self.kickoff_utc, self.team_id, self.opponent_id]):
            raise ModelIntegrityError("team match identity fields are required")
        values = [self.shots_for, self.sot_for, self.shots_against, self.sot_against]
        if any(value < 0 for value in values):
            raise ModelIntegrityError("team shooting counts must be nonnegative")
        if self.sot_for > self.shots_for or self.sot_against > self.shots_against:
            raise ModelIntegrityError("team SoT cannot exceed shots")


def _sorted_unique(rows, identity_key):
    validated = []
    seen = set()
    for row in rows:
        row.validate()
        key = identity_key(row)
        if key in seen:
            raise ModelIntegrityError(f"duplicate canonical row: {key}")
        seen.add(key)
        validated.append(row)
    return sorted(validated, key=lambda row: (row.kickoff_utc, row.fixture_id))


def build_player_prematch_priors(
    rows: Iterable[PlayerMatchShooting],
    league_shots_per90_prior: float = 1.6,
    shot_rate_prior_minutes: float = 450.0,
    league_sot_rate_prior: float = 0.33,
    sot_prior_shots: float = 12.0,
) -> List[Dict[str, object]]:
    """Emit one prior snapshot immediately before each player match row."""
    if league_shots_per90_prior < 0 or shot_rate_prior_minutes < 0:
        raise ModelIntegrityError("shot-rate priors must be nonnegative")
    state: Dict[str, Dict[str, float]] = {}
    output: List[Dict[str, object]] = []
    ordered = _sorted_unique(rows, lambda r: (r.fixture_id, r.player_id))
    for row in ordered:
        s = state.setdefault(row.player_id, {"minutes": 0.0, "shots": 0.0, "sot": 0.0, "matches": 0.0})
        denom_minutes = s["minutes"] + shot_rate_prior_minutes
        if denom_minutes <= 0:
            raise ModelIntegrityError("player shot prior denominator must be > 0")
        prior_shots = league_shots_per90_prior * shot_rate_prior_minutes / 90.0
        shots_per90 = (s["shots"] + prior_shots) / denom_minutes * 90.0
        p_sot = shrink_binomial_rate(s["sot"], s["shots"], league_sot_rate_prior, sot_prior_shots)
        output.append({
            "fixture_id": row.fixture_id,
            "kickoff_utc": row.kickoff_utc,
            "player_id": row.player_id,
            "history_matches": int(s["matches"]),
            "history_minutes": s["minutes"],
            "shots_per90_prior": shots_per90,
            "p_sot_given_shot_prior": p_sot,
        })
        s["minutes"] += row.minutes
        s["shots"] += row.shots
        s["sot"] += row.shots_on_target
        s["matches"] += 1
    return output


def build_keeper_prematch_priors(
    rows: Iterable[GoalkeeperMatch],
    league_save_rate_prior: float = 0.70,
    save_prior_sot: float = 20.0,
) -> List[Dict[str, object]]:
    state: Dict[str, Dict[str, float]] = {}
    output: List[Dict[str, object]] = []
    ordered = _sorted_unique(rows, lambda r: (r.fixture_id, r.player_id))
    for row in ordered:
        s = state.setdefault(row.player_id, {"sot": 0.0, "saves": 0.0, "minutes": 0.0, "matches": 0.0})
        p_save = shrink_binomial_rate(s["saves"], s["sot"], league_save_rate_prior, save_prior_sot)
        output.append({
            "fixture_id": row.fixture_id,
            "kickoff_utc": row.kickoff_utc,
            "player_id": row.player_id,
            "history_matches": int(s["matches"]),
            "history_minutes": s["minutes"],
            "p_save_given_sot_prior": p_save,
        })
        s["sot"] += row.shots_on_target_faced
        s["saves"] += row.saves
        s["minutes"] += row.minutes
        s["matches"] += 1
    return output


def build_team_prematch_priors(
    rows: Iterable[TeamMatchShooting],
    league_shots_for_prior: float = 13.0,
    league_sot_for_prior: float = 4.5,
    pseudo_matches: float = 5.0,
) -> List[Dict[str, object]]:
    if league_shots_for_prior < 0 or league_sot_for_prior < 0 or pseudo_matches <= 0:
        raise ModelIntegrityError("invalid team prior configuration")
    state: Dict[str, Dict[str, float]] = {}
    output: List[Dict[str, object]] = []
    ordered = _sorted_unique(rows, lambda r: (r.fixture_id, r.team_id))
    for row in ordered:
        s = state.setdefault(row.team_id, {
            "matches": 0.0,
            "shots_for": 0.0,
            "sot_for": 0.0,
            "shots_against": 0.0,
            "sot_against": 0.0,
        })
        denom = s["matches"] + pseudo_matches
        output.append({
            "fixture_id": row.fixture_id,
            "kickoff_utc": row.kickoff_utc,
            "team_id": row.team_id,
            "history_matches": int(s["matches"]),
            "shots_for_per90_prior": (s["shots_for"] + league_shots_for_prior * pseudo_matches) / denom,
            "sot_for_per90_prior": (s["sot_for"] + league_sot_for_prior * pseudo_matches) / denom,
            "shots_allowed_per90_prior": (s["shots_against"] + league_shots_for_prior * pseudo_matches) / denom,
            "sot_allowed_per90_prior": (s["sot_against"] + league_sot_for_prior * pseudo_matches) / denom,
        })
        s["matches"] += 1
        s["shots_for"] += row.shots_for
        s["sot_for"] += row.sot_for
        s["shots_against"] += row.shots_against
        s["sot_against"] += row.sot_against
    return output
