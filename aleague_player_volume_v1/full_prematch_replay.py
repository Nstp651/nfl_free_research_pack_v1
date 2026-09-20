"""Snapshot-driven historical replay with a genuine pre-match participant set.

This is stronger than conditional replay because participant inclusion and minutes
come from a persisted snapshot captured before kickoff. It still uses neutral
role multipliers unless a persisted historical model-input snapshot is supplied,
so it is intentionally NOT sufficient to prove the final V1 production edge.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, Iterable

from .backtest import CountForecastObservation
from .historical_replay import ReplayConfig
from .model_core import (
    ModelIntegrityError,
    PlayerShotProjection,
    allocate_team_shots,
    expected_goalkeeper_saves,
    expected_player_sot,
    shrink_binomial_rate,
)
from .prematch_snapshot import PrematchSnapshot, validate_snapshot_series
from .qbase import GoalkeeperMatch, PlayerMatchShooting, TeamMatchShooting


def _dt(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ModelIntegrityError(f"invalid replay timestamp {value}") from exc
    if parsed.tzinfo is None:
        raise ModelIntegrityError("replay timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _player_prior(
    player_id: str,
    cutoff: datetime,
    rows: list[PlayerMatchShooting],
    config: ReplayConfig,
) -> Dict[str, float]:
    history = [row for row in rows if row.player_id == player_id and _dt(row.kickoff_utc) < cutoff]
    minutes = sum(float(row.minutes) for row in history)
    shots = sum(int(row.shots) for row in history)
    sot = sum(int(row.shots_on_target) for row in history)
    prior_minutes = 450.0
    denom = minutes + prior_minutes
    shots_per90 = (shots + config.league_shots_per90_prior * prior_minutes / 90.0) / denom * 90.0
    p_sot = shrink_binomial_rate(sot, shots, config.league_sot_given_shot_prior, 12.0)
    return {
        "history_matches": float(len(history)),
        "history_minutes": minutes,
        "shots_per90_prior": shots_per90,
        "p_sot_given_shot_prior": p_sot,
    }


def _team_prior(
    team_id: str,
    cutoff: datetime,
    rows: list[TeamMatchShooting],
    config: ReplayConfig,
) -> Dict[str, float]:
    history = [row for row in rows if row.team_id == team_id and _dt(row.kickoff_utc) < cutoff]
    pseudo = 5.0
    denom = len(history) + pseudo
    return {
        "history_matches": float(len(history)),
        "shots_for": (sum(row.shots_for for row in history) + config.league_team_shots_prior * pseudo) / denom,
        "sot_for": (sum(row.sot_for for row in history) + config.league_team_sot_prior * pseudo) / denom,
        "shots_allowed": (sum(row.shots_against for row in history) + config.league_team_shots_prior * pseudo) / denom,
        "sot_allowed": (sum(row.sot_against for row in history) + config.league_team_sot_prior * pseudo) / denom,
    }


def _keeper_prior(
    player_id: str,
    cutoff: datetime,
    rows: list[GoalkeeperMatch],
    config: ReplayConfig,
) -> Dict[str, float]:
    history = [row for row in rows if row.player_id == player_id and _dt(row.kickoff_utc) < cutoff]
    faced = sum(row.shots_on_target_faced for row in history)
    saves = sum(row.saves for row in history)
    return {
        "history_matches": float(len(history)),
        "history_minutes": sum(float(row.minutes) for row in history),
        "p_save_given_sot_prior": shrink_binomial_rate(saves, faced, config.league_save_rate_prior, 20.0),
    }


def generate_snapshot_participant_replay(
    snapshots: Iterable[PrematchSnapshot],
    player_rows: Iterable[PlayerMatchShooting],
    team_rows: Iterable[TeamMatchShooting],
    goalkeeper_rows: Iterable[GoalkeeperMatch],
    *,
    config: ReplayConfig = ReplayConfig(),
) -> Dict[str, Any]:
    """Replay historical distributions using only persisted pre-match participants.

    Selected participants who did not record a provider appearance are recorded as
    void/unsettled and are never converted into zero-count losses. This mirrors the
    economic reality that player props normally void when a player does not play.
    """
    config.validate()
    snapshot_list = validate_snapshot_series(snapshots)
    players = list(player_rows)
    teams = list(team_rows)
    keepers = list(goalkeeper_rows)
    for row in players + teams + keepers:
        row.validate()

    target_team_rows: Dict[str, Dict[str, TeamMatchShooting]] = defaultdict(dict)
    for row in teams:
        if row.team_id in target_team_rows[row.fixture_id]:
            raise ModelIntegrityError(f"duplicate team target row {row.fixture_id}/{row.team_id}")
        target_team_rows[row.fixture_id][row.team_id] = row
    actual_players = {(row.fixture_id, row.player_id): row for row in players}
    actual_keepers = {(row.fixture_id, row.player_id): row for row in keepers}

    observations: list[CountForecastObservation] = []
    fixture_receipts: list[Dict[str, Any]] = []
    void_participants: list[Dict[str, Any]] = []
    selected_participants = 0

    for snapshot in snapshot_list:
        cutoff = _dt(snapshot.kickoff_utc)
        fixture_teams = target_team_rows.get(snapshot.fixture_id)
        if not fixture_teams or set(fixture_teams) != {snapshot.home_team_id, snapshot.away_team_id}:
            raise ModelIntegrityError(f"target team identity missing/mismatched for snapshot {snapshot.fixture_id}")
        if any(_dt(row.kickoff_utc) != cutoff for row in fixture_teams.values()):
            raise ModelIntegrityError(f"target kickoff mismatch for snapshot {snapshot.fixture_id}")

        team_priors = {
            team_id: _team_prior(team_id, cutoff, teams, config)
            for team_id in (snapshot.home_team_id, snapshot.away_team_id)
        }
        team_shot_means: Dict[str, float] = {}
        for team_id in (snapshot.home_team_id, snapshot.away_team_id):
            opponent_id = snapshot.away_team_id if team_id == snapshot.home_team_id else snapshot.home_team_id
            team_shot_means[team_id] = (
                config.team_offense_weight * team_priors[team_id]["shots_for"]
                + (1.0 - config.team_offense_weight) * team_priors[opponent_id]["shots_allowed"]
            )

        team_sot_means: Dict[str, float] = {}
        player_projection_receipts: list[Dict[str, Any]] = []
        for team_id in (snapshot.home_team_id, snapshot.away_team_id):
            eligible = [
                participant
                for participant in snapshot.participants
                if participant.team_id == team_id
                and participant.player_type == "OUTFIELD"
                and participant.status != "OUT"
                and participant.minutes_mean > 0
            ]
            if not eligible:
                raise ModelIntegrityError(f"snapshot {snapshot.fixture_id} has no modeled outfield players for {team_id}")
            priors = {participant.player_id: _player_prior(participant.player_id, cutoff, players, config) for participant in eligible}
            projections = [
                PlayerShotProjection(
                    player_id=participant.player_id,
                    minutes_mean=participant.minutes_mean,
                    shots_per90_prior=priors[participant.player_id]["shots_per90_prior"],
                    role_multiplier=1.0,
                )
                for participant in eligible
            ]
            modeled_weight = sum(projection.shot_propensity_weight for projection in projections)
            if modeled_weight <= 0:
                raise ModelIntegrityError(f"snapshot {snapshot.fixture_id}/{team_id} has zero modeled shot weight")
            unmodelled_weight = modeled_weight * config.unmodelled_team_shot_share / (1.0 - config.unmodelled_team_shot_share)
            shot_means, unmodelled_shots = allocate_team_shots(team_shot_means[team_id], projections, unmodelled_weight)
            team_sot = unmodelled_shots * config.league_sot_given_shot_prior
            for participant in eligible:
                selected_participants += 1
                prior = priors[participant.player_id]
                mean_shots = shot_means[participant.player_id]
                mean_sot = expected_player_sot(mean_shots, prior["p_sot_given_shot_prior"])
                team_sot += mean_sot
                actual = actual_players.get((snapshot.fixture_id, participant.player_id))
                player_projection_receipts.append({
                    "player_id": participant.player_id,
                    "team_id": team_id,
                    "projected_minutes_mean": participant.minutes_mean,
                    "history_matches": int(prior["history_matches"]),
                    "shots_per90_prior": prior["shots_per90_prior"],
                    "p_sot_given_shot_prior": prior["p_sot_given_shot_prior"],
                    "role_multiplier": 1.0,
                    "shot_mean": mean_shots,
                    "sot_mean": mean_sot,
                    "settled": actual is not None,
                })
                if actual is None:
                    void_participants.append({
                        "fixture_id": snapshot.fixture_id,
                        "player_id": participant.player_id,
                        "player_name": participant.player_name,
                        "stat_heads": ["SHOTS", "SOT"],
                        "reason": "NO_PROVIDER_APPEARANCE_ROW_VOID_NOT_SCORED",
                    })
                    continue
                baseline_shots = config.league_shots_per90_prior * participant.minutes_mean / 90.0
                observations.extend([
                    CountForecastObservation(
                        fixture_id=snapshot.fixture_id,
                        kickoff_utc=snapshot.kickoff_utc,
                        forecast_created_utc=snapshot.captured_at_utc,
                        player_id=participant.player_id,
                        head="SHOTS",
                        mean=mean_shots,
                        dispersion=config.shots_dispersion,
                        actual_count=int(actual.shots),
                        baseline_mean=baseline_shots,
                        source_run_id=f"snapshot-replay:{snapshot.fixture_id}",
                    ),
                    CountForecastObservation(
                        fixture_id=snapshot.fixture_id,
                        kickoff_utc=snapshot.kickoff_utc,
                        forecast_created_utc=snapshot.captured_at_utc,
                        player_id=participant.player_id,
                        head="SOT",
                        mean=mean_sot,
                        dispersion=config.sot_dispersion,
                        actual_count=int(actual.shots_on_target),
                        baseline_mean=baseline_shots * config.league_sot_given_shot_prior,
                        source_run_id=f"snapshot-replay:{snapshot.fixture_id}",
                    ),
                ])
            team_sot_means[team_id] = team_sot

        keeper_projection_receipts: list[Dict[str, Any]] = []
        for team_id in (snapshot.home_team_id, snapshot.away_team_id):
            opponent_id = snapshot.away_team_id if team_id == snapshot.home_team_id else snapshot.home_team_id
            candidates = sorted(
                [
                    participant
                    for participant in snapshot.participants
                    if participant.team_id == team_id
                    and participant.player_type == "GOALKEEPER"
                    and participant.status != "OUT"
                    and participant.minutes_mean > 0
                ],
                key=lambda participant: (-participant.minutes_mean, participant.player_id),
            )
            if not candidates:
                raise ModelIntegrityError(f"snapshot {snapshot.fixture_id} has no goalkeeper for {team_id}")
            keeper = candidates[0]
            selected_participants += 1
            prior = _keeper_prior(keeper.player_id, cutoff, keepers, config)
            mean = expected_goalkeeper_saves(
                team_sot_means[opponent_id],
                prior["p_save_given_sot_prior"],
                keeper.minutes_mean,
            )
            actual = actual_keepers.get((snapshot.fixture_id, keeper.player_id))
            keeper_projection_receipts.append({
                "player_id": keeper.player_id,
                "team_id": team_id,
                "projected_minutes_mean": keeper.minutes_mean,
                "history_matches": int(prior["history_matches"]),
                "p_save_given_sot_prior": prior["p_save_given_sot_prior"],
                "opponent_sot_mean": team_sot_means[opponent_id],
                "save_mean": mean,
                "settled": actual is not None,
            })
            if actual is None:
                void_participants.append({
                    "fixture_id": snapshot.fixture_id,
                    "player_id": keeper.player_id,
                    "player_name": keeper.player_name,
                    "stat_heads": ["SAVES"],
                    "reason": "NO_PROVIDER_APPEARANCE_ROW_VOID_NOT_SCORED",
                })
                continue
            baseline = config.league_team_sot_prior * config.league_save_rate_prior * keeper.minutes_mean / 90.0
            observations.append(CountForecastObservation(
                fixture_id=snapshot.fixture_id,
                kickoff_utc=snapshot.kickoff_utc,
                forecast_created_utc=snapshot.captured_at_utc,
                player_id=keeper.player_id,
                head="SAVES",
                mean=mean,
                dispersion=config.saves_dispersion,
                actual_count=int(actual.saves),
                baseline_mean=baseline,
                source_run_id=f"snapshot-replay:{snapshot.fixture_id}",
            ))

        fixture_receipts.append({
            "fixture_id": snapshot.fixture_id,
            "snapshot_receipt_sha256": snapshot.to_dict()["snapshot_receipt_sha256"],
            "captured_at_utc": snapshot.captured_at_utc,
            "team_shot_means": team_shot_means,
            "team_sot_means": team_sot_means,
            "player_projections": player_projection_receipts,
            "goalkeeper_projections": keeper_projection_receipts,
        })

    for observation in observations:
        observation.validate()
    return {
        "schema_version": "aleague_player_volume_snapshot_participant_replay_v1",
        "replay_mode": "FULL_PREMATCH_PARTICIPANT_SET_REPLAY",
        "market_data_used": False,
        "selection_integrity": "FULL_PREMATCH_PARTICIPANT_SET_ONLY",
        "participant_set_source": "PERSISTED_PREMATCH_SNAPSHOT",
        "model_input_integrity": "ROLLING_QBASE_PLUS_NEUTRAL_ROLE_MULTIPLIERS",
        "role_adjustment_source": "NEUTRAL_1_0_NOT_PERSISTED_HISTORICAL_RESEARCH",
        "production_edge_acceptance": "BLOCKED_REQUIRES_PERSISTED_PREMATCH_MODEL_INPUTS",
        "allowed_uses": [
            "PARTICIPANT_SELECTION_REPLAY",
            "MINUTES_SNAPSHOT_DIAGNOSTICS",
            "DISTRIBUTION_CALIBRATION",
            "MODEL_PIPELINE_DIAGNOSTICS",
        ],
        "prohibited_uses": ["FINAL_V1_PRODUCTION_EDGE_CLAIM", "PRODUCTION_READY_GATE"],
        "selected_participants": selected_participants,
        "settled_forecast_observations": len(observations),
        "void_participants": void_participants,
        "fixture_receipts": fixture_receipts,
        "observations": observations,
    }
