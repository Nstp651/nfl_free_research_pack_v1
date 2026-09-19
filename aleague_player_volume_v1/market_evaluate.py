"""Read-only post-freeze market evaluation for A-League Player Volume V1.

The evaluator can price milestone (2+), half-point (over 1.5) and integer push
(over 2) markets only when the exact required frozen count probabilities exist.
It never interpolates and never mutates/recomputes P_model after prices arrive.
"""
from __future__ import annotations

import copy
import math
import re
from typing import Any, Iterable, Sequence

from .freeze_core import SCHEMA_VERSION as FREEZE_SCHEMA_VERSION, sha256_json
from .market_adapters import MarketRecord, best_price


DEFAULT_SELECTION_SIDES = ("AT_LEAST", "OVER")
CONF_RANK = {"A": 0, "B": 1, "C": 2}
FRAG_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
HASH64 = re.compile(r"^[0-9a-f]{64}$")


class MarketEvaluationError(ValueError):
    pass


def norm_name(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def validate_frozen_fixture(frozen: dict[str, Any]) -> dict[str, Any]:
    """Verify the immutable receipt and per-head hashes before market mapping."""
    if not isinstance(frozen, dict):
        raise MarketEvaluationError("frozen artifact must be an object")
    if frozen.get("schema_version") != FREEZE_SCHEMA_VERSION:
        raise MarketEvaluationError("unexpected freeze schema")
    if frozen.get("market_data") is not False:
        raise MarketEvaluationError("frozen artifact must declare market_data=false")
    receipt = str(frozen.get("freeze_receipt_sha256") or "")
    if not HASH64.fullmatch(receipt):
        raise MarketEvaluationError("freeze receipt missing/invalid")
    unsigned = copy.deepcopy(frozen)
    unsigned.pop("freeze_receipt_sha256", None)
    if sha256_json(unsigned) != receipt:
        raise MarketEvaluationError("freeze receipt mismatch")

    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    for player in list(frozen.get("outfield_players") or []) + list(frozen.get("goalkeepers") or []):
        if not isinstance(player, dict):
            raise MarketEvaluationError("invalid frozen player row")
        pid = str(player.get("player_id") or "").strip()
        name = norm_name(player.get("player_name"))
        if pid:
            if pid in seen_ids:
                raise MarketEvaluationError(f"duplicate frozen player id {pid}")
            seen_ids.add(pid)
        if not name or name in seen_names:
            raise MarketEvaluationError(f"duplicate/empty normalized frozen player name {name}")
        seen_names.add(name)
        heads = player.get("heads") or {}
        if not isinstance(heads, dict):
            raise MarketEvaluationError("invalid frozen heads")
        for stat, head in heads.items():
            if not isinstance(head, dict) or head.get("stat") != stat:
                raise MarketEvaluationError(f"frozen head mismatch {stat}")
            model_hash = str(head.get("model_hash") or "")
            if not HASH64.fullmatch(model_hash):
                raise MarketEvaluationError(f"{stat} model hash invalid")
            unhashed = copy.deepcopy(head)
            unhashed.pop("model_hash", None)
            if sha256_json(unhashed) != model_hash:
                raise MarketEvaluationError(f"{stat} model hash mismatch")
            ladder = head.get("at_least")
            if not isinstance(ladder, dict) or not ladder:
                raise MarketEvaluationError(f"{stat} missing at_least ladder")
            previous = 1.0
            for key in sorted(ladder, key=lambda x: int(x)):
                value = float(ladder[key])
                if value < -1e-12 or value > 1 + 1e-12 or value > previous + 1e-12:
                    raise MarketEvaluationError(f"{stat} invalid probability ladder")
                previous = value
    return frozen


def _player_index(frozen: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for player in list(frozen.get("outfield_players") or []) + list(frozen.get("goalkeepers") or []):
        pid = str(player.get("player_id") or "").strip()
        if pid:
            index[("id", pid)] = player
        index[("name", norm_name(player.get("player_name")))] = player
    return index


def _at_least(head: dict[str, Any], minimum_count: int) -> float:
    if minimum_count <= 0:
        return 1.0
    ladder = head.get("at_least") or {}
    key = str(int(minimum_count))
    if key not in ladder:
        raise MarketEvaluationError(f"exact frozen count threshold {minimum_count}+ unavailable")
    value = float(ladder[key])
    if not 0 <= value <= 1:
        raise MarketEvaluationError("frozen probability outside [0,1]")
    return value


def _probability_partition(head: dict[str, Any], side: str, threshold: float) -> tuple[float, float, float]:
    """Return (p_win, p_push, p_loss) from exact frozen at-least counts."""
    line = float(threshold)
    if side == "AT_LEAST":
        minimum = int(round(line))
        p_win = _at_least(head, minimum)
        return p_win, 0.0, 1.0 - p_win

    doubled = line * 2.0
    if abs(doubled - round(doubled)) > 1e-9:
        raise MarketEvaluationError("only integer/half-point lines are supported")
    is_integer = abs(line - round(line)) <= 1e-9
    if not is_integer:
        minimum_over = math.floor(line) + 1
        p_over = _at_least(head, minimum_over)
        if side == "OVER":
            return p_over, 0.0, 1.0 - p_over
        if side == "UNDER":
            return 1.0 - p_over, 0.0, p_over
        raise MarketEvaluationError(f"unsupported side {side}")

    n = int(round(line))
    p_ge_n = _at_least(head, n)
    p_ge_n_plus_1 = _at_least(head, n + 1)
    p_equal_n = p_ge_n - p_ge_n_plus_1
    p_below_n = 1.0 - p_ge_n
    if min(p_equal_n, p_below_n, p_ge_n_plus_1) < -1e-12:
        raise MarketEvaluationError("invalid integer-line frozen partition")
    if side == "OVER":
        return p_ge_n_plus_1, p_equal_n, p_below_n
    if side == "UNDER":
        return p_below_n, p_equal_n, p_ge_n_plus_1
    raise MarketEvaluationError(f"unsupported side {side}")


def _map_record(
    frozen: dict[str, Any],
    index: dict[tuple[str, str], dict[str, Any]],
    record: MarketRecord,
    selection_sides: set[str],
) -> dict[str, Any]:
    record.validate()
    if record.fixture_id != str(frozen.get("fixture_id")):
        raise MarketEvaluationError("market fixture does not match frozen fixture")
    player = index.get(("id", str(record.player_id))) if record.player_id else None
    if player is None:
        player = index.get(("name", norm_name(record.player_name)))
    if player is None:
        raise MarketEvaluationError(f"market player {record.player_name} not in frozen P_model")
    head = (player.get("heads") or {}).get(record.stat_type)
    if not isinstance(head, dict):
        raise MarketEvaluationError(f"frozen {record.stat_type} unavailable for {record.player_name}")
    p_win, p_push, p_loss = _probability_partition(head, record.side, record.threshold)
    if abs(p_win + p_push + p_loss - 1.0) > 1e-9 or min(p_win, p_push, p_loss) < -1e-12:
        raise MarketEvaluationError("frozen probability partition invalid")
    price = float(record.decimal_price)
    ev = p_win * (price - 1.0) - p_loss
    non_push = p_win + p_loss
    conditional_win = p_win / non_push if non_push > 0 else math.nan
    market_break_even = 1.0 / price
    fair_price = non_push / p_win if p_win > 0 else math.inf
    probability_edge = conditional_win - market_break_even if math.isfinite(conditional_win) else math.nan
    selection_eligible = record.side in selection_sides
    return {
        **record.to_dict(),
        "frozen_player_id": player.get("player_id"),
        "frozen_player_name": player.get("player_name"),
        "p_win": p_win,
        "p_push": p_push,
        "p_loss": p_loss,
        "conditional_win_probability": conditional_win,
        "market_break_even_probability": market_break_even,
        "probability_edge": probability_edge,
        "fair_decimal_price": fair_price,
        "ev_per_unit": ev,
        "positive_ev": bool(ev > 0),
        "selection_eligible": selection_eligible,
        "confidence": str(player.get("confidence") or "C"),
        "fragility": str(player.get("fragility") or "HIGH"),
        "model_hash": head.get("model_hash"),
        "freeze_receipt_sha256": frozen.get("freeze_receipt_sha256"),
        "frozen_at": frozen.get("frozen_at"),
    }


def evaluate_markets(
    frozen: dict[str, Any],
    records: Iterable[MarketRecord],
    *,
    only_best_price: bool = True,
    selection_sides: Sequence[str] = DEFAULT_SELECTION_SIDES,
) -> dict[str, Any]:
    """Evaluate exact markets and rank eligible positive EV across all three heads."""
    validate_frozen_fixture(frozen)
    before = copy.deepcopy(frozen)
    normalized_selection_sides = {str(side).upper() for side in selection_sides}
    if not normalized_selection_sides or not normalized_selection_sides.issubset({"AT_LEAST", "OVER", "UNDER"}):
        raise MarketEvaluationError("invalid selection_sides")
    rows = list(records)
    if only_best_price:
        rows = best_price(rows)
    index = _player_index(frozen)
    evaluated = [_map_record(frozen, index, row, normalized_selection_sides) for row in rows]
    if frozen != before:
        raise AssertionError("market evaluation mutated frozen P_model")

    def rank_key(row: dict[str, Any]):
        return (
            -float(row["ev_per_unit"]),
            CONF_RANK.get(str(row.get("confidence")), 99),
            FRAG_RANK.get(str(row.get("fragility")), 99),
            str(row.get("stat_type")),
            str(row.get("frozen_player_name")).casefold(),
            float(row.get("threshold")),
            str(row.get("bookmaker")).casefold(),
        )

    evaluated.sort(key=rank_key)
    positives = [row for row in evaluated if row["positive_ev"] and row["selection_eligible"]]
    for rank, row in enumerate(positives, start=1):
        row["positive_edge_rank"] = rank
    return {
        "fixture_id": frozen.get("fixture_id"),
        "freeze_receipt_sha256": frozen.get("freeze_receipt_sha256"),
        "frozen_at": frozen.get("frozen_at"),
        "selection_sides": sorted(normalized_selection_sides),
        "market_records_evaluated": len(evaluated),
        "evaluated": evaluated,
        "positive_edges": positives,
        "best_single": positives[0] if positives else None,
        "no_forced_bet": not bool(positives),
    }
