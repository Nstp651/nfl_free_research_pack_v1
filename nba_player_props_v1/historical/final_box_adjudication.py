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
ALL_FIELDS = (
    "assists",
    "rebounds",
    "offensive_rebounds",
    "defensive_rebounds",
    "field_goals_made",
    "field_goals_attempted",
    "three_point_field_goals_made",
    "three_point_field_goals_attempted",
    "free_throws_made",
    "free_throws_attempted",
)
REBOUND_FIELDS = {"rebounds", "offensive_rebounds", "defensive_rebounds"}
PAIR_KEYS = {
    "fieldGoalsMade-fieldGoalsAttempted": ("field_goals_made", "field_goals_attempted"),
    "threePointFieldGoalsMade-threePointFieldGoalsAttempted": (
        "three_point_field_goals_made",
        "three_point_field_goals_attempted",
    ),
    "freeThrowsMade-freeThrowsAttempted": ("free_throws_made", "free_throws_attempted"),
}
SINGLE_KEYS = {
    "assists": "assists",
    "rebounds": "rebounds",
    "totalRebounds": "rebounds",
    "offensiveRebounds": "offensive_rebounds",
    "defensiveRebounds": "defensive_rebounds",
}


def _empty_stats() -> dict[str, float]:
    return {field: 0.0 for field in ALL_FIELDS}


def _number(value) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").strip().replace(",", "")
    if not text or text in {"--", "-", "DNP"}:
        return 0.0
    return float(text)


def _pair(value) -> tuple[float, float]:
    text = str(value or "").strip()
    if not text or text in {"--", "-"}:
        return 0.0, 0.0
    parts = text.split("-")
    if len(parts) != 2:
        raise ValueError(f"invalid made-attempted stat {value!r}")
    return _number(parts[0]), _number(parts[1])


def _team_stats(team_row: dict) -> dict[str, float]:
    out = _empty_stats()
    stats = team_row.get("statistics")
    if not isinstance(stats, list):
        raise ValueError("final team box missing statistics")
    seen = set()
    for item in stats:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        if name in PAIR_KEYS:
            made_key, attempt_key = PAIR_KEYS[name]
            made, attempted = _pair(item.get("displayValue"))
            out[made_key], out[attempt_key] = made, attempted
            seen.update((made_key, attempt_key))
        elif name in SINGLE_KEYS:
            key = SINGLE_KEYS[name]
            out[key] = _number(item.get("value", item.get("displayValue")))
            seen.add(key)
    missing = sorted(set(ALL_FIELDS).difference(seen))
    if missing:
        raise ValueError(f"final team box missing required stats {missing}")
    if out["offensive_rebounds"] + out["defensive_rebounds"] != out["rebounds"]:
        raise ValueError("final team box ORB + DRB != REB")
    return out


def _player_group_stats(group: dict) -> dict[str, float]:
    out = _empty_stats()
    sections = group.get("statistics")
    if not isinstance(sections, list) or not sections:
        raise ValueError("final player box missing statistics group")
    rows_seen = 0
    keys_seen = set()
    for section in sections:
        if not isinstance(section, dict):
            continue
        keys = section.get("keys")
        athletes = section.get("athletes")
        if not isinstance(keys, list) or not isinstance(athletes, list):
            continue
        index = {str(key): i for i, key in enumerate(keys)}
        required = {
            "assists",
            "rebounds",
            "offensiveRebounds",
            "defensiveRebounds",
            *PAIR_KEYS.keys(),
        }
        if not required.issubset(index):
            continue
        keys_seen.update(required)
        for row in athletes:
            if not isinstance(row, dict) or bool(row.get("didNotPlay")):
                continue
            values = row.get("stats")
            if not isinstance(values, list) or len(values) < len(keys):
                raise ValueError("final player stat row malformed")
            rows_seen += 1
            out["assists"] += _number(values[index["assists"]])
            out["rebounds"] += _number(values[index["rebounds"]])
            out["offensive_rebounds"] += _number(values[index["offensiveRebounds"]])
            out["defensive_rebounds"] += _number(values[index["defensiveRebounds"]])
            for source_key, (made_key, attempt_key) in PAIR_KEYS.items():
                made, attempted = _pair(values[index[source_key]])
                out[made_key] += made
                out[attempt_key] += attempted
    if rows_seen == 0 or len(keys_seen) < 7:
        raise ValueError("final player box has no usable played rows")
    if out["offensive_rebounds"] + out["defensive_rebounds"] != out["rebounds"]:
        raise ValueError("final player box ORB + DRB != REB")
    return out


def derive_final_box_stats(payload: dict) -> dict[str, dict]:
    box = payload.get("boxscore")
    if not isinstance(box, dict):
        raise ValueError("final game payload missing boxscore")
    teams = box.get("teams")
    players = box.get("players")
    if not isinstance(teams, list) or len(teams) != 2:
        raise ValueError("final boxscore must contain two teams")
    if not isinstance(players, list) or len(players) != 2:
        raise ValueError("final boxscore must contain two player groups")

    out: dict[str, dict] = {}
    for item in teams:
        team = item.get("team") if isinstance(item, dict) else None
        team_id = str((team or {}).get("id") or "")
        if not team_id:
            raise ValueError("final team identity missing")
        out.setdefault(team_id, {})["team"] = _team_stats(item)
    for group in players:
        team = group.get("team") if isinstance(group, dict) else None
        team_id = str((team or {}).get("id") or "")
        if not team_id or team_id not in out:
            raise ValueError("final player group identity mismatch")
        out[team_id]["player"] = _player_group_stats(group)

    for team_id, values in out.items():
        if "player" not in values or "team" not in values:
            raise ValueError(f"final box incomplete for team {team_id}")
        values["team_only_rebounds"] = {
            "rebounds": values["team"]["rebounds"] - values["player"]["rebounds"],
            "offensive_rebounds": values["team"]["offensive_rebounds"]
            - values["player"]["offensive_rebounds"],
            "defensive_rebounds": values["team"]["defensive_rebounds"]
            - values["player"]["defensive_rebounds"],
        }
        if min(values["team_only_rebounds"].values()) < 0:
            raise ValueError(f"final team rebound total below player sum for team {team_id}")
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
        headers={
            "User-Agent": "NBA-V1-final-box-adjudication/2.0",
            "Accept": "application/json",
        },
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


def _adjudicate_field(field: str, values: dict, final: dict) -> dict:
    raw = float(values["raw"])
    team_release = float(values["team"])
    final_player = float(final["player"][field])
    final_team = float(final["team"][field])
    raw_confirmed = raw == final_player
    team_confirmed = team_release == final_team

    if field in REBOUND_FIELDS:
        team_only = float(final["team_only_rebounds"][field])
        if raw_confirmed and team_confirmed:
            decision = "FINAL_PLAYER_AND_TEAM_RELEASES_CONFIRMED_TEAM_REBOUND_ACCOUNTING"
        elif not raw_confirmed and team_confirmed:
            decision = "TEAM_RELEASE_CONFIRMED_PLAYER_RELEASE_STALE"
        elif raw_confirmed and not team_confirmed:
            decision = "PLAYER_RELEASE_CONFIRMED_TEAM_RELEASE_STALE"
        else:
            decision = "UNRESOLVED"
        return {
            **values,
            "final_player_box": final_player,
            "final_team_box": final_team,
            "final_team_only_rebounds": team_only,
            "raw_player_release_confirmed": raw_confirmed,
            "team_release_confirmed": team_confirmed,
            "decision": decision,
        }

    # Core counted stats have no legitimate team-only accounting bucket. If the
    # final player sum and final team total disagree, the final box is internally
    # inconsistent and the unit remains blocked even if one release matches.
    if final_player != final_team:
        decision = "UNRESOLVED_FINAL_BOX_INTERNAL_MISMATCH"
    elif raw_confirmed and team_confirmed:
        decision = "BOTH_RELEASES_CONFIRMED"
    elif not raw_confirmed and team_confirmed:
        decision = "TEAM_RELEASE_CONFIRMED_PLAYER_RELEASE_STALE"
    elif raw_confirmed and not team_confirmed:
        decision = "PLAYER_RELEASE_CONFIRMED_TEAM_RELEASE_STALE"
    else:
        decision = "UNRESOLVED"
    return {
        **values,
        "final_player_box": final_player,
        "final_team_box": final_team,
        "raw_player_release_confirmed": raw_confirmed,
        "team_release_confirmed": team_confirmed,
        "decision": decision,
    }


def adjudicate(source_report: dict) -> dict:
    units = _mismatch_units(source_report)
    by_game: dict[str, tuple[dict, dict]] = {}
    rows = []
    stale_player_units = set()
    stale_team_units = set()
    unresolved_units = set()

    for (game, team), fields in sorted(units.items()):
        if game not in by_game:
            payload, receipt = _fetch_final(game)
            by_game[game] = (derive_final_box_stats(payload), receipt)
        final_by_team, _ = by_game[game]
        if team not in final_by_team:
            raise ValueError(f"final box team {team} missing for game {game}")
        decisions = {
            field: _adjudicate_field(field, values, final_by_team[team])
            for field, values in sorted(fields.items())
        }
        decision_values = {detail["decision"] for detail in decisions.values()}
        if "TEAM_RELEASE_CONFIRMED_PLAYER_RELEASE_STALE" in decision_values:
            stale_player_units.add((game, team))
        if "PLAYER_RELEASE_CONFIRMED_TEAM_RELEASE_STALE" in decision_values:
            stale_team_units.add((game, team))
        if any(value.startswith("UNRESOLVED") for value in decision_values):
            unresolved_units.add((game, team))
        rows.append(
            {
                "game_id_espn": game,
                "team_id_espn": team,
                "fields": decisions,
            }
        )

    status = "PASS" if not unresolved_units else "FAIL"
    receipts = {game: receipt for game, (_, receipt) in sorted(by_game.items())}
    report = {
        "schema_version": "nba_final_box_adjudication_v2",
        "market_data": False,
        "status": status,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "mismatch_game_team_units": len(units),
        "stale_player_release_units": [
            {"game_id_espn": game, "team_id_espn": team}
            for game, team in sorted(stale_player_units)
        ],
        "stale_team_release_units": [
            {"game_id_espn": game, "team_id_espn": team}
            for game, team in sorted(stale_team_units)
        ],
        "unresolved_units": [
            {"game_id_espn": game, "team_id_espn": team}
            for game, team in sorted(unresolved_units)
        ],
        "game_payload_receipts": receipts,
        "adjudications": rows,
        "rule": (
            "NO TOLERANCE: season-release mismatches are compared independently to "
            "the final per-game player box and team box. Team-only rebound accounting "
            "is explicit. Any stale player-release unit requires history quarantine "
            "and model rebuild; unresolved final-box discrepancies block promotion."
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
                "stale_team_release_units": report["stale_team_release_units"],
                "unresolved_units": report["unresolved_units"],
                "receipt_sha256": report["receipt_sha256"],
            }
        )
    )


if __name__ == "__main__":
    main()
