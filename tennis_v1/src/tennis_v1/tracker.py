from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class TrackedBet:
    run_id: str
    event_id: str
    tour: str
    tournament: str
    player_a: str
    player_b: str
    market: str
    selection: str
    line: Optional[float]
    bookmaker: str
    odds: float
    stake: float
    p_model_win: float
    p_model_push: float
    ev_at_bet: float
    freeze_sha256: str
    placed_at_utc: str
    close_odds: Optional[float] = None
    result: Optional[str] = None
    pnl: Optional[float] = None


def append_bet(path: str | Path, bet: TrackedBet) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(bet), sort_keys=True) + "\n")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
