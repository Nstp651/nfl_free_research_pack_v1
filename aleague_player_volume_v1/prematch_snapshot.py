"""Persisted pre-match participant snapshots for full historical replay.

A snapshot is an immutable, market-blind record of who the model believed was
available and how many minutes they were expected to play before kickoff. This is
the minimum evidence needed to reconstruct historical player selection without
using the realised appearance set as a hidden hindsight filter.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from .model_core import ModelIntegrityError, assert_market_blind


SCHEMA_VERSION = "aleague_prematch_participant_snapshot_v1"
VALID_PLAYER_TYPES = {"OUTFIELD", "GOALKEEPER"}
VALID_STATUSES = {"EXPECTED_ACTIVE", "QUESTIONABLE", "EXPECTED_BENCH", "OUT"}
VALID_SOURCES = {"PERSISTED_PREMATCH_LINEUP_SNAPSHOT", "PERSISTED_PREMATCH_RESEARCH_SNAPSHOT"}


def _utc(value: str, field: str) -> datetime:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ModelIntegrityError(f"{field} must be ISO-8601") from exc
    if dt.tzinfo is None:
        raise ModelIntegrityError(f"{field} must be timezone-aware")
    return dt.astimezone(timezone.utc)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


@dataclass(frozen=True)
class PrematchParticipant:
    player_id: str
    player_name: str
    team_id: str
    player_type: str
    status: str
    minutes_low: float
    minutes_mean: float
    minutes_high: float
    evidence_source_ids: tuple[str, ...]

    def validate(self, team_ids: set[str], known_sources: set[str]) -> None:
        if not self.player_id or not self.player_name:
            raise ModelIntegrityError("prematch participant player_id/player_name required")
        if self.team_id not in team_ids:
            raise ModelIntegrityError(f"prematch participant {self.player_id} team invalid")
        if self.player_type not in VALID_PLAYER_TYPES:
            raise ModelIntegrityError(f"prematch participant {self.player_id} player_type invalid")
        if self.status not in VALID_STATUSES:
            raise ModelIntegrityError(f"prematch participant {self.player_id} status invalid")
        if not 0 <= self.minutes_low <= self.minutes_mean <= self.minutes_high <= 90:
            raise ModelIntegrityError(f"prematch participant {self.player_id} minutes invalid")
        if self.status == "OUT" and any(value != 0 for value in (self.minutes_low, self.minutes_mean, self.minutes_high)):
            raise ModelIntegrityError(f"OUT participant {self.player_id} must have zero projected minutes")
        if not self.evidence_source_ids:
            raise ModelIntegrityError(f"prematch participant {self.player_id} evidence required")
        unknown = set(self.evidence_source_ids) - known_sources
        if unknown:
            raise ModelIntegrityError(f"prematch participant {self.player_id} unknown sources {sorted(unknown)}")


@dataclass(frozen=True)
class PrematchSnapshot:
    fixture_id: str
    kickoff_utc: str
    captured_at_utc: str
    home_team_id: str
    away_team_id: str
    source_type: str
    source_revision: str
    evidence_sources: Mapping[str, Mapping[str, Any]]
    participants: tuple[PrematchParticipant, ...]
    market_data: bool = False

    def validate(self) -> "PrematchSnapshot":
        if self.market_data is not False:
            raise ModelIntegrityError("prematch snapshot must declare market_data=False")
        assert_market_blind(self.to_unsigned_dict())
        if not self.fixture_id or not self.source_revision:
            raise ModelIntegrityError("prematch snapshot fixture_id/source_revision required")
        kickoff = _utc(self.kickoff_utc, "kickoff_utc")
        captured = _utc(self.captured_at_utc, "captured_at_utc")
        if captured >= kickoff:
            raise ModelIntegrityError("prematch snapshot must be captured strictly before kickoff")
        if not self.home_team_id or not self.away_team_id or self.home_team_id == self.away_team_id:
            raise ModelIntegrityError("prematch snapshot requires distinct home/away teams")
        if self.source_type not in VALID_SOURCES:
            raise ModelIntegrityError("prematch snapshot source_type invalid")
        if not isinstance(self.evidence_sources, Mapping) or not self.evidence_sources:
            raise ModelIntegrityError("prematch snapshot evidence_sources required")
        known_sources = set()
        for source_id, source in self.evidence_sources.items():
            if not str(source_id).strip() or not isinstance(source, Mapping):
                raise ModelIntegrityError("prematch snapshot invalid source entry")
            if not str(source.get("title") or "").strip() or not str(source.get("url") or "").startswith("https://"):
                raise ModelIntegrityError(f"prematch snapshot source {source_id} invalid")
            checked = _utc(str(source.get("checked_at_utc") or ""), f"source {source_id}.checked_at_utc")
            if checked > captured:
                raise ModelIntegrityError(f"source {source_id} checked after snapshot capture")
            known_sources.add(str(source_id))
        if not self.participants:
            raise ModelIntegrityError("prematch snapshot participants required")
        team_ids = {self.home_team_id, self.away_team_id}
        seen: set[str] = set()
        active_keeper_teams: set[str] = set()
        active_outfield_teams: set[str] = set()
        for participant in self.participants:
            participant.validate(team_ids, known_sources)
            if participant.player_id in seen:
                raise ModelIntegrityError(f"duplicate prematch participant {participant.player_id}")
            seen.add(participant.player_id)
            if participant.status != "OUT" and participant.minutes_mean > 0:
                if participant.player_type == "GOALKEEPER":
                    active_keeper_teams.add(participant.team_id)
                else:
                    active_outfield_teams.add(participant.team_id)
        if active_outfield_teams != team_ids:
            raise ModelIntegrityError("prematch snapshot requires projected outfield participants for both teams")
        if active_keeper_teams != team_ids:
            raise ModelIntegrityError("prematch snapshot requires projected goalkeeper for both teams")
        return self

    def to_unsigned_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "market_data": self.market_data,
            "fixture_id": self.fixture_id,
            "kickoff_utc": self.kickoff_utc,
            "captured_at_utc": self.captured_at_utc,
            "home_team_id": self.home_team_id,
            "away_team_id": self.away_team_id,
            "source_type": self.source_type,
            "source_revision": self.source_revision,
            "evidence_sources": {str(k): dict(v) for k, v in self.evidence_sources.items()},
            "participants": [
                {
                    "player_id": p.player_id,
                    "player_name": p.player_name,
                    "team_id": p.team_id,
                    "player_type": p.player_type,
                    "status": p.status,
                    "minutes_low": p.minutes_low,
                    "minutes_mean": p.minutes_mean,
                    "minutes_high": p.minutes_high,
                    "evidence_source_ids": list(p.evidence_source_ids),
                }
                for p in self.participants
            ],
        }

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        value = self.to_unsigned_dict()
        value["snapshot_receipt_sha256"] = sha256_json(value)
        return value


def snapshot_from_dict(value: Mapping[str, Any]) -> PrematchSnapshot:
    if not isinstance(value, Mapping):
        raise ModelIntegrityError("prematch snapshot row must be object")
    if value.get("schema_version") != SCHEMA_VERSION:
        raise ModelIntegrityError("prematch snapshot schema_version invalid")
    receipt = str(value.get("snapshot_receipt_sha256") or "")
    unsigned = dict(value)
    unsigned.pop("snapshot_receipt_sha256", None)
    if receipt and sha256_json(unsigned) != receipt:
        raise ModelIntegrityError("prematch snapshot receipt mismatch")
    participants_raw = value.get("participants")
    if not isinstance(participants_raw, list):
        raise ModelIntegrityError("prematch snapshot participants must be list")
    participants = tuple(
        PrematchParticipant(
            player_id=str(row.get("player_id") or "").strip(),
            player_name=str(row.get("player_name") or "").strip(),
            team_id=str(row.get("team_id") or "").strip(),
            player_type=str(row.get("player_type") or "").upper(),
            status=str(row.get("status") or "").upper(),
            minutes_low=float(row.get("minutes_low", 0)),
            minutes_mean=float(row.get("minutes_mean", 0)),
            minutes_high=float(row.get("minutes_high", 0)),
            evidence_source_ids=tuple(str(x) for x in row.get("evidence_source_ids") or []),
        )
        for row in participants_raw
        if isinstance(row, Mapping)
    )
    snapshot = PrematchSnapshot(
        fixture_id=str(value.get("fixture_id") or "").strip(),
        kickoff_utc=str(value.get("kickoff_utc") or ""),
        captured_at_utc=str(value.get("captured_at_utc") or ""),
        home_team_id=str(value.get("home_team_id") or "").strip(),
        away_team_id=str(value.get("away_team_id") or "").strip(),
        source_type=str(value.get("source_type") or "").upper(),
        source_revision=str(value.get("source_revision") or "").strip(),
        evidence_sources=value.get("evidence_sources") or {},
        participants=participants,
        market_data=value.get("market_data", False),
    )
    return snapshot.validate()


def validate_snapshot_series(snapshots: Iterable[PrematchSnapshot]) -> list[PrematchSnapshot]:
    out = []
    seen = set()
    for snapshot in snapshots:
        snapshot.validate()
        if snapshot.fixture_id in seen:
            raise ModelIntegrityError(f"duplicate prematch snapshot fixture {snapshot.fixture_id}")
        seen.add(snapshot.fixture_id)
        out.append(snapshot)
    return sorted(out, key=lambda item: (_utc(item.kickoff_utc, "kickoff_utc"), item.fixture_id))
