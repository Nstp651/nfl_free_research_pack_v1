"""Historical pre-target replay for A-League Player Volume V1.

This module has two explicit concepts that must never be conflated:

1. CONDITIONAL_DISTRIBUTION_REPLAY: uses the target fixture's realised appearance
   set only to define which player distributions are scored. All statistical
   parameters, minutes priors and team environments are computed strictly from
   earlier matches. This is suitable for distribution/dispersion calibration,
   but NOT for proving live selection edge because participant inclusion is known
   with hindsight.
2. FULL_PREMATCH_REPLAY: reserved for a future historical lineup/availability
   snapshot rail. Production economic acceptance must use that stronger mode.

The distinction is encoded in every replay receipt and fails closed if callers
try to claim full-prematch integrity without a pre-match participant source.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, Mapping, Sequence

from .backtest import CountForecastObservation
from .model_core import ModelIntegrityError
from .qbase import (
    GoalkeeperMatch,
    PlayerMatchShooting,
    TeamMatchShooting,
    build_keeper_prematch_priors,
    build_player_prematch_priors,
    build_team_prematch_priors,
)


CONDITIONAL_DISTRIBUTION_REPLAY = "CONDITIONAL_DISTRIBUTION_REPLAY"
FULL_PREMATCH_REPLAY = "FULL_PREMATCH_REPLAY"


@dataclass(frozen=True)
class ReplayConfig:
    player_minutes_prior: float = 62.0
    player_minutes_pseudo_matches: float = 2.0
    goalkeeper_minutes_prior: float = 90.0
    goalkeeper_minutes_pseudo_matches: float = 2.0
    league_shots_per90_prior: float = 1.6
    league_sot_given_shot_prior: float = 0.33
    league_team_shots_prior: float = 13.0
    league_team_sot_prior: float = 4.5
    league_save_rate_prior: float = 0.70
    team_offense_weight: float = 0.50
    unmodelled_team_shot_share: float = 0.10
    shots_dispersion: float = 3.0
    sot_dispersion: float = 3.0
    saves_dispersion: float = 4.0

    def validate(self) -> None:
        if not 0 <= self.team_offense_weight <= 1:
            raise ModelIntegrityError("team_offense_weight must be in [0,1]")
        if not 0 <= self.unmodelled_team_shot_share < 1:
            raise ModelIntegrityError("unmodelled_team_shot_share must be in [0,1)")
        positive = {
            "player_minutes_pseudo_matches": self.player_minutes_pseudo_matches,
            "goalkeeper_minutes_pseudo_matches": self.goalkeeper_minutes_pseudo_matches,
            "league_team_shots_prior": self.league_team_shots_prior,
            "shots_dispersion": self.shots_dispersion,
            "sot_dispersion": self.sot_dispersion,
            "saves_dispersion": self.saves_dispersion,
        }
        if any(value <= 0 for value in positive.values()):
            raise ModelIntegrityError(f"replay positive configuration invalid: {positive}")
        if not 0 <= self.league_sot_given_shot_prior <= 1 or not 0 <= self.league_save_rate_prior <= 1:
            raise ModelIntegrityError("replay probability priors must be in [0,1]")
        if not 0 <= self.player_minutes_prior <= 90 or not 0 <= self.goalkeeper_minutes_prior <= 90:
            raise ModelIntegrityError("replay minutes priors must be in [0,90]")


def _dt(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ModelIntegrityError(f"invalid replay kickoff {value}") from exc
    if parsed.tzinfo is None:
        raise ModelIntegrityError("replay kickoff must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _forecast_effective_time(kickoff: str) -> str:
    return (_dt(kickoff) - timedelta(seconds=1)).isoformat().replace("+00:00", "Z")


def _minute_priors(
    rows: Sequence[Any],
    *,
    identity,
    prior_minutes: float,
    pseudo_matches: float,
) -> Dict[tuple[str, str], Dict[str, float]]:
    ordered = sorted(rows, key=lambda row: (_dt(row.kickoff_utc), row.fixture_id, identity(row)))
    state: Dict[str, Dict[str, float]] = defaultdict(lambda: {"minutes": 0.0, "matches": 0.0})
    out: Dict[tuple[str, str], Dict[str, float]] = {}
    seen = set()
    for row in ordered:
        key = identity(row)
        row_key = (row.fixture_id, key)
        if row_key in seen:
            raise ModelIntegrityError(f"duplicate minute replay row {row_key}")
        seen.add(row_key)
        s = state[key]
        denom = s["matches"] + pseudo_matches
        mean = (s["minutes"] + prior_minutes * pseudo_matches) / denom
        out[row_key] = {
            "projected_minutes_mean": max(0.0, min(90.0, mean)),
            "history_matches": int(s["matches"]),
            "history_minutes": s["minutes"],
        }
        s["minutes"] += float(row.minutes)
        s["matches"] += 1
    return out


def _lookup(rows: Iterable[Mapping[str, Any]], keys: tuple[str, ...]) -> Dict[tuple[Any, ...], Mapping[str, Any]]:
    out = {}
    for row in rows:
        key = tuple(row[field] for field in keys)
        if key in out:
            raise ModelIntegrityError(f"duplicate replay prior {key}")
        out[key] = row
    return out


def generate_conditional_distribution_replay(
    player_rows: Iterable[PlayerMatchShooting],
    team_rows: Iterable[TeamMatchShooting],
    goalkeeper_rows: Iterable[GoalkeeperMatch],
    *,
    config: ReplayConfig = ReplayConfig(),
) -> Dict[str, Any]:
    """Build pre-target statistical forecasts conditional on realised participants.

    No target match count or target minutes enters any mean. The only hindsight
    information is membership of the target appearance set, which is why this
    output may calibrate distributions but cannot satisfy the full selection-edge
    acceptance gate.
    """
    config.validate()
    players = list(player_rows)
    teams = list(team_rows)
    keepers = list(goalkeeper_rows)
    for row in players + teams + keepers:
        row.validate()

    player_prior = _lookup(
        build_player_prematch_priors(
            players,
            league_shots_per90_prior=config.league_shots_per90_prior,
            league_sot_rate_prior=config.league_sot_given_shot_prior,
        ),
        ("fixture_id", "player_id"),
    )
    team_prior = _lookup(
        build_team_prematch_priors(
            teams,
            league_shots_for_prior=config.league_team_shots_prior,
            league_sot_for_prior=config.league_team_sot_prior,
        ),
        ("fixture_id", "team_id"),
    )
    keeper_prior = _lookup(
        build_keeper_prematch_priors(
            keepers,
            league_save_rate_prior=config.league_save_rate_prior,
        ),
        ("fixture_id", "player_id"),
    )
    player_minutes = _minute_priors(
        players,
        identity=lambda r: r.player_id,
        prior_minutes=config.player_minutes_prior,
        pseudo_matches=config.player_minutes_pseudo_matches,
    )
    keeper_minutes = _minute_priors(
        keepers,
        identity=lambda r: r.player_id,
        prior_minutes=config.goalkeeper_minutes_prior,
        pseudo_matches=config.goalkeeper_minutes_pseudo_matches,
    )

    team_rows_by_fixture: Dict[str, Dict[str, TeamMatchShooting]] = defaultdict(dict)
    for row in teams:
        if row.team_id in team_rows_by_fixture[row.fixture_id]:
            raise ModelIntegrityError(f"duplicate team row in fixture {row.fixture_id}: {row.team_id}")
        team_rows_by_fixture[row.fixture_id][row.team_id] = row

    player_rows_by_fixture_team: Dict[tuple[str, str], list[PlayerMatchShooting]] = defaultdict(list)
    for row in players:
        player_rows_by_fixture_team[(row.fixture_id, row.team_id)].append(row)

    team_environment: Dict[tuple[str, str], Dict[str, float]] = {}
    player_means: Dict[tuple[str, str], Dict[str, float]] = {}
    for fixture_id, fixture_teams in sorted(
        team_rows_by_fixture.items(),
        key=lambda item: min(_dt(row.kickoff_utc) for row in item[1].values()),
    ):
        if len(fixture_teams) != 2:
            raise ModelIntegrityError(f"replay fixture {fixture_id} requires exactly two team rows")
        for team_id, target in fixture_teams.items():
            opponent_id = target.opponent_id
            own = team_prior.get((fixture_id, team_id))
            opponent = team_prior.get((fixture_id, opponent_id))
            if own is None or opponent is None:
                raise ModelIntegrityError(f"team prior missing for replay fixture {fixture_id}")
            shot_mean = (
                config.team_offense_weight * float(own["shots_for_per90_prior"])
                + (1.0 - config.team_offense_weight) * float(opponent["shots_allowed_per90_prior"])
            )
            candidates = player_rows_by_fixture_team.get((fixture_id, team_id), [])
            weights: Dict[str, float] = {}
            for target_player in candidates:
                prior = player_prior[(fixture_id, target_player.player_id)]
                minutes = player_minutes[(fixture_id, target_player.player_id)]["projected_minutes_mean"]
                weights[target_player.player_id] = max(0.0, float(prior["shots_per90_prior"]) * minutes / 90.0)
            total_weight = sum(weights.values())
            modeled_shots = shot_mean * (1.0 - config.unmodelled_team_shot_share)
            modeled_sot = 0.0
            if candidates and total_weight <= 0:
                raise ModelIntegrityError(f"zero player allocation weight in {fixture_id}/{team_id}")
            for target_player in candidates:
                prior = player_prior[(fixture_id, target_player.player_id)]
                minutes_info = player_minutes[(fixture_id, target_player.player_id)]
                mu_shots = modeled_shots * weights[target_player.player_id] / total_weight if total_weight else 0.0
                p_sot = float(prior["p_sot_given_shot_prior"])
                mu_sot = mu_shots * p_sot
                modeled_sot += mu_sot
                player_means[(fixture_id, target_player.player_id)] = {
                    "shots": mu_shots,
                    "sot": mu_sot,
                    "projected_minutes_mean": minutes_info["projected_minutes_mean"],
                    "history_matches": int(prior["history_matches"]),
                    "shots_per90_prior": float(prior["shots_per90_prior"]),
                    "p_sot_given_shot_prior": p_sot,
                }
            unmodelled_shots = shot_mean * config.unmodelled_team_shot_share
            unmodelled_sot = unmodelled_shots * config.league_sot_given_shot_prior
            team_environment[(fixture_id, team_id)] = {
                "shots_mean": shot_mean,
                "sot_mean": modeled_sot + unmodelled_sot,
                "unmodelled_shots_mean": unmodelled_shots,
                "unmodelled_sot_mean": unmodelled_sot,
            }

    observations: list[CountForecastObservation] = []
    for row in sorted(players, key=lambda r: (_dt(r.kickoff_utc), r.fixture_id, r.player_id)):
        means = player_means[(row.fixture_id, row.player_id)]
        effective = _forecast_effective_time(row.kickoff_utc)
        baseline_shots = config.league_shots_per90_prior * means["projected_minutes_mean"] / 90.0
        observations.append(CountForecastObservation(
            fixture_id=row.fixture_id,
            kickoff_utc=row.kickoff_utc,
            forecast_created_utc=effective,
            player_id=row.player_id,
            head="SHOTS",
            mean=means["shots"],
            dispersion=config.shots_dispersion,
            actual_count=int(row.shots),
            baseline_mean=baseline_shots,
            source_run_id=f"conditional-replay:{row.fixture_id}",
        ))
        observations.append(CountForecastObservation(
            fixture_id=row.fixture_id,
            kickoff_utc=row.kickoff_utc,
            forecast_created_utc=effective,
            player_id=row.player_id,
            head="SOT",
            mean=means["sot"],
            dispersion=config.sot_dispersion,
            actual_count=int(row.shots_on_target),
            baseline_mean=baseline_shots * config.league_sot_given_shot_prior,
            source_run_id=f"conditional-replay:{row.fixture_id}",
        ))

    for row in sorted(keepers, key=lambda r: (_dt(r.kickoff_utc), r.fixture_id, r.player_id)):
        prior = keeper_prior[(row.fixture_id, row.player_id)]
        minutes = keeper_minutes[(row.fixture_id, row.player_id)]["projected_minutes_mean"]
        opponent = team_environment.get((row.fixture_id, row.opponent_id))
        if opponent is None:
            raise ModelIntegrityError(f"opponent team SOT environment missing for keeper {row.player_id}")
        mean = float(opponent["sot_mean"]) * float(prior["p_save_given_sot_prior"]) * minutes / 90.0
        baseline = config.league_team_sot_prior * config.league_save_rate_prior * minutes / 90.0
        observations.append(CountForecastObservation(
            fixture_id=row.fixture_id,
            kickoff_utc=row.kickoff_utc,
            forecast_created_utc=_forecast_effective_time(row.kickoff_utc),
            player_id=row.player_id,
            head="SAVES",
            mean=mean,
            dispersion=config.saves_dispersion,
            actual_count=int(row.saves),
            baseline_mean=baseline,
            source_run_id=f"conditional-replay:{row.fixture_id}",
        ))

    return {
        "schema_version": "aleague_player_volume_conditional_replay_v1",
        "replay_mode": CONDITIONAL_DISTRIBUTION_REPLAY,
        "market_data_used": False,
        "selection_integrity": "INSUFFICIENT_FOR_PRODUCTION_EDGE_ACCEPTANCE",
        "participant_set_source": "TARGET_FIXTURE_REALIZED_APPEARANCE_SET",
        "parameter_information_cutoff": "STRICTLY_BEFORE_TARGET_FIXTURE",
        "forecast_timestamp_semantics": "REPLAY_EFFECTIVE_TIME_NOT_PERSISTED_LIVE",
        "allowed_uses": ["DISTRIBUTION_CALIBRATION", "DISPERSION_SELECTION_TRAIN_ONLY", "MODEL_DIAGNOSTICS"],
        "prohibited_uses": ["PRODUCTION_EDGE_CLAIM", "SELECTION_HIT_RATE_CLAIM", "PRODUCTION_READY_GATE"],
        "observations": observations,
        "team_environment": team_environment,
        "player_means": player_means,
    }


def require_full_prematch_replay(replay: Mapping[str, Any]) -> Mapping[str, Any]:
    """Production acceptance helper: fail closed on conditional replay artifacts."""
    if replay.get("replay_mode") != FULL_PREMATCH_REPLAY:
        raise ModelIntegrityError("production edge acceptance requires FULL_PREMATCH_REPLAY")
    if replay.get("participant_set_source") not in {"PERSISTED_PREMATCH_LINEUP_SNAPSHOT", "PERSISTED_PREMATCH_RESEARCH_SNAPSHOT"}:
        raise ModelIntegrityError("full replay requires persisted pre-match participant source")
    if replay.get("selection_integrity") != "FULL_PREMATCH":
        raise ModelIntegrityError("full replay selection integrity invalid")
    return replay
