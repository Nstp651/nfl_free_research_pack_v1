#!/usr/bin/env python3
"""Atomic pre-market freeze core for one NBL matchup.

The quantitative head artifacts are immutable QBASE anchors. Current research and
scenario projections are validated separately, then both requested stat heads are
frozen together. Probability grids are generated here from the final weighted mean
and the temporal-OOS dispersion stored in QBASE; sportsbook data is forbidden.

This Python reference mirrors the production Worker contract: every frozen head
must carry an explicit server QBASE/translation attestation and every quantitative
scenario must carry a 64-hex quantitative input receipt.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from typing import Any

try:
    from .model.distribution import probability_grid
    from .research_contract import (
        player_key, research_player_map, requested_heads, validate_research_context,
    )
    from .source_client import market_key_hits
except ImportError:  # pragma: no cover - CLI/local import compatibility
    from model.distribution import probability_grid
    from research_contract import player_key, research_player_map, requested_heads, validate_research_context
    from source_client import market_key_hits

SCHEMA_VERSION = "nbl_dual_head_freeze_v1"
VALID_CONFIDENCE = {"A", "B", "C"}
VALID_FRAGILITY = {"LOW", "MEDIUM", "HIGH"}
VALID_SCENARIO_METHODS = {
    "QBASE_RUNTIME_SCORE",
    "QBASE_MINUTES_RECOMPUTE",
    "EMPIRICAL_ROLE_SPLIT",
    "PRIOR_COMP_TRANSLATION",
}
VALID_SERVER_QBASE_SOURCES = {"SERVER_QBASE_RUNTIME_SCORE", "PRIOR_COMP_TRANSLATION"}
HASH64 = re.compile(r"^[0-9a-f]{64}$")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _iso8601(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return datetime.now(timezone.utc).isoformat()
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("frozen_at must be ISO-8601") from exc
    return text


def _qbase_contract(artifact: dict[str, Any], stat: str) -> dict[str, Any]:
    if not isinstance(artifact, dict) or artifact.get("market_data") is not False:
        raise ValueError(f"{stat} QBASE must declare market_data=false")
    if market_key_hits(artifact):
        raise ValueError(f"{stat} QBASE contains market-like fields")
    if artifact.get("stat_type") != stat:
        raise ValueError(f"QBASE stat mismatch for {stat}")
    wf = artifact.get("walk_forward") or {}
    prob = artifact.get("probability_contract") or {}
    try:
        alpha = float(wf["nb2_alpha_oos"])
        max_count = int(prob["max_count"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"{stat} QBASE missing dispersion/max_count contract") from exc
    if not math.isfinite(alpha) or alpha <= 0:
        raise ValueError(f"{stat} QBASE dispersion must be positive")
    if max_count < 5 or max_count > 60:
        raise ValueError(f"{stat} QBASE max_count invalid")
    return {
        "stat_type": stat,
        "model_name": artifact.get("model_name"),
        "model_version": artifact.get("model_version"),
        "feature_schema": artifact.get("feature_schema"),
        "dispersion_alpha": alpha,
        "max_count": max_count,
        "qbase_sha256": sha256_json(artifact),
    }


def _source_ids(scenario: dict[str, Any], known_sources: set[str], label: str) -> list[str]:
    value = scenario.get("evidence_source_ids")
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label}.evidence_source_ids required")
    ids = [str(x).strip() for x in value if str(x).strip()]
    unknown = sorted(set(ids) - known_sources)
    if unknown:
        raise ValueError(f"{label} references unknown source ids {unknown}")
    return ids


def _server_attestation(head: dict[str, Any], label: str) -> dict[str, Any]:
    source = str(head.get("server_qbase_source") or "").upper()
    if source not in VALID_SERVER_QBASE_SOURCES:
        raise ValueError(f"{label}.server_qbase_source invalid")
    raw_receipt = head.get("server_qbase_receipt_sha256")
    receipt = None if raw_receipt is None else str(raw_receipt).strip()
    raw_prior = head.get("server_player_prior_key")
    prior_key = None if raw_prior is None else str(raw_prior).strip()
    if source == "SERVER_QBASE_RUNTIME_SCORE":
        if not HASH64.fullmatch(receipt or ""):
            raise ValueError(f"{label}.server QBASE receipt required")
        if not prior_key:
            raise ValueError(f"{label}.server player prior key required")
    else:
        if receipt:
            raise ValueError(f"{label}.translated head cannot claim server QBASE receipt")
        if prior_key:
            raise ValueError(f"{label}.translated head cannot claim NBL player prior key")
    return {
        "source": source,
        "receipt_sha256": receipt or None,
        "player_prior_key": prior_key or None,
    }


def _validate_scenarios(
    head: dict[str, Any], known_sources: set[str], label: str
) -> tuple[list[dict[str, Any]], float]:
    scenarios = head.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError(f"{label}.scenarios must be non-empty")
    out: list[dict[str, Any]] = []
    total_weight = 0.0
    weighted_mean = 0.0
    seen_ids: set[str] = set()
    for idx, row in enumerate(scenarios):
        if not isinstance(row, dict):
            raise ValueError(f"{label}.scenarios[{idx}] must be an object")
        sid = str(row.get("id") or "").strip()
        if not sid or sid in seen_ids:
            raise ValueError(f"{label}.scenarios[{idx}] id missing/duplicate")
        seen_ids.add(sid)
        try:
            weight = float(row["weight"])
            mean = float(row["mean"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"{label}.scenarios[{idx}] weight/mean required") from exc
        if not math.isfinite(weight) or weight <= 0 or weight > 1:
            raise ValueError(f"{label}.scenarios[{idx}] invalid weight")
        if not math.isfinite(mean) or mean < 0 or mean > 50:
            raise ValueError(f"{label}.scenarios[{idx}] invalid mean")
        method = str(row.get("method") or "").upper()
        if method not in VALID_SCENARIO_METHODS:
            raise ValueError(f"{label}.scenarios[{idx}] invalid method")
        evidence = _source_ids(row, known_sources, f"{label}.scenarios[{idx}]")
        assumptions = row.get("assumptions", [])
        if not isinstance(assumptions, list):
            raise ValueError(f"{label}.scenarios[{idx}].assumptions must be a list")
        assumptions = [str(x).strip() for x in assumptions if str(x).strip()]
        receipt = str(row.get("quant_input_receipt_sha256") or "").strip()
        if not HASH64.fullmatch(receipt):
            raise ValueError(f"{label}.scenarios[{idx}] quant input receipt required")
        out.append({
            "id": sid,
            "weight": weight,
            "mean": mean,
            "method": method,
            "evidence_source_ids": evidence,
            "assumptions": assumptions,
            "quant_input_receipt_sha256": receipt,
        })
        total_weight += weight
        weighted_mean += weight * mean
    if abs(total_weight - 1.0) > 1e-9:
        raise ValueError(f"{label}.scenario weights must sum to 1.0, got {total_weight}")
    return out, weighted_mean


def _minutes_snapshot(research_player: dict[str, Any]) -> dict[str, Any]:
    minutes = research_player["projected_minutes"]
    snapshot = {
        "low": float(minutes["low"]),
        "mean": float(minutes["mean"]),
        "high": float(minutes["high"]),
        "source_ids": list(minutes["source_ids"]),
    }
    return {**snapshot, "minutes_projection_sha256": sha256_json(snapshot)}


def build_frozen_matchup(
    research_context: dict[str, Any],
    qbase_artifacts: dict[str, dict[str, Any]],
    player_projections: list[dict[str, Any]],
    *,
    frozen_at: str | None = None,
) -> dict[str, Any]:
    """Validate and atomically freeze all requested heads for all modeled players."""
    validate_research_context(research_context)
    if market_key_hits(player_projections):
        raise ValueError("player projections contain market-like fields")
    run_mode = str(research_context["run_mode"]).upper()
    heads = requested_heads(run_mode)
    qbase = {stat: _qbase_contract(qbase_artifacts.get(stat, {}), stat) for stat in heads}
    known_sources = set(research_context["sources"].keys())
    research_players = research_player_map(research_context)

    if not isinstance(player_projections, list) or not player_projections:
        raise ValueError("player_projections must be a non-empty list")
    frozen_players: list[dict[str, Any]] = []
    seen: set[str] = set()
    for pidx, projection in enumerate(player_projections):
        if not isinstance(projection, dict):
            raise ValueError(f"player_projections[{pidx}] must be an object")
        key = player_key(projection)
        if key in seen:
            raise ValueError(f"duplicate modeled player {key}")
        seen.add(key)
        research_player = research_players.get(key)
        if research_player is None:
            raise ValueError(f"modeled player {key} missing from research context")
        if str(projection.get("player_name") or "").strip() != str(research_player.get("player_name") or "").strip():
            raise ValueError(f"modeled player name mismatch for {key}")
        if str(projection.get("team") or "").strip() != str(research_player.get("team") or "").strip():
            raise ValueError(f"modeled player team mismatch for {key}")
        availability = str(research_player.get("availability_status") or "").upper()
        if availability == "OUT":
            raise ValueError(f"cannot freeze modeled OUT player {research_player['player_name']}")

        supplied_heads = projection.get("heads")
        if not isinstance(supplied_heads, dict):
            raise ValueError(f"modeled player {key} missing heads")
        missing = set(heads) - set(supplied_heads)
        if missing:
            raise ValueError(f"modeled player {key} missing requested heads {sorted(missing)}")
        unexpected = set(supplied_heads) - set(heads)
        if unexpected:
            raise ValueError(f"modeled player {key} has unexpected heads {sorted(unexpected)}")

        frozen_heads: dict[str, Any] = {}
        for stat in heads:
            head = supplied_heads[stat]
            if not isinstance(head, dict):
                raise ValueError(f"{key}.{stat} head must be an object")
            try:
                qbase_mean = float(head["qbase_mean"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"{key}.{stat}.qbase_mean required") from exc
            if not math.isfinite(qbase_mean) or qbase_mean < 0 or qbase_mean > 50:
                raise ValueError(f"{key}.{stat}.qbase_mean invalid")

            attestation = _server_attestation(head, f"{key}.{stat}")
            confidence = str(head.get("confidence") or "").upper()
            fragility = str(head.get("fragility") or "").upper()
            if confidence not in VALID_CONFIDENCE:
                raise ValueError(f"{key}.{stat}.confidence invalid")
            if fragility not in VALID_FRAGILITY:
                raise ValueError(f"{key}.{stat}.fragility invalid")

            scenarios, final_mean = _validate_scenarios(head, known_sources, f"{key}.{stat}")
            contract = qbase[stat]
            alpha = float(contract["dispersion_alpha"])
            dispersion_source = "QBASE_TEMPORAL_OOS"

            if attestation["source"] == "PRIOR_COMP_TRANSLATION":
                if any(row["method"] != "PRIOR_COMP_TRANSLATION" for row in scenarios):
                    raise ValueError(f"{key}.{stat} translated head must use PRIOR_COMP_TRANSLATION scenarios only")
                if "dispersion_override" not in head:
                    raise ValueError(f"{key}.{stat} translated head requires dispersion override")

            if "dispersion_override" in head:
                override = head.get("dispersion_override") or {}
                if not any(row["method"] == "PRIOR_COMP_TRANSLATION" for row in scenarios):
                    raise ValueError("dispersion override only permitted for prior-comp translation")
                try:
                    override_alpha = float(override["alpha"])
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError("dispersion override receipt invalid") from exc
                if (
                    override.get("method") != "MAX_QBASE_PRIOR_COMP"
                    or not HASH64.fullmatch(str(override.get("receipt_sha256") or ""))
                ):
                    raise ValueError("dispersion override receipt invalid")
                if not math.isfinite(override_alpha) or override_alpha < alpha or override_alpha > 5:
                    raise ValueError("dispersion override may not narrow QBASE")
                alpha = override_alpha
                dispersion_source = "MAX_QBASE_PRIOR_COMP"

            grid = probability_grid(final_mean, alpha, contract["max_count"])
            frozen_heads[stat] = {
                "qbase_anchor": contract,
                "qbase_mean": qbase_mean,
                "server_quantitative_attestation": attestation,
                "scenario_ledger": scenarios,
                "final_mean": final_mean,
                "dispersion_alpha": alpha,
                "dispersion_source": dispersion_source,
                "probability_grid": grid,
                "confidence": confidence,
                "fragility": fragility,
            }

        frozen_players.append({
            "player_id": str(projection.get("player_id") or "").strip() or None,
            "player_name": str(projection["player_name"]).strip(),
            "team": str(projection["team"]).strip(),
            "availability_status": availability,
            "role": research_player["role"],
            "projected_minutes": _minutes_snapshot(research_player),
            "heads": frozen_heads,
        })

    frozen_players.sort(key=lambda r: (r["team"].lower(), r["player_name"].lower()))
    timestamp = _iso8601(frozen_at)
    core = {
        "schema_version": SCHEMA_VERSION,
        "market_data": False,
        "status": "FROZEN",
        "run_mode": run_mode,
        "requested_heads": list(heads),
        "fixture_id": str(research_context["fixture_id"]),
        "pack_revision": str(research_context["pack_revision"]),
        "research_context_sha256": sha256_json(research_context),
        "qbase_sha256": {stat: qbase[stat]["qbase_sha256"] for stat in heads},
        "frozen_at": timestamp,
        "players": frozen_players,
        "audits": {
            "market_boundary": "PASS",
            "research_binding": "PASS",
            "server_quantitative_authority": "PASS",
            "scenario_weighting": "PASS",
            "probability_grid": "PASS",
            "atomic_requested_heads": "PASS",
        },
    }
    if market_key_hits(core):
        raise ValueError("frozen model market-boundary audit failed")
    receipt = sha256_json(core)
    return {**core, "freeze_receipt_sha256": receipt}


def validate_frozen_matchup(frozen: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(frozen, dict) or frozen.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("invalid frozen matchup schema")
    if frozen.get("status") != "FROZEN" or frozen.get("market_data") is not False:
        raise ValueError("invalid frozen matchup status")
    hits = market_key_hits({k: v for k, v in frozen.items() if k != "freeze_receipt_sha256"})
    if hits:
        raise ValueError("frozen matchup contains market-like fields")
    receipt = str(frozen.get("freeze_receipt_sha256") or "")
    core = {k: v for k, v in frozen.items() if k != "freeze_receipt_sha256"}
    expected = sha256_json(core)
    if receipt != expected:
        raise ValueError("freeze receipt hash mismatch")
    return frozen
