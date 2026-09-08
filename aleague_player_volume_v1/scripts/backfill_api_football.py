#!/usr/bin/env python3
"""Quota-aware API-Football historical backfill for A-League Men."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Mapping

from aleague_player_volume_v1.ingest.api_football import (
    ALEAGUE_MEN_LEAGUE_ID,
    MAX_BATCH_FIXTURE_IDS,
    ApiFootballClient,
    canonical_dicts,
    fixture_metadata,
    parse_fixture_players,
    parse_fixture_team_statistics,
    reconcile_fixture,
)
from aleague_player_volume_v1.publication import build_manifest, write_jsonl


def chunks(values: List[int], size: int = MAX_BATCH_FIXTURE_IDS):
    for index in range(0, len(values), size):
        yield values[index:index + size]


def coverage_gate(payload: Dict[str, Any], season: int) -> Dict[str, Any]:
    response = payload.get("response") or []
    if len(response) != 1:
        raise RuntimeError(f"A-League league coverage not resolved for season {season}")
    seasons = response[0].get("seasons") or []
    selected = next((item for item in seasons if int(item.get("year", -1)) == season), None)
    if not selected:
        raise RuntimeError(f"API-Football season {season} is not available")
    coverage = selected.get("coverage") or {}
    fixtures = coverage.get("fixtures") or {}
    required = {
        "statistics_fixtures": fixtures.get("statistics_fixtures"),
        "statistics_players": fixtures.get("statistics_players"),
    }
    missing = [key for key, value in required.items() if value is not True]
    if missing:
        raise RuntimeError(f"A-League {season} missing required API coverage: {missing}")
    return {"coverage": coverage, "required": required}


def embedded_payload(entry: Mapping[str, Any], key: str) -> Dict[str, Any] | None:
    value = entry.get(key)
    if isinstance(value, list) and value:
        return {"response": value}
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--output-root", default="aleague_player_volume_v1/data/canonical")
    parser.add_argument("--min-coverage-rate", type=float, default=0.97)
    parser.add_argument("--allow-endpoint-fallback", action="store_true")
    args = parser.parse_args()

    key = os.getenv("API_FOOTBALL_KEY", "")
    if not key:
        raise SystemExit("API_FOOTBALL_KEY is required")
    client = ApiFootballClient(key)
    coverage_receipt = coverage_gate(client.league(args.season), args.season)
    fixtures_payload = client.fixtures(args.season)
    entries = fixtures_payload.get("response") or []
    completed = [entry for entry in entries if ((entry.get("fixture") or {}).get("status") or {}).get("short") in {"FT", "AET", "PEN"}]
    if not completed:
        raise RuntimeError("no completed A-League fixtures returned")

    detail_by_provider_id: Dict[int, Mapping[str, Any]] = {}
    completed_ids = [int((entry.get("fixture") or {})["id"]) for entry in completed]
    for batch_ids in chunks(completed_ids):
        for detail in client.fixture_batch(batch_ids).get("response") or []:
            fixture_id = int((detail.get("fixture") or {}).get("id"))
            detail_by_provider_id[fixture_id] = detail

    team_rows = []
    player_rows = []
    keeper_rows = []
    player_names: Dict[str, str] = {}
    reconciliation = []
    usable = 0
    dedicated_fallback_calls = 0

    for original in completed:
        metadata = fixture_metadata(original, args.season)
        fixture_id = int(metadata["provider_fixture_id"])
        detail = detail_by_provider_id.get(fixture_id, original)
        players_payload = embedded_payload(detail, "players")
        stats_payload = embedded_payload(detail, "statistics")
        if players_payload is None or stats_payload is None:
            if not args.allow_endpoint_fallback:
                reconciliation.append({"fixture_id": metadata["fixture_id"], "usable": False, "error": "BATCH_DETAIL_MISSING"})
                continue
            if players_payload is None:
                players_payload = client.fixture_players(fixture_id)
                dedicated_fallback_calls += 1
            if stats_payload is None:
                stats_payload = client.fixture_statistics(fixture_id)
                dedicated_fallback_calls += 1
        try:
            players, keepers, names = parse_fixture_players(metadata, players_payload)
            teams = parse_fixture_team_statistics(metadata, stats_payload)
        except Exception as exc:
            reconciliation.append({"fixture_id": metadata["fixture_id"], "usable": False, "error": type(exc).__name__})
            continue
        receipt = reconcile_fixture(teams, players, keepers)
        receipt.update({"fixture_id": metadata["fixture_id"], "usable": True})
        reconciliation.append(receipt)
        team_rows.extend(teams)
        player_rows.extend(players)
        keeper_rows.extend(keepers)
        player_names.update(names)
        usable += 1

    coverage_rate = usable / len(completed)
    if coverage_rate < args.min_coverage_rate:
        raise RuntimeError(
            f"usable fixture coverage {coverage_rate:.3%} below gate {args.min_coverage_rate:.3%}; "
            "inspect reconciliation before enabling endpoint fallback"
        )

    season_label = f"{args.season}-{str(args.season + 1)[-2:]}"
    base = Path(args.output_root) / season_label
    assets = [
        write_jsonl(base / "team_match_shooting.jsonl", canonical_dicts(team_rows)),
        write_jsonl(base / "player_match_shooting.jsonl", canonical_dicts(player_rows)),
        write_jsonl(base / "goalkeeper_match.jsonl", canonical_dicts(keeper_rows)),
        write_jsonl(base / "player_identity.jsonl", ({"player_id": k, "name": v} for k, v in player_names.items())),
        write_jsonl(base / "reconciliation.jsonl", reconciliation),
    ]
    model_root = Path("aleague_player_volume_v1")
    for asset in assets:
        asset["path"] = str(Path(asset["path"]).relative_to(model_root))
    manifest = build_manifest(
        source_id="api_football",
        season=season_label,
        assets=assets,
        source_receipt={
            "league_id": ALEAGUE_MEN_LEAGUE_ID,
            "requested_season": args.season,
            "completed_fixtures": len(completed),
            "usable_fixtures": usable,
            "usable_coverage_rate": coverage_rate,
            "batch_requests": (len(completed_ids) + MAX_BATCH_FIXTURE_IDS - 1) // MAX_BATCH_FIXTURE_IDS,
            "dedicated_fallback_calls": dedicated_fallback_calls,
            **coverage_receipt,
        },
    )
    (base / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "season": season_label, "coverage_rate": coverage_rate, "manifest": str(base / "manifest.json")}, indent=2))


if __name__ == "__main__":
    main()
