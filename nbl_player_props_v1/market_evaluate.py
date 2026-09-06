#!/usr/bin/env python3
"""Post-freeze EV evaluation for NBL assists/rebounds markets.

This module is deliberately read-only with respect to P_model. Every market record
must map to an exact frozen fixture/player/stat/threshold. Integer lines use the
frozen push partition; half-point lines use the no-push partition. No interpolation
or nearest-line substitution is permitted.
"""
from __future__ import annotations

import copy
import math
import re
from typing import Any, Iterable

try:
    from .freeze_core import validate_frozen_matchup
    from .market_adapters import MarketRecord, best_price
except ImportError:  # pragma: no cover
    from freeze_core import validate_frozen_matchup
    from market_adapters import MarketRecord, best_price

CONF_RANK = {"A": 0, "B": 1, "C": 2}
FRAG_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


def norm_name(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _player_index(frozen: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for p in frozen.get("players", []):
        pid = str(p.get("player_id") or "").strip()
        if pid:
            out[("id", pid)] = p
        out[("name", norm_name(p.get("player_name")))] = p
    return out


def _find_line(grid: dict[str, Any], threshold: float) -> dict[str, Any]:
    line = float(threshold)
    doubled = line * 2.0
    if abs(doubled - round(doubled)) > 1e-9:
        raise ValueError(f"unsupported non integer/half threshold {threshold}")
    if abs(line - round(line)) <= 1e-9:
        rows = grid.get("integer_push_grid", [])
    else:
        rows = grid.get("half_point_grid", [])
    found = [r for r in rows if abs(float(r.get("line")) - line) <= 1e-9]
    if len(found) != 1:
        raise ValueError(f"exact frozen threshold {threshold} unavailable")
    return found[0]


def _map_record(frozen: dict[str, Any], index: dict[tuple[str, str], dict[str, Any]], record: MarketRecord) -> dict[str, Any]:
    record.validate()
    if record.fixture_id != str(frozen.get("fixture_id")):
        raise ValueError(f"market fixture {record.fixture_id} does not match frozen fixture")
    player = None
    if record.player_id:
        player = index.get(("id", str(record.player_id)))
    if player is None:
        player = index.get(("name", norm_name(record.player_name)))
    if player is None:
        raise ValueError(f"market player {record.player_name} not in frozen P_model")
    head = (player.get("heads") or {}).get(record.stat_type)
    if not isinstance(head, dict):
        raise ValueError(f"frozen {record.stat_type} head unavailable for {record.player_name}")
    line = _find_line(head.get("probability_grid") or {}, record.threshold)
    side = record.side
    p_win = float(line[side])
    p_push = float(line.get("push", 0.0))
    other = "under" if side == "over" else "over"
    p_loss = float(line[other])
    if min(p_win, p_push, p_loss) < -1e-12 or abs(p_win + p_push + p_loss - 1.0) > 1e-9:
        raise ValueError("frozen probability partition invalid")
    price = float(record.decimal_price)
    ev = p_win * (price - 1.0) - p_loss
    non_push = p_win + p_loss
    conditional_win = p_win / non_push if non_push > 0 else math.nan
    market_break_even = 1.0 / price
    fair_price = non_push / p_win if p_win > 0 else math.inf
    probability_edge = conditional_win - market_break_even if math.isfinite(conditional_win) else math.nan
    return {
        **record.to_dict(),
        "frozen_player_name": player.get("player_name"),
        "frozen_player_id": player.get("player_id"),
        "p_win": p_win,
        "p_push": p_push,
        "p_loss": p_loss,
        "conditional_win_probability": conditional_win,
        "market_break_even_probability": market_break_even,
        "probability_edge": probability_edge,
        "fair_decimal_price": fair_price,
        "ev_per_unit": ev,
        "positive_ev": bool(ev > 0),
        "confidence": str(head.get("confidence") or "C"),
        "fragility": str(head.get("fragility") or "HIGH"),
        "freeze_receipt_sha256": frozen.get("freeze_receipt_sha256"),
        "frozen_at": frozen.get("frozen_at"),
    }


def evaluate_markets(
    frozen: dict[str, Any],
    records: Iterable[MarketRecord],
    *,
    only_best_price: bool = True,
) -> dict[str, Any]:
    """Evaluate exact post-freeze markets and return positive-edge ranking.

    Ranking is EV-first. Confidence/fragility are deterministic tie-breaks only;
    V1 does not invent an undocumented risk-adjustment multiplier.
    """
    validate_frozen_matchup(frozen)
    before = copy.deepcopy(frozen)
    rows = list(records)
    if only_best_price:
        rows = best_price(rows)
    index = _player_index(frozen)
    evaluated = [_map_record(frozen, index, row) for row in rows]
    if frozen != before:
        raise AssertionError("market evaluation mutated frozen P_model")

    def rank_key(row: dict[str, Any]):
        return (
            -float(row["ev_per_unit"]),
            CONF_RANK.get(str(row.get("confidence")), 99),
            FRAG_RANK.get(str(row.get("fragility")), 99),
            str(row.get("stat_type")),
            str(row.get("player_name")).lower(),
            float(row.get("threshold")),
            str(row.get("bookmaker")).lower(),
        )

    evaluated.sort(key=rank_key)
    positives = [row for row in evaluated if row["positive_ev"]]
    for rank, row in enumerate(positives, start=1):
        row["positive_edge_rank"] = rank
    return {
        "fixture_id": frozen.get("fixture_id"),
        "freeze_receipt_sha256": frozen.get("freeze_receipt_sha256"),
        "frozen_at": frozen.get("frozen_at"),
        "market_records_evaluated": len(evaluated),
        "evaluated": evaluated,
        "positive_edges": positives,
        "best_single": positives[0] if positives else None,
        "no_forced_bet": not bool(positives),
    }
