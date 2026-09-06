#!/usr/bin/env python3
"""Canonical post-freeze market records for NBL player assists/rebounds.

Market source is deliberately abstract: The Odds API, a user screenshot already
parsed by the GPT, or a clean public-web source all normalize to the same record.
Nothing in this module is allowed to modify P_model.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

VALID_STATS = {"assists", "rebounds"}
VALID_SIDES = {"over", "under"}
VALID_SOURCES = {"odds_api", "screenshot", "public_web"}


@dataclass(frozen=True)
class MarketRecord:
    fixture_id: str
    player_name: str
    stat_type: str
    side: str
    threshold: float
    decimal_price: float
    bookmaker: str
    captured_at: str
    source_type: str
    player_id: str | None = None

    def validate(self) -> "MarketRecord":
        if not self.fixture_id.strip():
            raise ValueError("fixture_id required")
        if not self.player_name.strip():
            raise ValueError("player_name required")
        if self.stat_type not in VALID_STATS:
            raise ValueError(f"unsupported stat_type {self.stat_type}")
        if self.side not in VALID_SIDES:
            raise ValueError(f"unsupported side {self.side}")
        if self.source_type not in VALID_SOURCES:
            raise ValueError(f"unsupported source_type {self.source_type}")
        if self.threshold < 0 or self.threshold > 40:
            raise ValueError(f"implausible threshold {self.threshold}")
        if self.decimal_price <= 1.0 or self.decimal_price > 1000:
            raise ValueError(f"invalid decimal price {self.decimal_price}")
        if not self.bookmaker.strip():
            raise ValueError("bookmaker required")
        try:
            datetime.fromisoformat(self.captured_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("captured_at must be ISO-8601") from exc
        return self

    def to_dict(self) -> dict[str, Any]:
        return asdict(self.validate())


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def from_screenshot_rows(fixture_id: str, rows: Iterable[dict[str, Any]],
                         captured_at: str | None = None) -> list[MarketRecord]:
    """Normalize GPT-extracted screenshot rows after the model is frozen."""
    ts = captured_at or utc_now_iso()
    out: list[MarketRecord] = []
    for row in rows:
        out.append(MarketRecord(
            fixture_id=str(fixture_id),
            player_id=str(row["player_id"]) if row.get("player_id") else None,
            player_name=str(row["player_name"]).strip(),
            stat_type=str(row["stat_type"]).strip().lower(),
            side=str(row["side"]).strip().lower(),
            threshold=float(row["threshold"]),
            decimal_price=float(row["decimal_price"]),
            bookmaker=str(row["bookmaker"]).strip(),
            captured_at=str(row.get("captured_at") or ts),
            source_type="screenshot",
        ).validate())
    return out


def best_price(records: Iterable[MarketRecord]) -> list[MarketRecord]:
    """Highest price for exact fixture/player/stat/side/threshold; deterministic tie break."""
    best: dict[tuple[Any, ...], MarketRecord] = {}
    for r in records:
        r.validate()
        key = (r.fixture_id, (r.player_id or r.player_name.lower()), r.stat_type, r.side, r.threshold)
        old = best.get(key)
        if old is None or (r.decimal_price, r.captured_at, r.bookmaker.lower()) > (
            old.decimal_price, old.captured_at, old.bookmaker.lower()
        ):
            best[key] = r
    return sorted(best.values(), key=lambda r: (
        r.stat_type, r.player_name.lower(), r.threshold, r.side, r.bookmaker.lower()
    ))
