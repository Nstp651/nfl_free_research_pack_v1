"""Market-blind current-research contract for A-League Player Volume V1."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict
from urllib.parse import urlparse

from .model_core import assert_market_blind


SCHEMA_VERSION = "aleague_player_volume_research_v1"
VALID_RUN_MODES = {"ALL", "SHOOTING_ONLY", "SAVES_ONLY"}
VALID_AVAILABILITY = {"ACTIVE", "PROBABLE", "QUESTIONABLE", "DOUBTFUL", "OUT", "UNKNOWN"}
VALID_ROLE_STATES = {"RETURNING_SAME", "RETURNING_CHANGED", "NEW_TO_TEAM", "NEW_TO_ALEAGUE", "ROOKIE", "UNKNOWN"}
VALID_ROLES = {"CF", "WIDE_FORWARD", "AM", "CM", "WING_BACK", "FULL_BACK", "CB", "GK", "OTHER", "UNKNOWN"}
VALID_PLAYER_TYPES = {"OUTFIELD", "GOALKEEPER"}


def _iso8601(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} required")
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be ISO-8601") from exc
    return text


def _https(value: Any, field: str) -> str:
    text = str(value or "").strip()
    parsed = urlparse(text)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"{field} must be an absolute HTTPS URL")
    return text


def _source_ids(value: Any, known: set[str], field: str, *, required: bool = True) -> list[str]:
    if value is None:
        ids: list[str] = []
    elif isinstance(value, list):
        ids = [str(x).strip() for x in value if str(x).strip()]
    else:
        raise ValueError(f"{field} must be a list")
    if required and not ids:
        raise ValueError(f"{field} requires at least one source id")
    unknown = sorted(set(ids) - known)
    if unknown:
        raise ValueError(f"{field} contains unknown source ids {unknown}")
    return ids


def _notes(value: Any, field: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    notes = [str(x).strip() for x in value if str(x).strip()]
    if not notes:
        raise ValueError(f"{field} requires at least one note")
    return notes


def player_key(row: Dict[str, Any]) -> str:
    player_id = str(row.get("player_id") or "").strip()
    if player_id:
        return "id:" + player_id
    name = re.sub(r"[^a-z0-9]+", "", str(row.get("player_name") or "").lower())
    if not name:
        raise ValueError("player_id or player_name required")
    return "name:" + name


def validate_research_context(context: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(context, dict):
        raise ValueError("research context must be an object")
    if context.get("market_data") is not False:
        raise ValueError("research context must declare market_data=false")
    assert_market_blind(context)
    if context.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
    run_mode = str(context.get("run_mode") or "").upper()
    if run_mode not in VALID_RUN_MODES:
        raise ValueError(f"unsupported run_mode {run_mode}")
    if not str(context.get("fixture_id") or "").strip():
        raise ValueError("fixture_id required")
    if not str(context.get("pack_revision") or "").strip():
        raise ValueError("pack_revision required")
    _iso8601(context.get("checked_at"), "checked_at")

    sources = context.get("sources")
    if not isinstance(sources, dict) or not sources:
        raise ValueError("sources must be a non-empty object")
    known_sources: set[str] = set()
    for source_id, source in sources.items():
        source_id = str(source_id).strip()
        if not source_id or not isinstance(source, dict):
            raise ValueError("invalid source entry")
        known_sources.add(source_id)
        _https(source.get("url"), f"sources.{source_id}.url")
        _iso8601(source.get("checked_at"), f"sources.{source_id}.checked_at")
        if not str(source.get("title") or "").strip():
            raise ValueError(f"sources.{source_id}.title required")

    fixture = context.get("fixture_context")
    if not isinstance(fixture, dict):
        raise ValueError("fixture_context required")
    home_team_id = str(fixture.get("home_team_id") or "").strip()
    away_team_id = str(fixture.get("away_team_id") or "").strip()
    if not home_team_id or not away_team_id or home_team_id == away_team_id:
        raise ValueError("fixture_context requires distinct home/away team ids")
    _iso8601(fixture.get("kickoff_utc"), "fixture_context.kickoff_utc")
    _source_ids(fixture.get("source_ids"), known_sources, "fixture_context.source_ids")
    if not str(fixture.get("status") or "").strip():
        raise ValueError("fixture_context.status required")

    teams = context.get("teams")
    if not isinstance(teams, list) or len(teams) != 2:
        raise ValueError("teams must contain exactly two entries")
    expected_team_ids = {home_team_id, away_team_id}
    seen_teams = set()
    for idx, team in enumerate(teams):
        if not isinstance(team, dict):
            raise ValueError(f"teams[{idx}] must be an object")
        team_id = str(team.get("team_id") or "").strip()
        if team_id not in expected_team_ids or team_id in seen_teams:
            raise ValueError(f"teams[{idx}].team_id invalid/duplicate")
        seen_teams.add(team_id)
        if not str(team.get("team_name") or "").strip():
            raise ValueError(f"teams[{idx}].team_name required")
        _source_ids(team.get("source_ids"), known_sources, f"teams[{idx}].source_ids")
        _notes(team.get("notes"), f"teams[{idx}].notes")

    players = context.get("players")
    if not isinstance(players, list) or not players:
        raise ValueError("players must be a non-empty list")
    seen_players = set()
    goalkeeper_teams = set()
    for idx, row in enumerate(players):
        if not isinstance(row, dict):
            raise ValueError(f"players[{idx}] must be an object")
        key = player_key(row)
        if key in seen_players:
            raise ValueError(f"duplicate research player {key}")
        seen_players.add(key)
        team_id = str(row.get("team_id") or "").strip()
        if team_id not in expected_team_ids:
            raise ValueError(f"players[{idx}].team_id invalid")
        if not str(row.get("player_name") or "").strip():
            raise ValueError(f"players[{idx}].player_name required")
        player_type = str(row.get("player_type") or "").upper()
        if player_type not in VALID_PLAYER_TYPES:
            raise ValueError(f"players[{idx}].player_type invalid")
        availability = str(row.get("availability_status") or "").upper()
        if availability not in VALID_AVAILABILITY:
            raise ValueError(f"players[{idx}].availability_status invalid")
        _source_ids(row.get("availability_source_ids"), known_sources, f"players[{idx}].availability_source_ids")

        minutes = row.get("projected_minutes")
        if not isinstance(minutes, dict):
            raise ValueError(f"players[{idx}].projected_minutes required")
        try:
            low = float(minutes["low"])
            mean = float(minutes["mean"])
            high = float(minutes["high"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"players[{idx}].projected_minutes low/mean/high required") from exc
        if not 0 <= low <= mean <= high <= 90:
            raise ValueError(f"players[{idx}].projected_minutes must satisfy 0<=low<=mean<=high<=90")
        _source_ids(minutes.get("source_ids"), known_sources, f"players[{idx}].projected_minutes.source_ids")

        role = row.get("role")
        if not isinstance(role, dict):
            raise ValueError(f"players[{idx}].role required")
        if str(role.get("state") or "").upper() not in VALID_ROLE_STATES:
            raise ValueError(f"players[{idx}].role.state invalid")
        role_name = str(role.get("position_role") or "").upper()
        if role_name not in VALID_ROLES:
            raise ValueError(f"players[{idx}].role.position_role invalid")
        if player_type == "GOALKEEPER" and role_name != "GK":
            raise ValueError(f"players[{idx}] goalkeeper must use GK role")
        if player_type == "OUTFIELD" and role_name == "GK":
            raise ValueError(f"players[{idx}] outfield player cannot use GK role")
        _source_ids(role.get("source_ids"), known_sources, f"players[{idx}].role.source_ids")
        _notes(role.get("notes"), f"players[{idx}].role.notes")

        stat_context = row.get("stat_context")
        if not isinstance(stat_context, dict):
            raise ValueError(f"players[{idx}].stat_context required")
        required_stats = {"saves"} if player_type == "GOALKEEPER" else {"shots", "shots_on_target"}
        if not required_stats.issubset(stat_context):
            raise ValueError(f"players[{idx}].stat_context missing {sorted(required_stats - set(stat_context))}")
        for stat in required_stats:
            value = stat_context[stat]
            if not isinstance(value, dict):
                raise ValueError(f"players[{idx}].stat_context.{stat} must be an object")
            _source_ids(value.get("source_ids"), known_sources, f"players[{idx}].stat_context.{stat}.source_ids")
            _notes(value.get("notes"), f"players[{idx}].stat_context.{stat}.notes")
        if player_type == "GOALKEEPER" and availability != "OUT":
            goalkeeper_teams.add(team_id)

    if run_mode in {"ALL", "SAVES_ONLY"} and goalkeeper_teams != expected_team_ids:
        raise ValueError("save modeling requires a researched non-OUT goalkeeper for each team")
    return context


def research_player_map(context: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    validate_research_context(context)
    return {player_key(row): row for row in context["players"]}
