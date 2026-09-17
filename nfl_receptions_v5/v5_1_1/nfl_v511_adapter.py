"""Adapter from actual NFL Receptions V5 Worker responses to V5.1.1 selector input.

V5.1.1 uses the existing frozen source_to_parameter_ledger as a pre-market,
receipt-bound selection eligibility registry. No probability-engine change is
required.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal

REGISTRY_VERSION = 1
GLOBAL_PATH = "selection_policy.research_quality_permission"
PLAYER_PREFIX = "selection_eligibility."
_ALLOWED_CLASS = {
    "ELITE TARGET EARNER",
    "PRIMARY TARGET EARNER",
    "SECONDARY HIGH-VOLUME TARGET",
    "ROLE-SPECIFIC TARGET EARNER",
    "OTHER",
}
_ALLOWED_ROLE = {"STABLE", "VERIFIED_EXPANSION", "SPECULATIVE", "UNUSABLE"}
_ALLOWED_POS = {"WR", "TE", "RB", "OTHER"}
_ALLOWED_STATUS = {"INCLUDE", "WATCHLIST", "EXCLUDE"}
_ALLOWED_FRAG = {"LOW", "MODERATE", "HIGH"}


def _iso_epoch(value: str) -> int:
    if not isinstance(value, str) or not value:
        raise ValueError("missing quote timestamp")
    text = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        raise ValueError("quote timestamp must include timezone")
    return int(dt.timestamp())


def _parse_json_rationale(item: dict, label: str) -> dict:
    raw = item.get("rationale")
    if not isinstance(raw, str):
        raise ValueError(f"{label} rationale missing")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} rationale is not canonical JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} rationale must be an object")
    return value


def _validate_player_registry(pid: str, item: dict, frozen_player: dict) -> dict:
    value = _parse_json_rationale(item, pid)
    required = {
        "v", "position", "include", "receiver_class", "role", "pathway_usable",
        "evidence_score", "availability_score", "role_score", "threshold_fragility",
    }
    if set(value) != required:
        raise ValueError(f"{pid} selection registry keys mismatch")
    if value["v"] != REGISTRY_VERSION:
        raise ValueError(f"{pid} selection registry version mismatch")
    if value["position"] not in _ALLOWED_POS:
        raise ValueError(f"{pid} invalid position")
    if value["include"] not in _ALLOWED_STATUS:
        raise ValueError(f"{pid} invalid include status")
    if value["receiver_class"] not in _ALLOWED_CLASS:
        raise ValueError(f"{pid} invalid receiver class")
    if value["role"] not in _ALLOWED_ROLE:
        raise ValueError(f"{pid} invalid role")
    if not isinstance(value["pathway_usable"], bool):
        raise ValueError(f"{pid} pathway_usable must be boolean")
    for key, hi in (("evidence_score", 16), ("availability_score", 2), ("role_score", 2)):
        n = value[key]
        if isinstance(n, bool) or not isinstance(n, int) or not 0 <= n <= hi:
            raise ValueError(f"{pid} invalid {key}")
    frag = value["threshold_fragility"]
    if not isinstance(frag, dict):
        raise ValueError(f"{pid} threshold_fragility must be an object")
    for k, verdict in frag.items():
        if not isinstance(k, str) or not k.isdigit() or int(k) < 1 or verdict not in _ALLOWED_FRAG:
            raise ValueError(f"{pid} invalid threshold fragility entry")
    evidence_ids = item.get("evidence_ids")
    if not isinstance(evidence_ids, list) or not evidence_ids or not all(isinstance(x, str) and x for x in evidence_ids):
        raise ValueError(f"{pid} selection registry evidence_ids missing")
    if frozen_player.get("player_id") != pid:
        raise ValueError(f"{pid} frozen player identity mismatch")
    if frozen_player.get("confidence") not in {"HIGH", "MEDIUM", "LOW"}:
        raise ValueError(f"{pid} invalid frozen confidence")
    if frozen_player.get("fragility") not in _ALLOWED_FRAG:
        raise ValueError(f"{pid} invalid frozen fragility")
    return {
        "position": value["position"],
        "include": value["include"],
        "receiver_class": value["receiver_class"],
        "role": value["role"],
        "pathway_usable": value["pathway_usable"],
        "evidence_score": value["evidence_score"],
        "availability_score": value["availability_score"],
        "role_score": value["role_score"],
        "confidence": frozen_player["confidence"],
        "fragility": frozen_player["fragility"],
        "evidence_ids": evidence_ids,
        "threshold_fragility": frag,
        "player_name": frozen_player.get("player_name"),
        "team": frozen_player.get("team"),
    }


def normalize_v511_inputs(freeze_response: dict, market_response: dict, now_epoch: int | None = None) -> dict:
    """Normalize actual V5 control + market responses into selector input.

    Raises ValueError/RuntimeError on missing or contradictory integrity fields.
    """
    if not isinstance(freeze_response, dict) or not isinstance(market_response, dict):
        raise ValueError("SELECTION INPUT INCOMPLETE")
    if freeze_response.get("p_model_status") != "FROZEN":
        raise ValueError("SELECTION INPUT INCOMPLETE")
    freeze = freeze_response.get("freeze")
    if not isinstance(freeze, dict):
        raise ValueError("FROZEN ARTIFACT INCOMPLETE")
    run_id = freeze_response.get("run_id") or market_response.get("run_id")
    if not isinstance(run_id, str) or len(run_id) != 64:
        raise ValueError("run identity missing")
    if market_response.get("run_id") != run_id:
        raise RuntimeError("RUN IDENTITY CONFLICT")
    receipt = freeze.get("freeze_receipt_sha256")
    if not isinstance(receipt, str) or len(receipt) != 64:
        raise ValueError("freeze receipt missing")
    if market_response.get("freeze_receipt_sha256") != receipt:
        raise RuntimeError("FREEZE RECEIPT CONFLICT")

    frozen_players = freeze.get("players")
    ledger = freeze.get("source_to_parameter_ledger")
    if not isinstance(frozen_players, list) or not frozen_players or not isinstance(ledger, list):
        raise ValueError("FROZEN SELECTION METADATA INCOMPLETE")
    frozen_by_id = {}
    for p in frozen_players:
        pid = p.get("player_id") if isinstance(p, dict) else None
        if not isinstance(pid, str) or pid in frozen_by_id:
            raise ValueError("frozen player identity invalid")
        frozen_by_id[pid] = p

    global_items = [x for x in ledger if isinstance(x, dict) and x.get("parameter_path") == GLOBAL_PATH]
    if len(global_items) != 1:
        raise ValueError("RESEARCH QUALITY REGISTRY INCOMPLETE")
    global_value = _parse_json_rationale(global_items[0], "research quality")
    if set(global_value) != {"v", "permission"} or global_value.get("v") != REGISTRY_VERSION or global_value.get("permission") not in {"YES", "NO"}:
        raise ValueError("research quality registry invalid")

    registry_items = {}
    for item in ledger:
        if not isinstance(item, dict):
            continue
        path = item.get("parameter_path")
        if isinstance(path, str) and path.startswith(PLAYER_PREFIX):
            pid = path[len(PLAYER_PREFIX):]
            if not pid or pid in registry_items:
                raise ValueError("duplicate/invalid selection registry player")
            registry_items[pid] = item
    if set(registry_items) != set(frozen_by_id):
        raise ValueError("SELECTION ELIGIBILITY REGISTRY INCOMPLETE")

    players = {
        pid: _validate_player_registry(pid, registry_items[pid], frozen_by_id[pid])
        for pid in sorted(frozen_by_id)
    }

    best_prices = market_response.get("best_prices")
    mapped_count = market_response.get("mapped_selection_count")
    if not isinstance(best_prices, list) or isinstance(mapped_count, bool) or not isinstance(mapped_count, int) or mapped_count != len(best_prices):
        raise ValueError("MARKET COVERAGE INCOMPLETE")

    rows = []
    for source in best_prices:
        if not isinstance(source, dict):
            raise ValueError("invalid market row")
        pid = source.get("player_id")
        if pid not in players:
            raise RuntimeError("MARKET PLAYER NOT IN FROZEN REGISTRY")
        k = source.get("reception_threshold")
        if isinstance(k, bool) or not isinstance(k, int) or k < 1:
            raise ValueError("invalid reception threshold")
        p = source.get("p_model")
        odds = source.get("price")
        try:
            if not Decimal(str(p)).is_finite() or not Decimal(str(odds)).is_finite():
                raise ValueError
        except Exception as exc:
            raise ValueError("invalid probability/price") from exc
        market_key = source.get("market_key")
        if market_key == "player_receptions":
            market = "standard"
        elif market_key == "player_receptions_alternate":
            market = "alternate"
        else:
            raise ValueError("unsupported market key")
        try:
            quote_time = _iso_epoch(source.get("last_update"))
        except ValueError:
            quote_time = -1
        rows.append({
            "player_id": pid,
            "k": k,
            "p": str(p),
            "odds": str(odds),
            "book": str(source.get("bookmaker_key") or source.get("bookmaker") or ""),
            "quote_time": quote_time,
            "market": market,
            "verified": True,
            "threshold_fragility": players[pid]["threshold_fragility"].get(str(k)),
        })

    if now_epoch is None:
        now_epoch = int(datetime.now(timezone.utc).timestamp())
    if isinstance(now_epoch, bool) or not isinstance(now_epoch, int):
        raise ValueError("now_epoch must be integer seconds")

    selector_players = {}
    for pid, p in players.items():
        q = dict(p)
        q.pop("threshold_fragility", None)
        q.pop("player_name", None)
        q.pop("team", None)
        selector_players[pid] = q

    return {
        "integrity_verified": True,
        "complete_board": True,
        "frozen": True,
        "research_permission": global_value["permission"] == "YES",
        "run_id": run_id,
        "freeze_receipt": receipt,
        "now": now_epoch,
        "players": selector_players,
        "rows": rows,
    }


def execute_v511(freeze_response: dict, market_response: dict, now_epoch: int | None = None) -> dict:
    """Normalize actual responses, preserve readiness statuses, then run selector."""
    from nfl_v511_selector import select

    try:
        data = normalize_v511_inputs(freeze_response, market_response, now_epoch=now_epoch)
    except RuntimeError as exc:
        return {"decision": "SELECTION INPUT INCOMPLETE", "status_detail": str(exc), "recommendations": []}
    except ValueError as exc:
        msg = str(exc)
        if "MARKET" in msg or "market" in msg or "quote" in msg:
            decision = "MARKET COVERAGE INCOMPLETE"
        else:
            decision = "SELECTION INPUT INCOMPLETE"
        return {"decision": decision, "status_detail": msg, "recommendations": []}

    if data.get("research_permission") is not True:
        return {
            "decision": "RESEARCH QUALITY BLOCKED",
            "status_detail": "research_quality_permission is not YES",
            "run_id": data["run_id"],
            "freeze_receipt": data["freeze_receipt"],
            "recommendations": [],
        }

    now = int(data["now"])
    current_rows = [r for r in data["rows"] if isinstance(r.get("quote_time"), int) and 0 <= now - r["quote_time"] <= 1800]
    if not current_rows:
        return {
            "decision": "MARKET INPUT REQUIRED",
            "status_detail": "no current valid mapped reception prices",
            "run_id": data["run_id"],
            "freeze_receipt": data["freeze_receipt"],
            "recommendations": [],
        }

    result = select(data)
    if result.get("decision") == "NO BET" and any(r not in current_rows for r in data["rows"]):
        result["decision"] = "MARKET INPUT REQUIRED"
        result["status_detail"] = "no qualifying core among current quotes; noncurrent quotes remain"
    return result
