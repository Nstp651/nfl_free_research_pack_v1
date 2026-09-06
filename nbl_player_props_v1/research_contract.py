#!/usr/bin/env python3
"""Market-blind current-research contract for one NBL fixture.

The Custom GPT/research layer may discover injuries, availability, projected minutes,
role changes, imports and coaching context from the public web. This module turns
that work into a narrow auditable receipt before either quantitative head can
freeze. Sportsbook/market fields are forbidden at this boundary.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

try:
    from .source_client import market_key_hits
except ImportError:  # pragma: no cover - CLI/local import compatibility
    from source_client import market_key_hits

SCHEMA_VERSION = "nbl_fixture_research_v1"
VALID_RUN_MODES = {"BOTH", "ASSISTS_ONLY", "REBOUNDS_ONLY"}
VALID_AVAILABILITY = {"ACTIVE", "PROBABLE", "QUESTIONABLE", "DOUBTFUL", "OUT", "UNKNOWN"}
VALID_ROLE_STATES = {
    "RETURNING_SAME", "RETURNING_CHANGED", "NEW_TO_TEAM", "NEW_TO_NBL", "ROOKIE", "UNKNOWN"
}
VALID_CREATION_ROLES = {"PRIMARY", "SECONDARY", "CONNECTOR", "OFF_BALL", "LOW", "UNKNOWN"}
VALID_FRONTCOURT_ROLES = {"PRIMARY_BIG", "SECOND_BIG", "SMALL_BALL_BIG", "WING", "GUARD", "UNKNOWN"}
STAT_TYPES = {"assists", "rebounds"}


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


def _player_key(row: dict[str, Any]) -> str:
    pid = str(row.get("player_id") or "").strip()
    if pid:
        return "id:" + pid
    name = re.sub(r"[^a-z0-9]+", "", str(row.get("player_name") or "").lower())
    if not name:
        raise ValueError("player_id or player_name required")
    return "name:" + name


def requested_heads(run_mode: str) -> tuple[str, ...]:
    if run_mode == "BOTH":
        return ("assists", "rebounds")
    if run_mode == "ASSISTS_ONLY":
        return ("assists",)
    if run_mode == "REBOUNDS_ONLY":
        return ("rebounds",)
    raise ValueError(f"unsupported run_mode {run_mode}")


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


def validate_research_context(context: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(context, dict):
        raise ValueError("research context must be an object")
    if context.get("market_data") is not False:
        raise ValueError("research context must declare market_data=false")
    hits = market_key_hits(context)
    if hits:
        raise ValueError("market-boundary audit failed: " + ", ".join(hits[:20]))
    if context.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {SCHEMA_VERSION}")

    fixture_id = str(context.get("fixture_id") or "").strip()
    pack_revision = str(context.get("pack_revision") or "").strip()
    if not fixture_id or not pack_revision:
        raise ValueError("fixture_id and pack_revision required")
    run_mode = str(context.get("run_mode") or "").strip().upper()
    requested_heads(run_mode)
    _iso8601(context.get("checked_at"), "checked_at")

    sources = context.get("sources")
    if not isinstance(sources, dict) or not sources:
        raise ValueError("sources must be a non-empty object keyed by source id")
    known_sources: set[str] = set()
    for sid, source in sources.items():
        sid = str(sid).strip()
        if not sid or not isinstance(source, dict):
            raise ValueError("invalid research source entry")
        known_sources.add(sid)
        _https(source.get("url"), f"sources.{sid}.url")
        _iso8601(source.get("checked_at"), f"sources.{sid}.checked_at")
        if not str(source.get("title") or "").strip():
            raise ValueError(f"sources.{sid}.title required")

    fixture = context.get("fixture_context")
    if not isinstance(fixture, dict):
        raise ValueError("fixture_context required")
    _source_ids(fixture.get("source_ids"), known_sources, "fixture_context.source_ids")
    if not str(fixture.get("status") or "").strip():
        raise ValueError("fixture_context.status required")

    players = context.get("players")
    if not isinstance(players, list) or not players:
        raise ValueError("players must be a non-empty list")
    seen: set[str] = set()
    for idx, row in enumerate(players):
        if not isinstance(row, dict):
            raise ValueError(f"players[{idx}] must be an object")
        key = _player_key(row)
        if key in seen:
            raise ValueError(f"duplicate research player {key}")
        seen.add(key)
        if not str(row.get("player_name") or "").strip():
            raise ValueError(f"players[{idx}].player_name required")
        if not str(row.get("team") or "").strip():
            raise ValueError(f"players[{idx}].team required")
        availability = str(row.get("availability_status") or "").upper()
        if availability not in VALID_AVAILABILITY:
            raise ValueError(f"players[{idx}].availability_status invalid")
        _source_ids(row.get("availability_source_ids"), known_sources,
                    f"players[{idx}].availability_source_ids")

        minutes = row.get("projected_minutes")
        if not isinstance(minutes, dict):
            raise ValueError(f"players[{idx}].projected_minutes required")
        try:
            low = float(minutes["low"]); mean = float(minutes["mean"]); high = float(minutes["high"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"players[{idx}].projected_minutes low/mean/high required") from exc
        if not (0 <= low <= mean <= high <= 50):
            raise ValueError(f"players[{idx}].projected_minutes must satisfy 0<=low<=mean<=high<=50")
        _source_ids(minutes.get("source_ids"), known_sources,
                    f"players[{idx}].projected_minutes.source_ids")

        role = row.get("role")
        if not isinstance(role, dict):
            raise ValueError(f"players[{idx}].role required")
        role_state = str(role.get("state") or "").upper()
        if role_state not in VALID_ROLE_STATES:
            raise ValueError(f"players[{idx}].role.state invalid")
        creation = str(role.get("creation_role") or "UNKNOWN").upper()
        frontcourt = str(role.get("frontcourt_role") or "UNKNOWN").upper()
        if creation not in VALID_CREATION_ROLES:
            raise ValueError(f"players[{idx}].role.creation_role invalid")
        if frontcourt not in VALID_FRONTCOURT_ROLES:
            raise ValueError(f"players[{idx}].role.frontcourt_role invalid")
        _source_ids(role.get("source_ids"), known_sources, f"players[{idx}].role.source_ids")

        stat_context = row.get("stat_context", {})
        if not isinstance(stat_context, dict):
            raise ValueError(f"players[{idx}].stat_context must be an object")
        for stat, value in stat_context.items():
            if stat not in STAT_TYPES or not isinstance(value, dict):
                raise ValueError(f"players[{idx}].stat_context contains invalid stat {stat}")
            _source_ids(value.get("source_ids"), known_sources,
                        f"players[{idx}].stat_context.{stat}.source_ids", required=False)

    return context


def research_player_map(context: dict[str, Any]) -> dict[str, dict[str, Any]]:
    validate_research_context(context)
    return {_player_key(row): row for row in context["players"]}


def player_key(row: dict[str, Any]) -> str:
    return _player_key(row)
