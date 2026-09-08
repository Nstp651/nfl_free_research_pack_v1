"""Pure parser/join logic for the pinned SkillCorner A-League open-data aggregates."""
from __future__ import annotations

import csv
import hashlib
import io
import math
from typing import Any, Dict, Iterable, Mapping

from ..model_core import ModelIntegrityError


APPROVED_COMMIT = "c1e17a0cc3e07e1774b52d929c1a0b85115143fc"
EXPECTED_COMPETITION = "AUS - A-League"
EXPECTED_SEASON = "2024/2025"

OBR_FEATURES = (
    "offballrun_count_p30tip",
    "behindrun_count_p30tip",
    "aheadoftheballrun_count_p30tip",
    "offballrun_count_shotwithin10s_p30tip",
    "behindrun_count_shotwithin10s_p30tip",
    "offballrun_count_targeted_p30tip",
    "offballrun_count_received_p30tip",
    "offballrun_count_penaltyarea_p30tip",
    "offballrun_count_dangerous_p30tip",
    "offballrun_count_dangerous_targeted_p30tip",
    "offballrun_count_dangerous_received_p30tip",
)
PASSING_FEATURES = (
    "passopportunity_count_p30tip",
    "pass_count_shotwithin10s_p30tip",
    "pass_count_attempted_p30tip",
    "pass_count_completed_p30tip",
    "pass_pct_completed",
    "passopportunity_count_torun_p30tip",
    "pass_count_torun_attempted_p30tip",
    "pass_count_torun_completed_p30tip",
    "pass_count_torun_shotwithin10s_p30tip",
    "passopportunity_count_dangerous_p30tip",
    "pass_count_dangerous_attempted_p30tip",
)
PHYSICAL_FEATURES = (
    "total_metersperminute_full_all",
    "hsr_count_full_all",
    "sprint_count_full_all",
    "hi_count_full_all",
    "psv99",
    "total_metersperminute_full_tip",
    "hsr_count_full_tip",
    "sprint_count_full_tip",
)


def git_blob_sha1(content: bytes) -> str:
    """Compute the Git object id for raw file bytes."""
    header = f"blob {len(content)}\0".encode("ascii")
    return hashlib.sha1(header + content).hexdigest()


def verify_git_blob(content: bytes, expected_sha: str) -> None:
    actual = git_blob_sha1(content)
    if actual != str(expected_sha):
        raise ModelIntegrityError(f"SkillCorner blob mismatch: expected {expected_sha}, got {actual}")


def _num(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError as exc:
        raise ModelIntegrityError(f"non-numeric SkillCorner feature {value!r}") from exc
    if not math.isfinite(number):
        raise ModelIntegrityError("non-finite SkillCorner feature")
    return number


def _identity(row: Mapping[str, str]) -> tuple[str, str]:
    player_id = str(row.get("player_id") or "").strip()
    team_id = str(row.get("team_id") or "").strip()
    if not player_id or not team_id:
        raise ModelIntegrityError("SkillCorner player_id/team_id required")
    return player_id, team_id


def parse_aggregate(text: str, kind: str) -> Dict[tuple[str, str], Dict[str, Any]]:
    """Parse one aggregate CSV into one row per player-team identity."""
    if kind not in {"obr", "passing", "physical"}:
        raise ModelIntegrityError(f"unsupported SkillCorner aggregate kind {kind}")
    features = {"obr": OBR_FEATURES, "passing": PASSING_FEATURES, "physical": PHYSICAL_FEATURES}[kind]
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ModelIntegrityError("SkillCorner aggregate missing header")
    missing = [field for field in ("player_id", "player_name", "team_id", "team_name", "position_group", *features) if field not in reader.fieldnames]
    if missing:
        raise ModelIntegrityError(f"SkillCorner {kind} missing fields {missing}")
    out: Dict[tuple[str, str], Dict[str, Any]] = {}
    for raw in reader:
        competition = str(raw.get("competition_name") or "").strip()
        season = str(raw.get("season_name") or "").strip()
        if competition != EXPECTED_COMPETITION or season != EXPECTED_SEASON:
            raise ModelIntegrityError(f"unexpected SkillCorner competition/season {competition} {season}")
        key = _identity(raw)
        if key in out:
            raise ModelIntegrityError(f"duplicate SkillCorner {kind} identity {key}")
        minutes_field = "minutes_full_all" if kind == "physical" else "minutes"
        out[key] = {
            "source_player_id": key[0],
            "source_team_id": key[1],
            "player_name": str(raw.get("player_name") or "").strip(),
            "player_birthdate": str(raw.get("player_birthdate") or "").strip() or None,
            "team_name": str(raw.get("team_name") or "").strip(),
            "position_group": str(raw.get("position_group") or "").strip(),
            "minutes": _num(raw.get(minutes_field)),
            "features": {field: _num(raw.get(field)) for field in features},
        }
    if not out:
        raise ModelIntegrityError(f"SkillCorner {kind} aggregate contains no rows")
    return out


def build_role_profiles(
    obr: Mapping[tuple[str, str], Mapping[str, Any]],
    passing: Mapping[tuple[str, str], Mapping[str, Any]],
    physical: Mapping[tuple[str, str], Mapping[str, Any]],
) -> tuple[list[Dict[str, Any]], Dict[str, Any]]:
    """Join raw aggregate families without inventing a fitted composite score."""
    keys = sorted(set(obr) | set(passing) | set(physical), key=lambda x: (int(x[0]) if x[0].isdigit() else x[0], x[1]))
    profiles: list[Dict[str, Any]] = []
    complete = 0
    for key in keys:
        sources = {"obr": obr.get(key), "passing": passing.get(key), "physical": physical.get(key)}
        present = [name for name, row in sources.items() if row is not None]
        if len(present) == 3:
            complete += 1
        anchor = next(row for row in sources.values() if row is not None)
        for name, row in sources.items():
            if row is None:
                continue
            if row["player_name"] != anchor["player_name"] or row["team_name"] != anchor["team_name"]:
                raise ModelIntegrityError(f"SkillCorner identity disagreement for {key} in {name}")
        profiles.append({
            "schema_version": "aleague_skillcorner_role_profile_v1",
            "profile_id": f"skillcorner:{key[0]}:{key[1]}:2024-25",
            "season": "2024-25",
            "source_player_id": key[0],
            "source_team_id": key[1],
            "player_name": anchor["player_name"],
            "player_birthdate": anchor.get("player_birthdate"),
            "team_name": anchor["team_name"],
            "position_group": anchor["position_group"],
            "source_presence": present,
            "minutes": {name: row.get("minutes") if row else None for name, row in sources.items()},
            "features": {
                name: dict(row.get("features") or {}) if row else None
                for name, row in sources.items()
            },
            "model_use": "ROLE_FEATURE_RESEARCH_ONLY_UNTIL_VALIDATED",
        })
    coverage = complete / len(keys) if keys else 0.0
    return profiles, {
        "profiles": len(profiles),
        "complete_three_family_profiles": complete,
        "complete_join_rate": coverage,
        "obr_rows": len(obr),
        "passing_rows": len(passing),
        "physical_rows": len(physical),
    }
