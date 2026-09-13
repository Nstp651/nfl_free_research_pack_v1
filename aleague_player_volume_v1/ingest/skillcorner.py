"""Pure parser/join logic for the pinned SkillCorner A-League open-data aggregates."""
from __future__ import annotations

import csv
import hashlib
import io
import math
import re
from typing import Any, Dict, Mapping

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

# Goalkeepers are retained and validated in the source artifact, but they are not
# members of the attacking-role feature universe. Their sparse/zero off-ball-run
# rows must therefore never dilute the completeness gate for an attacking model.
ATTACKING_EXCLUDED_POSITION_GROUPS = frozenset({"Goalkeeper"})

RoleKey = tuple[str, str, str]


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


def _identity(row: Mapping[str, str]) -> RoleKey:
    """SkillCorner aggregates are role-segmented, so position is part of identity.

    A player may legitimately have multiple aggregate rows for one team when they
    played materially different position groups. Keeping those rows separate is
    preferable to averaging away the role signal we intend to study.
    """
    player_id = str(row.get("player_id") or "").strip()
    team_id = str(row.get("team_id") or "").strip()
    position_group = str(row.get("position_group") or "").strip()
    if not player_id or not team_id or not position_group:
        raise ModelIntegrityError("SkillCorner player_id/team_id/position_group required")
    return player_id, team_id, position_group


def parse_aggregate(text: str, kind: str) -> Dict[RoleKey, Dict[str, Any]]:
    """Parse one aggregate CSV into one row per player-team-position identity."""
    if kind not in {"obr", "passing", "physical"}:
        raise ModelIntegrityError(f"unsupported SkillCorner aggregate kind {kind}")
    features = {"obr": OBR_FEATURES, "passing": PASSING_FEATURES, "physical": PHYSICAL_FEATURES}[kind]
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ModelIntegrityError("SkillCorner aggregate missing header")
    missing = [field for field in ("player_id", "player_name", "team_id", "team_name", "position_group", *features) if field not in reader.fieldnames]
    if missing:
        raise ModelIntegrityError(f"SkillCorner {kind} missing fields {missing}")
    out: Dict[RoleKey, Dict[str, Any]] = {}
    for raw in reader:
        competition = str(raw.get("competition_name") or "").strip()
        season = str(raw.get("season_name") or "").strip()
        if competition != EXPECTED_COMPETITION or season != EXPECTED_SEASON:
            raise ModelIntegrityError(f"unexpected SkillCorner competition/season {competition} {season}")
        key = _identity(raw)
        if key in out:
            raise ModelIntegrityError(f"duplicate SkillCorner {kind} role identity {key}")
        minutes_field = "minutes_full_all" if kind == "physical" else "minutes"
        out[key] = {
            "source_player_id": key[0],
            "source_team_id": key[1],
            "player_name": str(raw.get("player_name") or "").strip(),
            "player_birthdate": str(raw.get("player_birthdate") or "").strip() or None,
            "team_name": str(raw.get("team_name") or "").strip(),
            "position_group": key[2],
            "minutes": _num(raw.get(minutes_field)),
            "features": {field: _num(raw.get(field)) for field in features},
        }
    if not out:
        raise ModelIntegrityError(f"SkillCorner {kind} aggregate contains no rows")
    return out


def _profile_role_slug(position_group: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", position_group.casefold()).strip("_")
    if not slug:
        raise ModelIntegrityError("empty SkillCorner role slug")
    return slug


def build_role_profiles(
    obr: Mapping[RoleKey, Mapping[str, Any]],
    passing: Mapping[RoleKey, Mapping[str, Any]],
    physical: Mapping[RoleKey, Mapping[str, Any]],
) -> tuple[list[Dict[str, Any]], Dict[str, Any]]:
    """Join raw aggregate families by player-team-role without fitted composites.

    All rows are preserved in the output artifact. Coverage is reported two ways:
    an all-role diagnostic and the production attacking-role completeness rate.
    Only the latter is eligible for the attacking advanced-feature acceptance gate.
    """
    keys = sorted(
        set(obr) | set(passing) | set(physical),
        key=lambda x: (int(x[0]) if x[0].isdigit() else x[0], x[1], x[2]),
    )
    profiles: list[Dict[str, Any]] = []
    complete_all = 0
    complete_attacking = 0
    attacking_keys = [key for key in keys if key[2] not in ATTACKING_EXCLUDED_POSITION_GROUPS]
    players_with_multiple_roles: set[tuple[str, str]] = set()
    roles_per_player_team: Dict[tuple[str, str], set[str]] = {}
    for key in keys:
        roles_per_player_team.setdefault((key[0], key[1]), set()).add(key[2])
    for identity, roles in roles_per_player_team.items():
        if len(roles) > 1:
            players_with_multiple_roles.add(identity)

    for key in keys:
        sources = {"obr": obr.get(key), "passing": passing.get(key), "physical": physical.get(key)}
        present = [name for name, row in sources.items() if row is not None]
        is_complete = len(present) == 3
        if is_complete:
            complete_all += 1
            if key[2] not in ATTACKING_EXCLUDED_POSITION_GROUPS:
                complete_attacking += 1
        anchor = next(row for row in sources.values() if row is not None)
        for name, row in sources.items():
            if row is None:
                continue
            if (
                row["player_name"] != anchor["player_name"]
                or row["team_name"] != anchor["team_name"]
                or row["position_group"] != anchor["position_group"]
            ):
                raise ModelIntegrityError(f"SkillCorner identity disagreement for {key} in {name}")
        profiles.append({
            "schema_version": "aleague_skillcorner_role_profile_v1",
            "profile_id": f"skillcorner:{key[0]}:{key[1]}:{_profile_role_slug(key[2])}:2024-25",
            "season": "2024-25",
            "source_player_id": key[0],
            "source_team_id": key[1],
            "player_name": anchor["player_name"],
            "player_birthdate": anchor.get("player_birthdate"),
            "team_name": anchor["team_name"],
            "position_group": key[2],
            "source_presence": present,
            "minutes": {name: row.get("minutes") if row else None for name, row in sources.items()},
            "features": {
                name: dict(row.get("features") or {}) if row else None
                for name, row in sources.items()
            },
            "model_use": (
                "SOURCE_VALIDATION_ONLY"
                if key[2] in ATTACKING_EXCLUDED_POSITION_GROUPS
                else "ROLE_FEATURE_RESEARCH_ONLY_UNTIL_VALIDATED"
            ),
        })

    all_role_coverage = complete_all / len(keys) if keys else 0.0
    attacking_coverage = complete_attacking / len(attacking_keys) if attacking_keys else 0.0
    return profiles, {
        "profiles": len(profiles),
        "complete_three_family_profiles": complete_attacking,
        "complete_join_rate": attacking_coverage,
        "attacking_profiles": len(attacking_keys),
        "attacking_complete_three_family_profiles": complete_attacking,
        "attacking_complete_join_rate": attacking_coverage,
        "excluded_non_attacking_profiles": len(keys) - len(attacking_keys),
        "all_role_complete_three_family_profiles": complete_all,
        "all_role_complete_join_rate": all_role_coverage,
        "player_team_identities": len(roles_per_player_team),
        "player_team_identities_with_multiple_roles": len(players_with_multiple_roles),
        "obr_rows": len(obr),
        "passing_rows": len(passing),
        "physical_rows": len(physical),
    }
