#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from source_client import market_key_hits


def _team(fixture: dict[str, Any], side: str) -> dict[str, Any]:
    value = fixture.get(f"{side}_team")
    return value if isinstance(value, dict) else {}


def validate(pack: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if pack.get("schema_version") != "0.1.0":
        errors.append("schema_version must be 0.1.0")
    if pack.get("market_data") is not False:
        errors.append("market_data must be false")
    if not pack.get("pack_revision"):
        errors.append("pack_revision missing")
    fixture = pack.get("fixture") if isinstance(pack.get("fixture"), dict) else {}
    if not fixture.get("id"):
        errors.append("fixture id missing")
    for side in ("home", "away"):
        team = _team(fixture, side)
        if not team.get("id") or not team.get("name"):
            errors.append(f"fixture {side}_team id/name missing")
        roster = pack.get("rosters", {}).get(side, [])
        profiles = pack.get("player_profiles", {}).get(side, [])
        if not isinstance(roster, list) or not isinstance(profiles, list):
            errors.append(f"{side} roster/profiles malformed")
            continue
        if len(roster) != len(profiles):
            errors.append(f"{side} roster/profile count mismatch")
        seen: set[str] = set()
        for p in profiles:
            pid = p.get("player_id")
            name = p.get("player_name")
            if not pid and not name:
                errors.append(f"{side} player has no identity")
            key = str(pid or str(name).lower())
            if key in seen:
                errors.append(f"duplicate {side} player identity {key}")
            seen.add(key)
            for field in ("season_stats", "current_game_log", "prior_nbl_game_log"):
                if not isinstance(p.get(field, []), list):
                    errors.append(f"{side} player {key} {field} not list")
    hits = market_key_hits(pack)
    if hits:
        errors.append("market-key contamination: " + ", ".join(hits[:10]))
    return errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    args = ap.parse_args()
    path = Path(args.path)
    pack = json.loads(path.read_text(encoding="utf-8"))
    errors = validate(pack)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    print(json.dumps({
        "ok": not errors,
        "errors": errors,
        "file_sha256": digest,
        "pack_revision": pack.get("pack_revision"),
        "fixture_id": (pack.get("fixture") or {}).get("id"),
    }, sort_keys=True))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
