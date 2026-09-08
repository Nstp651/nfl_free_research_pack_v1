from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.request import Request, urlopen

from nba_player_props_v1.source_receipt import canonical_json, sha256_bytes

RAW_URL = (
    "https://raw.githubusercontent.com/sportsdataverse/hoopR-nba-raw/"
    "main/nba/json/final/{game_id}.json"
)
CORE_FIELDS = (
    "assists",
    "field_goals_made",
    "field_goals_attempted",
    "three_point_field_goals_made",
    "three_point_field_goals_attempted",
    "free_throws_made",
    "free_throws_attempted",
)
REBOUND_FIELDS = ("rebounds", "offensive_rebounds", "defensive_rebounds")


def _team_id(play: dict) -> str:
    value = play.get("team.id")
    if value is None and isinstance(play.get("team"), dict):
        value = play["team"].get("id")
    return str(value or "")


def _type_text(play: dict) -> str:
    value = play.get("type.text")
    if value is None and isinstance(play.get("type"), dict):
        value = play["type"].get("text")
    return str(value or "")


def _participant(play: dict, index: int) -> str | None:
    value = play.get(f"participants.{index}.athlete.id")
    if value is not None:
        return str(value)
    rows = play.get("participants")
    if isinstance(rows, list) and len(rows) > index and isinstance(rows[index], dict):
        athlete = rows[index].get("athlete")
        if isinstance(athlete, dict) and athlete.get("id") is not None:
            return str(athlete["id"])
    return None


def _number(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def derive_pbp_team_stats(payload: dict) -> dict[str, dict]:
    plays = payload.get("plays")
    if not isinstance(plays, list) or not plays:
        raise ValueError("final game payload missing plays")
    out: dict[str, dict] = {}

    def row(team: str) -> dict:
        return out.setdefault(
            team,
            {
                "assists": 0,
                "field_goals_made": 0,
                "field_goals_attempted": 0,
                "three_point_field_goals_made": 0,
                "three_point_field_goals_attempted": 0,
                "free_throws_made": 0,
                "free_throws_attempted": 0,
                "player_rebounds": 0,
                "player_offensive_rebounds": 0,
                "player_defensive_rebounds": 0,
                "team_rebounds": 0,
                "team_offensive_rebounds": 0,
                "team_defensive_rebounds": 0,
            },
        )

    for play in plays:
        if not isinstance(play, dict):
            continue
        team = _team_id(play)
        if not team:
            continue
        stats = row(team)
        kind = _type_text(play).lower()
        scoring = bool(play.get("scoringPlay"))
        shooting = bool(play.get("shootingPlay"))
        attempted = _number(play.get("pointsAttempted"))
        score_value = _number(play.get("scoreValue"))
        is_free_throw = "free throw" in kind

        if is_free_throw:
            stats["free_throws_attempted"] += 1
            if scoring and score_value == 1:
                stats["free_throws_made"] += 1
        elif shooting and attempted in (2, 3):
            stats["field_goals_attempted"] += 1
            if attempted == 3:
                stats["three_point_field_goals_attempted"] += 1
            if scoring and score_value in (2, 3):
                stats["field_goals_made"] += 1
                if score_value == 3:
                    stats["three_point_field_goals_made"] += 1
                if _participant(play, 1) is not None:
                    stats["assists"] += 1

        if "rebound" in kind:
            offensive = "offensive" in kind
            defensive = "defensive" in kind
            player_attributed = _participant(play, 0) is not None
            if player_attributed:
                stats["player_rebounds"] += 1
                if offensive:
                    stats["player_offensive_rebounds"] += 1
                if defensive:
                    stats["player_defensive_rebounds"] += 1
            else:
                stats["team_rebounds"] += 1
                if offensive:
                    stats["team_offensive_rebounds"] += 1
                if defensive:
                    stats["team_defensive_rebounds"] += 1
    return out


def _mismatch_units(source_report: dict) -> dict[tuple[str, str], dict]:
    fields = (source_report.get("raw_player_to_team_reconciliation") or {}).get(
        "exact_fields"
    ) or {}
    units: dict[tuple[str, str], dict] = {}
    for field, detail in fields.items():
        for item in detail.get("mismatch_sample") or []:
            game = str(item["game_id_espn"])
            team = str(item["team_id_espn"])
            units.setdefault((game, team), {})[field] = {
                "raw": float(item[f"raw_{field}"]),
                "team": float(item[field]),
            }
    return units


def _fetch_final(game_id: str) -> tuple[dict, dict]:
    url = RAW_URL.format(game_id=game_id)
    request = Request(
        url,
        headers={"User-Agent": "NBA-V1-final-box-adjudication/1.0", "Accept": "application/json"},
    )
    with urlopen(request, timeout=60) as response:
        raw = response.read()
        http_status = response.status
    payload = json.loads(raw)
    if str(payload.get("gameId") or payload.get("game_id") or "") != game_id:
        raise ValueError(f"final payload identity mismatch for {game_id}")
    receipt = {
        "url": url,
        "http_status": http_status,
        "bytes": len(raw),
        "sha256": sha256_bytes(raw),
    }
    return payload, receipt


def _adjudicate_field(field: str, values: dict, pbp: dict) -> dict:
    raw, team = values["raw"], values["team"]
    if field in CORE_FIELDS:
        final_value = float(pbp[field])
        if final_value == raw and final_value != team:
            decision = "RAW_PLAYER_RELEASE_CONFIRMED_TEAM_RELEASE_DIFFERS"
        elif final_value == team and final_value != raw:
            decision = "TEAM_RELEASE_CONFIRMED_PLAYER_RELEASE_STALE"
        elif final_value == raw == team:
            decision = "BOTH_RELEASES_CONFIRMED"
        else:
            decision = "UNRESOLVED"
        return {**values, "final_pbp": final_value, "decision": decision}

    mapping = {
        "rebounds": ("player_rebounds", "team_rebounds"),
        "offensive_rebounds": ("player_offensive_rebounds", "team_offensive_rebounds"),
        "defensive_rebounds": ("player_defensive_rebounds", "team_defensive_rebounds"),
    }
    player_key, team_key = mapping[field]
    player_final = float(pbp[player_key])
    team_only = float(pbp[team_key])
    total_final = player_final + team_only
    if player_final == raw and total_final == team:
        decision = "TEAM_REBOUND_ACCOUNTING_CONFIRMED"
    elif player_final == raw and team_only == 0 and team != raw:
        decision = "TEAM_RELEASE_DIFFERS_FROM_FINAL_PLAYER_REBOUNDS"
    elif total_final == team and player_final != raw:
        decision = "TEAM_RELEASE_CONFIRMED_PLAYER_RELEASE_STALE"
    else:
        decision = "UNRESOLVED"
    return {
        **values,
        "final_pbp_player": player_final,
        "final_pbp_team_only": team_only,
        "final_pbp_total": total_final,
        "decision": decision,
    }


def adjudicate(source_report: dict) -> dict:
    units = _mismatch_units(source_report)
    by_game: dict[str, tuple[dict, dict]] = {}
    rows = []
    stale_player_units = set()
    unresolved_units = set()

    for (game, team), fields in sorted(units.items()):
        if game not in by_game:
            payload, receipt = _fetch_final(game)
            by_game[game] = (derive_pbp_team_stats(payload), receipt)
        pbp_by_team, _ = by_game[game]
        if team not in pbp_by_team:
            raise ValueError(f"final PBP team {team} missing for game {game}")
        decisions = {
            field: _adjudicate_field(field, values, pbp_by_team[team])
            for field, values in sorted(fields.items())
        }
        decision_values = {detail["decision"] for detail in decisions.values()}
        if "TEAM_RELEASE_CONFIRMED_PLAYER_RELEASE_STALE" in decision_values:
            stale_player_units.add((game, team))
        if "UNRESOLVED" in decision_values:
            unresolved_units.add((game, team))
        rows.append({"game_id_espn": game, "team_id_espn": team, "fields": decisions})

    status = "PASS" if not unresolved_units else "FAIL"
    receipts = {game: receipt for game, (_, receipt) in sorted(by_game.items())}
    report = {
        "schema_version": "nba_final_box_adjudication_v1",
        "market_data": False,
        "status": status,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "mismatch_game_team_units": len(units),
        "stale_player_release_units": [
            {"game_id_espn": game, "team_id_espn": team}
            for game, team in sorted(stale_player_units)
        ],
        "unresolved_units": [
            {"game_id_espn": game, "team_id_espn": team}
            for game, team in sorted(unresolved_units)
        ],
        "game_payload_receipts": receipts,
        "adjudications": rows,
        "rule": (
            "NO TOLERANCE: every release mismatch must be explained by final PBP; "
            "player-release-stale units require model-history quarantine and rebuild"
        ),
    }
    report["receipt_sha256"] = sha256_bytes(canonical_json(report))
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-report", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    source = json.loads(Path(args.source_report).read_text())
    report = adjudicate(source)
    Path(args.output).write_bytes(canonical_json(report) + b"\n")
    print(
        json.dumps(
            {
                "status": report["status"],
                "mismatch_game_team_units": report["mismatch_game_team_units"],
                "stale_player_release_units": report["stale_player_release_units"],
                "unresolved_units": report["unresolved_units"],
                "receipt_sha256": report["receipt_sha256"],
            }
        )
    )


if __name__ == "__main__":
    main()
