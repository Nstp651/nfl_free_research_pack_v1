"""Deterministic NBL V1.1 player/stat-first selector.

Consumes evaluated rows produced by the existing post-freeze market evaluator.
It never changes P_model or recalculates server probability/EV math.
"""
from __future__ import annotations

from typing import Any

EDGE_BAND = {"PREMIUM": 0, "STRONG": 1, "PLAYABLE": 2}
CONF_RANK = {"A": 0, "B": 1, "C": 2}
FRAG_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
VALIDATION_RANK = {"DIRECT_VALIDATED": 0, "TAIL_SUPPORTED": 1, "EXTREME_TAIL": 2}


def edge_band(edge: float) -> str | None:
    if edge >= 0.07:
        return "PREMIUM"
    if edge >= 0.04:
        return "STRONG"
    if edge >= 0.02:
        return "PLAYABLE"
    return None


def _p(row: dict[str, Any]) -> float:
    return float(row["conditional_win_probability"])


def _edge(row: dict[str, Any]) -> float:
    return float(row["probability_edge"])


def _ev(row: dict[str, Any]) -> float:
    return float(row["ev_per_unit"])


def _supported_threshold(row: dict[str, Any]) -> bool:
    state = str(row.get("threshold_validation"))
    return state == "DIRECT_VALIDATED" or (
        state == "TAIL_SUPPORTED" and bool(row.get("threshold_best_single_supported"))
    )


def core_path(row: dict[str, Any]) -> str | None:
    if str(row.get("side", "")).lower() != "over":
        return None
    p, edge, ev = _p(row), _edge(row), _ev(row)
    conf, frag = str(row.get("confidence")), str(row.get("fragility"))
    state = str(row.get("threshold_validation"))
    if not _supported_threshold(row) or edge <= 0 or ev <= 0:
        return None
    if (
        p >= 0.40
        and edge >= 0.02
        and ev >= 0.05
        and conf in {"A", "B"}
        and frag in {"LOW", "MEDIUM"}
    ):
        return "STANDARD"
    if (
        0.30 <= p < 0.40
        and edge >= 0.04
        and ev >= 0.10
        and conf == "A"
        and frag == "LOW"
        and state == "DIRECT_VALIDATED"
    ):
        return "SUPPORTED_LOWER_HIT"
    return None


def _rank_key(row: dict[str, Any]) -> tuple:
    band = edge_band(_edge(row))
    path = core_path(row)
    return (
        EDGE_BAND.get(band or "", 99),
        0 if path == "STANDARD" else 1,
        -_edge(row),
        -_p(row),
        VALIDATION_RANK.get(str(row.get("threshold_validation")), 99),
        FRAG_RANK.get(str(row.get("fragility")), 99),
        CONF_RANK.get(str(row.get("confidence")), 99),
        -_ev(row),
        float(row.get("threshold")),
        str(row.get("stat_type")),
        str(row.get("frozen_player_id") or row.get("player_name") or ""),
        str(row.get("bookmaker") or ""),
    )


def _ladder_key(row: dict[str, Any]) -> tuple:
    return (
        EDGE_BAND.get(edge_band(_edge(row)) or "", 99),
        -_edge(row),
        -_p(row),
        VALIDATION_RANK.get(str(row.get("threshold_validation")), 99),
        FRAG_RANK.get(str(row.get("fragility")), 99),
        CONF_RANK.get(str(row.get("confidence")), 99),
        -_ev(row),
        float(row.get("threshold")),
        str(row.get("bookmaker") or ""),
    )


def _optional_ladder(row: dict[str, Any]) -> bool:
    return (
        str(row.get("side", "")).lower() == "over"
        and _p(row) >= 0.20
        and _edge(row) >= 0.02
        and _ev(row) >= 0.05
        and str(row.get("confidence")) in {"A", "B"}
        and str(row.get("fragility")) in {"LOW", "MEDIUM"}
        and _supported_threshold(row)
    )


def _optional_stretch(row: dict[str, Any]) -> bool:
    return (
        str(row.get("side", "")).lower() == "over"
        and 0.12 <= _p(row) < 0.20
        and _edge(row) >= 0.03
        and _ev(row) >= 0.10
        and str(row.get("confidence")) == "A"
        and str(row.get("fragility")) == "LOW"
        and _supported_threshold(row)
    )


def select_v11(evaluation: dict[str, Any]) -> dict[str, Any]:
    rows = evaluation.get("evaluated")
    if rows is None:
        return {"status": "MARKET_INPUT_INCOMPLETE"}
    if not rows:
        return {"status": "MARKET_INPUT_REQUIRED"}

    overs = [dict(r) for r in rows if str(r.get("side", "")).lower() == "over"]
    if not overs:
        return {"status": "MARKET_INPUT_REQUIRED"}

    by_head: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in overs:
        key = (
            str(row.get("frozen_player_id") or row.get("player_name") or ""),
            str(row.get("stat_type") or ""),
        )
        if not all(key):
            return {"status": "MARKET_INPUT_INCOMPLETE"}
        by_head.setdefault(key, []).append(row)

    anchors: list[dict[str, Any]] = []
    for rows_for_head in by_head.values():
        eligible = [r for r in rows_for_head if core_path(r)]
        if eligible:
            anchor = min(eligible, key=_rank_key)
            anchor["v11_core_path"] = core_path(anchor)
            anchor["v11_edge_band"] = edge_band(_edge(anchor))
            anchors.append(anchor)

    if not anchors:
        return {
            "status": "NO_BET",
            "message": "NO BET — no qualifying actionable NBL core prop.",
            "alternatives": [],
        }

    anchors.sort(key=_rank_key)
    core = anchors[0]
    core_key = (
        str(core.get("frozen_player_id") or core.get("player_name")),
        str(core.get("stat_type")),
    )
    higher = [
        r for r in by_head[core_key]
        if float(r.get("threshold")) > float(core.get("threshold"))
    ]

    ladder_rows = [r for r in higher if _optional_ladder(r)]
    stretch_rows = [r for r in higher if _optional_stretch(r)]
    ladder = min(ladder_rows, key=_ladder_key) if ladder_rows else None
    stretch = min(stretch_rows, key=_ladder_key) if stretch_rows else None

    return {
        "status": "BET",
        "policy_id": "NBL_PLAYER_PROPS_PLAYER_FIRST_1.1",
        "core": core,
        "optional_ladder": ladder,
        "optional_stretch": stretch,
        "alternatives": anchors[1:4],
        "server_best_single_audit": evaluation.get("best_single"),
    }
