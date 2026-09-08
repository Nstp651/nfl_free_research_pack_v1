"""Atomic market-blind freeze core for A-League Player Volume V1."""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable

from .model_core import (
    ModelIntegrityError,
    PlayerShotProjection,
    allocate_team_shots,
    assert_market_blind,
    build_at_least_ladder,
    expected_goalkeeper_saves,
    expected_player_sot,
)
from .research_contract import player_key, research_player_map, validate_research_context


SCHEMA_VERSION = "aleague_player_volume_freeze_v1"
HASH64 = re.compile(r"^[0-9a-f]{64}$")
VALID_CONFIDENCE = {"A", "B", "C"}
VALID_FRAGILITY = {"LOW", "MEDIUM", "HIGH"}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _iso_or_now(value: str | None) -> str:
    if value is None:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    text = str(value).strip()
    datetime.fromisoformat(text.replace("Z", "+00:00"))
    return text


def _finite_nonnegative(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ModelIntegrityError(f"{label} must be numeric") from exc
    if not math.isfinite(number) or number < 0:
        raise ModelIntegrityError(f"{label} must be finite and nonnegative")
    return number


def _positive(value: Any, label: str) -> float:
    number = _finite_nonnegative(value, label)
    if number <= 0:
        raise ModelIntegrityError(f"{label} must be > 0")
    return number


def _prob(value: Any, label: str) -> float:
    number = _finite_nonnegative(value, label)
    if number > 1:
        raise ModelIntegrityError(f"{label} must be <= 1")
    return number


def _receipt(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not HASH64.fullmatch(text):
        raise ModelIntegrityError(f"{label} must be a 64-char lowercase SHA-256")
    return text


def _confidence_fields(model: Dict[str, Any], label: str) -> tuple[str, str]:
    confidence = str(model.get("confidence") or "").upper()
    fragility = str(model.get("fragility") or "").upper()
    if confidence not in VALID_CONFIDENCE:
        raise ModelIntegrityError(f"{label}.confidence invalid")
    if fragility not in VALID_FRAGILITY:
        raise ModelIntegrityError(f"{label}.fragility invalid")
    return confidence, fragility


def _source_ids(model: Dict[str, Any], known_sources: set[str], label: str) -> list[str]:
    value = model.get("evidence_source_ids")
    if not isinstance(value, list) or not value:
        raise ModelIntegrityError(f"{label}.evidence_source_ids required")
    ids = [str(item).strip() for item in value if str(item).strip()]
    unknown = sorted(set(ids) - known_sources)
    if unknown:
        raise ModelIntegrityError(f"{label} references unknown sources {unknown}")
    return ids


def _ladder(mean: float, dispersion: float, maximum: int) -> Dict[str, float]:
    return {str(k): v for k, v in build_at_least_ladder(mean, dispersion, max_threshold=maximum).items()}


def build_frozen_fixture(
    research_context: Dict[str, Any],
    team_models: list[Dict[str, Any]],
    outfield_models: list[Dict[str, Any]],
    goalkeeper_models: list[Dict[str, Any]],
    *,
    frozen_at: str | None = None,
) -> Dict[str, Any]:
    """Build one internally coherent immutable probability artifact.

    Team shot means are allocated to outfield players by exposure-adjusted shot
    propensity. Player SOT is a thinning of that frozen shot process. Team SOT
    is reconstructed from player + unmodelled SOT, and opponent team SOT then
    drives goalkeeper saves. No head can be supplied as an unrelated mean.
    """
    validate_research_context(research_context)
    assert_market_blind(team_models)
    assert_market_blind(outfield_models)
    assert_market_blind(goalkeeper_models)
    known_sources = set(research_context["sources"])
    research_players = research_player_map(research_context)
    fixture = research_context["fixture_context"]
    team_ids = {str(fixture["home_team_id"]), str(fixture["away_team_id"])}
    run_mode = str(research_context["run_mode"]).upper()

    if not isinstance(team_models, list) or len(team_models) != 2:
        raise ModelIntegrityError("team_models must contain exactly two teams")
    team_model_map: Dict[str, Dict[str, Any]] = {}
    for idx, model in enumerate(team_models):
        if not isinstance(model, dict):
            raise ModelIntegrityError(f"team_models[{idx}] must be an object")
        team_id = str(model.get("team_id") or "").strip()
        if team_id not in team_ids or team_id in team_model_map:
            raise ModelIntegrityError(f"team_models[{idx}].team_id invalid/duplicate")
        shot_mean = _finite_nonnegative(model.get("shot_mean"), f"team_models[{idx}].shot_mean")
        shot_dispersion = _positive(model.get("shot_dispersion"), f"team_models[{idx}].shot_dispersion")
        unmodelled_weight = _finite_nonnegative(model.get("unmodelled_weight"), f"team_models[{idx}].unmodelled_weight")
        unmodelled_p_sot = _prob(model.get("unmodelled_p_sot"), f"team_models[{idx}].unmodelled_p_sot")
        evidence = _source_ids(model, known_sources, f"team_models[{idx}]")
        receipt = _receipt(model.get("quant_input_receipt_sha256"), f"team_models[{idx}].quant_input_receipt_sha256")
        team_model_map[team_id] = {
            "team_id": team_id,
            "shot_mean": shot_mean,
            "shot_dispersion": shot_dispersion,
            "unmodelled_weight": unmodelled_weight,
            "unmodelled_p_sot": unmodelled_p_sot,
            "evidence_source_ids": evidence,
            "quant_input_receipt_sha256": receipt,
        }
    if set(team_model_map) != team_ids:
        raise ModelIntegrityError("team model ids do not match fixture")

    outfield_by_team: Dict[str, list[Dict[str, Any]]] = {team_id: [] for team_id in team_ids}
    seen_players = set()
    for idx, model in enumerate(outfield_models):
        if not isinstance(model, dict):
            raise ModelIntegrityError(f"outfield_models[{idx}] must be an object")
        key = player_key(model)
        if key in seen_players:
            raise ModelIntegrityError(f"duplicate modeled player {key}")
        seen_players.add(key)
        research = research_players.get(key)
        if research is None or str(research.get("player_type")).upper() != "OUTFIELD":
            raise ModelIntegrityError(f"modeled outfield player {key} missing/mismatched in research")
        if str(research.get("availability_status")).upper() == "OUT":
            raise ModelIntegrityError(f"cannot model OUT player {key}")
        team_id = str(model.get("team_id") or "").strip()
        if team_id != str(research.get("team_id")) or team_id not in team_ids:
            raise ModelIntegrityError(f"team mismatch for {key}")
        minutes_mean = float(research["projected_minutes"]["mean"])
        shots_per90_prior = _finite_nonnegative(model.get("shots_per90_prior"), f"{key}.shots_per90_prior")
        role_multiplier = _positive(model.get("role_multiplier"), f"{key}.role_multiplier")
        if role_multiplier > 2.0:
            raise ModelIntegrityError(f"{key}.role_multiplier exceeds V1 hard bound")
        p_sot = _prob(model.get("p_sot_given_shot"), f"{key}.p_sot_given_shot")
        shot_dispersion = _positive(model.get("shot_dispersion"), f"{key}.shot_dispersion")
        confidence, fragility = _confidence_fields(model, key)
        evidence = _source_ids(model, known_sources, key)
        receipt = _receipt(model.get("quant_input_receipt_sha256"), f"{key}.quant_input_receipt_sha256")
        outfield_by_team[team_id].append({
            "key": key,
            "player_id": str(model.get("player_id") or research.get("player_id") or ""),
            "player_name": str(research["player_name"]),
            "team_id": team_id,
            "minutes_mean": minutes_mean,
            "shots_per90_prior": shots_per90_prior,
            "role_multiplier": role_multiplier,
            "p_sot_given_shot": p_sot,
            "shot_dispersion": shot_dispersion,
            "confidence": confidence,
            "fragility": fragility,
            "evidence_source_ids": evidence,
            "quant_input_receipt_sha256": receipt,
        })

    if run_mode in {"ALL", "SHOOTING_ONLY"} and any(not outfield_by_team[t] for t in team_ids):
        raise ModelIntegrityError("shooting freeze requires modeled outfield players for both teams")

    frozen_outfield = []
    team_environment: Dict[str, Dict[str, Any]] = {}
    for team_id in sorted(team_ids):
        team_model = team_model_map[team_id]
        models = outfield_by_team[team_id]
        projections = [
            PlayerShotProjection(
                player_id=model["key"],
                minutes_mean=model["minutes_mean"],
                shots_per90_prior=model["shots_per90_prior"],
                role_multiplier=model["role_multiplier"],
            )
            for model in models
        ]
        if projections or team_model["unmodelled_weight"] > 0:
            means, unmodelled_shots = allocate_team_shots(
                team_model["shot_mean"], projections, team_model["unmodelled_weight"]
            )
        else:
            raise ModelIntegrityError(f"team {team_id} has no shot allocation weight")
        modeled_sot = 0.0
        for model in models:
            mu_shots = means[model["key"]]
            mu_sot = expected_player_sot(mu_shots, model["p_sot_given_shot"])
            modeled_sot += mu_sot
            heads: Dict[str, Any] = {}
            if run_mode in {"ALL", "SHOOTING_ONLY"}:
                shots_head = {
                    "stat": "PLAYER_SHOTS",
                    "mean": mu_shots,
                    "dispersion": model["shot_dispersion"],
                    "at_least": _ladder(mu_shots, model["shot_dispersion"], 8),
                }
                shots_head["model_hash"] = sha256_json(shots_head)
                sot_head = {
                    "stat": "PLAYER_SHOTS_ON_TARGET",
                    "mean": mu_sot,
                    "p_sot_given_shot": model["p_sot_given_shot"],
                    "dispersion": model["shot_dispersion"],
                    "at_least": _ladder(mu_sot, model["shot_dispersion"], 5),
                }
                sot_head["model_hash"] = sha256_json(sot_head)
                heads = {"PLAYER_SHOTS": shots_head, "PLAYER_SHOTS_ON_TARGET": sot_head}
            frozen_outfield.append({
                "player_id": model["player_id"],
                "player_name": model["player_name"],
                "team_id": team_id,
                "projected_minutes_mean": model["minutes_mean"],
                "confidence": model["confidence"],
                "fragility": model["fragility"],
                "evidence_source_ids": model["evidence_source_ids"],
                "quant_input_receipt_sha256": model["quant_input_receipt_sha256"],
                "heads": heads,
            })
        unmodelled_sot = unmodelled_shots * team_model["unmodelled_p_sot"]
        team_sot_mean = modeled_sot + unmodelled_sot
        if team_sot_mean > team_model["shot_mean"] + 1e-9:
            raise ModelIntegrityError(f"team {team_id} SOT mean exceeds shot mean")
        team_environment[team_id] = {
            **team_model,
            "unmodelled_shot_mean": unmodelled_shots,
            "modeled_sot_mean": modeled_sot,
            "unmodelled_sot_mean": unmodelled_sot,
            "sot_mean": team_sot_mean,
        }

    frozen_keepers = []
    seen_keeper_teams = set()
    for idx, model in enumerate(goalkeeper_models):
        if not isinstance(model, dict):
            raise ModelIntegrityError(f"goalkeeper_models[{idx}] must be an object")
        key = player_key(model)
        research = research_players.get(key)
        if research is None or str(research.get("player_type")).upper() != "GOALKEEPER":
            raise ModelIntegrityError(f"modeled goalkeeper {key} missing/mismatched in research")
        if str(research.get("availability_status")).upper() == "OUT":
            raise ModelIntegrityError(f"cannot model OUT goalkeeper {key}")
        team_id = str(model.get("team_id") or "").strip()
        if team_id != str(research.get("team_id")) or team_id not in team_ids or team_id in seen_keeper_teams:
            raise ModelIntegrityError(f"goalkeeper team mismatch/duplicate for {key}")
        seen_keeper_teams.add(team_id)
        opponent_id = next(value for value in team_ids if value != team_id)
        p_save = _prob(model.get("p_save_given_sot"), f"{key}.p_save_given_sot")
        save_dispersion = _positive(model.get("save_dispersion"), f"{key}.save_dispersion")
        confidence, fragility = _confidence_fields(model, key)
        evidence = _source_ids(model, known_sources, key)
        receipt = _receipt(model.get("quant_input_receipt_sha256"), f"{key}.quant_input_receipt_sha256")
        minutes_mean = float(research["projected_minutes"]["mean"])
        mu_saves = expected_goalkeeper_saves(team_environment[opponent_id]["sot_mean"], p_save, minutes_mean)
        heads: Dict[str, Any] = {}
        if run_mode in {"ALL", "SAVES_ONLY"}:
            saves_head = {
                "stat": "GOALKEEPER_SAVES",
                "mean": mu_saves,
                "opponent_sot_mean": team_environment[opponent_id]["sot_mean"],
                "p_save_given_sot": p_save,
                "dispersion": save_dispersion,
                "at_least": _ladder(mu_saves, save_dispersion, 8),
            }
            saves_head["model_hash"] = sha256_json(saves_head)
            heads = {"GOALKEEPER_SAVES": saves_head}
        frozen_keepers.append({
            "player_id": str(model.get("player_id") or research.get("player_id") or ""),
            "player_name": str(research["player_name"]),
            "team_id": team_id,
            "projected_minutes_mean": minutes_mean,
            "confidence": confidence,
            "fragility": fragility,
            "evidence_source_ids": evidence,
            "quant_input_receipt_sha256": receipt,
            "heads": heads,
        })

    if run_mode in {"ALL", "SAVES_ONLY"} and seen_keeper_teams != team_ids:
        raise ModelIntegrityError("save freeze requires one modeled goalkeeper per team")

    research_hash = sha256_json(research_context)
    artifact = {
        "schema_version": SCHEMA_VERSION,
        "model_version": "ALEAGUE_PLAYER_VOLUME_V1_0.3.0",
        "market_data": False,
        "run_mode": run_mode,
        "fixture_id": str(research_context["fixture_id"]),
        "pack_revision": str(research_context["pack_revision"]),
        "research_hash": research_hash,
        "frozen_at": _iso_or_now(frozen_at),
        "team_environment": team_environment,
        "outfield_players": frozen_outfield,
        "goalkeepers": frozen_keepers,
    }
    assert_market_blind(artifact)
    artifact["freeze_receipt_sha256"] = sha256_json(artifact)
    return artifact
