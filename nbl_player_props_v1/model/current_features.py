#!/usr/bin/env python3
"""Assemble exact next-fixture QBASE features from compact NBL history priors."""
from __future__ import annotations

import math
import re
import unicodedata
from datetime import datetime
from typing import Any


class PriorTranslationRequired(ValueError):
    """Raised when a player has no usable NBL history for direct QBASE scoring."""


class TeamPriorMissing(ValueError):
    """Raised when own/opponent team context cannot be constructed."""


def norm_name(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "", text)


def _dt(value: Any, field: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} required")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include timezone")
    return parsed


def _days_between(target: str, previous: Any) -> float | None:
    if previous is None:
        return None
    days = (_dt(target, "target_time") - _dt(previous, "previous_time")).total_seconds() / 86400.0
    if not math.isfinite(days) or days < 0:
        raise ValueError("target fixture precedes historical prior timestamp")
    return days


def _find_player(snapshot: dict[str, Any], player_name: str, player_id: str | None = None) -> dict[str, Any]:
    players = snapshot.get("players")
    if not isinstance(players, dict):
        raise ValueError("prior snapshot players map missing")
    pid = str(player_id or "").strip()
    if pid:
        matches = [v for v in players.values() if isinstance(v, dict) and pid in {str(x) for x in v.get("source_player_ids", [])}]
        if len(matches) > 1:
            raise ValueError(f"Historical player ID {pid} maps to multiple priors")
        if len(matches) == 1:
            return matches[0]
    key = norm_name(player_name)
    direct = players.get(key)
    if isinstance(direct, dict):
        return direct
    matches = [v for k, v in players.items() if norm_name(k) == key and isinstance(v, dict)]
    if len(matches) == 1:
        return matches[0]
    raise PriorTranslationRequired(f"No NBL historical prior for {player_name}; prior-competition translation required")


def _find_team(snapshot: dict[str, Any], team_name: str) -> dict[str, Any]:
    teams = snapshot.get("teams")
    if not isinstance(teams, dict):
        raise ValueError("prior snapshot teams map missing")
    wanted = norm_name(team_name)
    matches = [v for k, v in teams.items() if norm_name(k) == wanted and isinstance(v, dict)]
    if len(matches) != 1:
        raise TeamPriorMissing(f"Expected one historical team prior for {team_name}, found {len(matches)}")
    return matches[0]


def _season_games(record: dict[str, Any], target_season_start: int, key: str) -> float:
    try:
        last = int(record.get("last_season_start"))
    except (TypeError, ValueError):
        return 0.0
    if last != int(target_season_start):
        return 0.0
    try:
        return float(record["features"][key])
    except (KeyError, TypeError, ValueError):
        return 0.0


def _copy_if(values: dict[str, Any], target: str, source: dict[str, Any], source_key: str | None = None) -> None:
    value = source.get(source_key or target)
    if value is None:
        return
    try:
        number = float(value)
    except (TypeError, ValueError):
        return
    if math.isfinite(number):
        values[target] = number


def assemble_feature_vector(
    qbase_artifact: dict[str, Any], prior_snapshot: dict[str, Any], *, player_name: str,
    team: str, opponent: str, target_season_start: int, target_time: str,
    home_flag: bool | int | float, player_id: str | None = None,
) -> dict[str, Any]:
    if prior_snapshot.get("market_data") is not False:
        raise ValueError("prior snapshot must declare market_data=false")
    selected = qbase_artifact.get("selected_model")
    if not isinstance(selected, dict) or not isinstance(selected.get("features"), list):
        raise ValueError("QBASE serialized feature list missing")
    required = [str(x) for x in selected["features"]]
    player = _find_player(prior_snapshot, player_name, player_id); own = _find_team(prior_snapshot, team); opp = _find_team(prior_snapshot, opponent)
    pf, tf, of, values = player.get("features") or {}, own.get("features") or {}, opp.get("features") or {}, {}

    for key in required:
        if key.startswith("player_") and key not in {"player_season_games_prior", "player_days_rest"}:
            _copy_if(values, key, pf)
    values["player_season_games_prior"] = _season_games(player, target_season_start, "player_last_season_games")
    rest = _days_between(target_time, player.get("last_match_time"))
    if rest is not None: values["player_days_rest"] = rest

    own_direct = {"team_games_prior", "team_points_mean_5", "team_points_mean_10", "team_possessions_mean_5", "team_possessions_mean_10", "team_assists_mean_5", "team_assists_mean_10", "team_fgm_mean_5", "team_fgm_mean_10", "team_rebounds_mean_5", "team_rebounds_mean_10", "team_missed_fg_mean_5", "team_missed_fg_mean_10"}
    for key in required:
        if key in own_direct: _copy_if(values, key, tf)
    values["team_season_games_prior"] = _season_games(own, target_season_start, "team_last_season_games")
    rest = _days_between(target_time, own.get("last_match_time"))
    if rest is not None: values["team_days_rest"] = rest

    opponent_map = {
        "opponent_points_allowed_mean_5": "points_allowed_mean_5", "opponent_points_allowed_mean_10": "points_allowed_mean_10",
        "opponent_possessions_mean_5": "team_possessions_mean_5", "opponent_possessions_mean_10": "team_possessions_mean_10",
        "opponent_assists_allowed_mean_5": "assists_allowed_mean_5", "opponent_assists_allowed_mean_10": "assists_allowed_mean_10",
        "opponent_fgm_allowed_mean_5": "fgm_allowed_mean_5", "opponent_fgm_allowed_mean_10": "fgm_allowed_mean_10",
        "opponent_missed_fg_mean_5": "team_missed_fg_mean_5", "opponent_missed_fg_mean_10": "team_missed_fg_mean_10",
        "opponent_rebounds_allowed_mean_5": "rebounds_allowed_mean_5", "opponent_rebounds_allowed_mean_10": "rebounds_allowed_mean_10",
    }
    for target, source in opponent_map.items():
        if target in required: _copy_if(values, target, of, source)
    rest = _days_between(target_time, opp.get("last_match_time"))
    if rest is not None: values["opponent_days_rest"] = rest

    try: hf = float(home_flag)
    except (TypeError, ValueError) as exc: raise ValueError("home_flag must be boolean/0/1") from exc
    if hf not in {0.0, 1.0}: raise ValueError("home_flag must be 0 or 1")
    values["home_flag"] = hf
    exact = {name: values[name] for name in required if name in values}
    return {
        "features": exact, "missing_features": [name for name in required if name not in exact],
        "player_prior_key": str(player.get("player_key") or norm_name(player_name)),
        "player_source_player_ids": [str(x) for x in player.get("source_player_ids", [])], "player_last_team": player.get("last_team"),
        "player_last_match_time": player.get("last_match_time"), "own_team_last_match_time": own.get("last_match_time"),
        "opponent_last_match_time": opp.get("last_match_time"), "target_season_start": int(target_season_start),
        "target_time": target_time, "snapshot_revision": prior_snapshot.get("snapshot_revision"),
    }
