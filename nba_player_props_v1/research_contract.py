from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

SCHEMA_VERSION = "nba_game_research_v1"
RUN_MODES = {"BOTH", "ASSISTS_ONLY", "REBOUNDS_ONLY"}
AVAILABILITY = {"ACTIVE", "PROBABLE", "QUESTIONABLE", "DOUBTFUL", "OUT", "UNKNOWN"}
ROLE_STATES = {
    "RETURNING_SAME",
    "RETURNING_CHANGED",
    "NEW_TO_TEAM",
    "ROOKIE",
    "NEW_TO_NBA",
    "UNKNOWN",
}
METRIC_STATUS = {"AVAILABLE", "PARTIAL", "UNAVAILABLE", "BLOCKED", "NOT_RELIABLE"}
EVIDENCE_TYPES = {"DESCRIPTIVE", "CAUSAL", "STATUS", "ROLE", "ROTATION", "LINEUP", "TRANSACTION"}
SOURCE_TIERS = {0, 1, 2, 3}

MARKET_TOKENS = {
    "player_assists",
    "player_assists_alternate",
    "player_rebounds",
    "player_rebounds_alternate",
    "sportsbook",
    "bookmaker_price",
    "market_consensus",
}


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    player_count: int
    evidence_count: int


def _require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def _https(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return parsed.scheme == "https" and bool(parsed.netloc)
    except Exception:
        return False


def _timestamp(value: str) -> datetime:
    _require(isinstance(value, str) and value, "timestamp required")
    normalized = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    _require(dt.tzinfo is not None, "timestamp must include timezone")
    return dt.astimezone(timezone.utc)


def requested_heads(run_mode: str) -> tuple[str, ...]:
    _require(run_mode in RUN_MODES, "invalid run_mode")
    if run_mode == "BOTH":
        return ("assists", "rebounds")
    return ("assists",) if run_mode == "ASSISTS_ONLY" else ("rebounds",)


def validate_research_checkpoint(payload: dict[str, Any], *, now: datetime | None = None) -> ValidationResult:
    _require(isinstance(payload, dict), "research checkpoint must be an object")
    _require(payload.get("schema_version") == SCHEMA_VERSION, "research schema mismatch")
    _require(payload.get("market_data") is False, "Layers 0-2 must be market-blind")
    _require(payload.get("run_mode") in RUN_MODES, "invalid run_mode")
    _require(isinstance(payload.get("game_id"), str) and len(payload["game_id"]) == 10, "invalid game_id")
    _require(isinstance(payload.get("slate_date_et"), str) and len(payload["slate_date_et"]) == 10, "invalid slate_date_et")

    text = repr(payload).lower()
    hits = sorted(token for token in MARKET_TOKENS if token in text)
    _require(not hits, f"market leakage detected: {hits}")

    evidence = payload.get("evidence")
    _require(isinstance(evidence, list) and evidence, "evidence required")
    evidence_ids: set[str] = set()
    current = now or datetime.now(timezone.utc)
    for row in evidence:
        _require(isinstance(row, dict), "invalid evidence row")
        evidence_id = row.get("evidence_id")
        _require(isinstance(evidence_id, str) and evidence_id and evidence_id not in evidence_ids, "invalid/duplicate evidence_id")
        evidence_ids.add(evidence_id)
        _require(_https(row.get("url", "")), "evidence URL must be absolute HTTPS")
        _require(isinstance(row.get("title"), str) and row["title"].strip(), "evidence title required")
        checked = _timestamp(row.get("checked_at"))
        _require(checked <= current.replace(microsecond=0), "evidence checked_at is in the future")
        if row.get("published_at"):
            published = _timestamp(row["published_at"])
            _require(published <= current.replace(microsecond=0), "evidence published_at is in the future")
        _require(row.get("source_tier") in SOURCE_TIERS, "invalid evidence source_tier")
        _require(row.get("evidence_type") in EVIDENCE_TYPES, "invalid evidence_type")

    metrics = payload.get("specialist_metrics")
    _require(isinstance(metrics, dict), "specialist_metrics registry required")
    for name, row in metrics.items():
        _require(isinstance(name, str) and name, "invalid specialist metric name")
        _require(isinstance(row, dict) and row.get("status") in METRIC_STATUS, f"invalid specialist metric status: {name}")
        if row.get("status") == "AVAILABLE":
            refs = row.get("evidence_ids")
            _require(isinstance(refs, list) and refs, f"AVAILABLE metric requires evidence: {name}")
            _require(all(ref in evidence_ids for ref in refs), f"unknown metric evidence id: {name}")

    players = payload.get("players")
    _require(isinstance(players, list) and players, "relevant players required")
    seen_players: set[str] = set()
    heads = requested_heads(payload["run_mode"])
    for player in players:
        _require(isinstance(player, dict), "invalid player record")
        player_id = str(player.get("player_id", "")).strip()
        _require(player_id and player_id not in seen_players, "invalid/duplicate player_id")
        seen_players.add(player_id)
        _require(player.get("availability") in AVAILABILITY, "invalid availability")
        _require(player.get("role_state") in ROLE_STATES, "invalid role_state")

        minutes = player.get("projected_minutes")
        _require(isinstance(minutes, dict), "projected_minutes required")
        low, mean, high = minutes.get("low"), minutes.get("mean"), minutes.get("high")
        _require(all(isinstance(x, (int, float)) for x in (low, mean, high)), "numeric minutes band required")
        _require(0 <= low <= mean <= high <= 53, "invalid minutes band")

        refs = player.get("evidence_ids")
        _require(isinstance(refs, list) and refs and all(ref in evidence_ids for ref in refs), "player evidence binding required")
        _require(isinstance(player.get("confidence_inputs"), dict), "confidence_inputs required")
        _require(isinstance(player.get("fragility_inputs"), dict), "fragility_inputs required")

        stat_context = player.get("stat_context")
        _require(isinstance(stat_context, dict), "stat_context required")
        for head in heads:
            context = stat_context.get(head)
            _require(isinstance(context, dict), f"{head} context required")
            _require(isinstance(context.get("causal_pathway"), str) and context["causal_pathway"].strip(), f"{head} causal pathway required")
            causal_refs = context.get("evidence_ids")
            _require(isinstance(causal_refs, list) and causal_refs, f"{head} evidence required")
            _require(all(ref in evidence_ids for ref in causal_refs), f"unknown {head} evidence id")

    return ValidationResult(ok=True, player_count=len(players), evidence_count=len(evidence))
