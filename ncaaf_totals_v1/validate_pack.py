#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

SCHEMA_VERSION = "0.1.0"
DENY_KEY = re.compile(r"(?:odds|spread|moneyline|betting|sportsbook|bookmaker|over_under|total_line|line_price)", re.I)


def walk_market_keys(value, path="root"):
    hits = []
    if isinstance(value, dict):
        for k, v in value.items():
            if DENY_KEY.search(str(k)):
                hits.append(f"{path}.{k}")
            hits.extend(walk_market_keys(v, f"{path}.{k}"))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            hits.extend(walk_market_keys(v, f"{path}[{i}]"))
    return hits


def finite_json(value, path="root"):
    bad = []
    if isinstance(value, dict):
        for k, v in value.items():
            bad.extend(finite_json(v, f"{path}.{k}"))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            bad.extend(finite_json(v, f"{path}[{i}]"))
    elif isinstance(value, float) and not math.isfinite(value):
        bad.append(path)
    return bad


def validate(data_dir: Path) -> dict:
    errors = []
    manifest_path = data_dir / "manifest.json"
    if not manifest_path.exists():
        return {"ok": False, "errors": ["manifest.json missing"]}
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema_version") != SCHEMA_VERSION:
        errors.append("manifest schema_version mismatch")
    if manifest.get("market_data") is not False:
        errors.append("manifest market_data must be false")
    slates = manifest.get("slates")
    if not isinstance(slates, list) or not slates:
        errors.append("manifest slates missing/empty")
        return {"ok": False, "errors": errors}
    if len({s.get("slate_id") for s in slates}) != len(slates):
        errors.append("duplicate slate_id in manifest")

    total_games = 0
    for entry in slates:
        season = entry.get("season")
        week = entry.get("week")
        slate_id = entry.get("slate_id")
        p = data_dir / "slates" / str(season) / f"{slate_id}.json"
        if not p.exists():
            errors.append(f"missing slate file {p}")
            continue
        pack = json.loads(p.read_text())
        if pack.get("schema_version") != SCHEMA_VERSION:
            errors.append(f"{slate_id}: schema mismatch")
        if pack.get("market_data") is not False:
            errors.append(f"{slate_id}: market_data must be false")
        if pack.get("pack_revision") != entry.get("pack_revision"):
            errors.append(f"{slate_id}: revision mismatch")
        if pack.get("season") != season or pack.get("week") != week:
            errors.append(f"{slate_id}: season/week mismatch")
        cutoff = week - 1
        through = pack.get("data_state", {}).get("current_season_data_through_week")
        if through is not None and through > cutoff:
            errors.append(f"{slate_id}: leakage cutoff failed ({through}>{cutoff})")
        games = pack.get("games")
        if not isinstance(games, list) or not games:
            errors.append(f"{slate_id}: games missing/empty")
            continue
        total_games += len(games)
        ids = [g.get("game_id") for g in games]
        if None in ids or len(set(ids)) != len(ids):
            errors.append(f"{slate_id}: null/duplicate game_id")
        for g in games:
            fixture = g.get("fixture", {})
            if fixture.get("fbs_game") is not True:
                errors.append(f"{slate_id}/{g.get('game_id')}: non-FBS game")
            if not fixture.get("home_id") or not fixture.get("away_id"):
                errors.append(f"{slate_id}/{g.get('game_id')}: missing team id")
            for side in ("home_profile", "away_profile"):
                prof = g.get(side, {})
                if not prof.get("team_id"):
                    errors.append(f"{slate_id}/{g.get('game_id')}: missing {side} team_id")
        hits = walk_market_keys(pack)
        if hits:
            errors.append(f"{slate_id}: market-key boundary violation: {hits[:10]}")
        bad = finite_json(pack)
        if bad:
            errors.append(f"{slate_id}: non-finite JSON values: {bad[:10]}")

    expected = manifest.get("fixture_count")
    if isinstance(expected, int) and expected != total_games:
        errors.append(f"fixture_count mismatch: manifest={expected} actual={total_games}")
    return {"ok": not errors, "slates": len(slates), "games": total_games, "errors": errors}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="ncaaf_totals_v1/data")
    args = ap.parse_args()
    result = validate(Path(args.data))
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
