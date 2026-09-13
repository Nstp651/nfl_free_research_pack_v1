"""Canonical post-freeze market rows for A-League Player Volume V1.

Sportsbook/API data enters only here, after an immutable freeze exists. Screenshot
OCR/extraction is performed outside this module; this code only validates and
normalizes structured rows. It has no import path into the quantitative engine.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Iterable


VALID_STATS = {"PLAYER_SHOTS", "PLAYER_SHOTS_ON_TARGET", "GOALKEEPER_SAVES"}
VALID_SIDES = {"AT_LEAST", "OVER", "UNDER"}
VALID_SOURCES = {"SCREENSHOT", "MANUAL", "ODDS_API"}

STAT_ALIASES = {
    "PLAYER_SHOTS": "PLAYER_SHOTS",
    "SHOTS": "PLAYER_SHOTS",
    "TOTAL_SHOTS": "PLAYER_SHOTS",
    "PLAYER_SHOTS_ON_TARGET": "PLAYER_SHOTS_ON_TARGET",
    "SHOTS_ON_TARGET": "PLAYER_SHOTS_ON_TARGET",
    "SOT": "PLAYER_SHOTS_ON_TARGET",
    "PLAYER_SOT": "PLAYER_SHOTS_ON_TARGET",
    "GOALKEEPER_SAVES": "GOALKEEPER_SAVES",
    "KEEPER_SAVES": "GOALKEEPER_SAVES",
    "SAVES": "GOALKEEPER_SAVES",
}

SIDE_ALIASES = {
    "AT_LEAST": "AT_LEAST",
    "MILESTONE": "AT_LEAST",
    "PLUS": "AT_LEAST",
    "+": "AT_LEAST",
    "OVER": "OVER",
    "UNDER": "UNDER",
}


class MarketIntegrityError(ValueError):
    pass


def canonical_stat(value: Any) -> str:
    key = str(value or "").strip().upper().replace(" ", "_").replace("-", "_")
    stat = STAT_ALIASES.get(key)
    if stat is None:
        raise MarketIntegrityError(f"unsupported stat_type {value}")
    return stat


def canonical_side(value: Any) -> str:
    key = str(value or "").strip().upper()
    side = SIDE_ALIASES.get(key)
    if side is None:
        raise MarketIntegrityError(f"unsupported side {value}")
    return side


def _iso8601_aware(value: str) -> str:
    text = str(value or "").strip()
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MarketIntegrityError("captured_at must be ISO-8601") from exc
    if dt.tzinfo is None:
        raise MarketIntegrityError("captured_at must be timezone-aware")
    return text


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
        if not str(self.fixture_id).strip():
            raise MarketIntegrityError("fixture_id required")
        if not str(self.player_name).strip():
            raise MarketIntegrityError("player_name required")
        if self.stat_type not in VALID_STATS:
            raise MarketIntegrityError(f"unsupported stat_type {self.stat_type}")
        if self.side not in VALID_SIDES:
            raise MarketIntegrityError(f"unsupported side {self.side}")
        if str(self.source_type).upper() not in VALID_SOURCES:
            raise MarketIntegrityError(f"unsupported source_type {self.source_type}")
        threshold = float(self.threshold)
        if threshold < 0 or threshold > 20:
            raise MarketIntegrityError(f"implausible threshold {threshold}")
        doubled = threshold * 2.0
        if abs(doubled - round(doubled)) > 1e-9:
            raise MarketIntegrityError("threshold must be integer or half-point")
        if self.side == "AT_LEAST":
            if threshold < 1 or abs(threshold - round(threshold)) > 1e-9:
                raise MarketIntegrityError("AT_LEAST threshold must be an integer >= 1")
        price = float(self.decimal_price)
        if price <= 1.0 or price > 1000:
            raise MarketIntegrityError(f"invalid decimal price {price}")
        if not str(self.bookmaker).strip():
            raise MarketIntegrityError("bookmaker required")
        _iso8601_aware(self.captured_at)
        return self

    def to_dict(self) -> dict[str, Any]:
        return asdict(self.validate())


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_rows(
    fixture_id: str,
    rows: Iterable[dict[str, Any]],
    *,
    default_source_type: str,
    captured_at: str | None = None,
) -> list[MarketRecord]:
    """Normalize already-extracted sportsbook rows into one strict contract."""
    source = str(default_source_type or "").strip().upper()
    if source not in VALID_SOURCES:
        raise MarketIntegrityError(f"unsupported default_source_type {default_source_type}")
    timestamp = captured_at or utc_now_iso()
    out: list[MarketRecord] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise MarketIntegrityError(f"rows[{index}] must be an object")
        try:
            record = MarketRecord(
                fixture_id=str(fixture_id).strip(),
                player_id=str(row["player_id"]).strip() if row.get("player_id") else None,
                player_name=str(row["player_name"]).strip(),
                stat_type=canonical_stat(row["stat_type"]),
                side=canonical_side(row["side"]),
                threshold=float(row["threshold"]),
                decimal_price=float(row["decimal_price"]),
                bookmaker=str(row["bookmaker"]).strip(),
                captured_at=str(row.get("captured_at") or timestamp),
                source_type=str(row.get("source_type") or source).strip().upper(),
            ).validate()
        except KeyError as exc:
            raise MarketIntegrityError(f"rows[{index}] missing required field {exc.args[0]}") from exc
        out.append(record)
    return out


def from_screenshot_rows(
    fixture_id: str,
    rows: Iterable[dict[str, Any]],
    *,
    captured_at: str | None = None,
) -> list[MarketRecord]:
    return normalize_rows(
        fixture_id,
        rows,
        default_source_type="SCREENSHOT",
        captured_at=captured_at,
    )


def best_price(records: Iterable[MarketRecord]) -> list[MarketRecord]:
    """Retain the highest current price for an exact player/stat/side/threshold key."""
    best: dict[tuple[Any, ...], MarketRecord] = {}
    for record in records:
        record.validate()
        identity = ("id", record.player_id) if record.player_id else ("name", record.player_name.casefold())
        key = (record.fixture_id, identity, record.stat_type, record.side, float(record.threshold))
        old = best.get(key)
        if old is None or (record.decimal_price, record.captured_at, record.bookmaker.casefold()) > (
            old.decimal_price,
            old.captured_at,
            old.bookmaker.casefold(),
        ):
            best[key] = record
    return sorted(
        best.values(),
        key=lambda r: (r.stat_type, r.player_name.casefold(), r.side, r.threshold, r.bookmaker.casefold()),
    )
