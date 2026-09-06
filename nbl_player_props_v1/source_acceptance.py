#!/usr/bin/env python3
"""Live source acceptance for the free official NBL/Genius data surface."""
from __future__ import annotations

import argparse
import json
import re

from source_client import RosettaClient

TZ = re.compile(r"(?:Z|[+-]\d\d:\d\d)$")


def fixture_time(row: dict) -> str:
    return str(row.get("start_time_datetime") or row.get("start_time") or "")


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--season-year", type=int, default=2026); args = ap.parse_args()
    c = RosettaClient(); seasons = c.seasons(); teams = c.teams(); schedule = c.schedule(args.season_year, "all"); historical = c.schedule(2025, "all"); team_stats = c.team_stats(args.season_year, "regular")
    if not seasons.data: raise SystemExit("NBL_SOURCE_ACCEPTANCE_FAIL seasons empty")
    if not teams.data: raise SystemExit("NBL_SOURCE_ACCEPTANCE_FAIL teams empty")
    if len(historical.data) < 150: raise SystemExit(f"NBL_SOURCE_ACCEPTANCE_FAIL historical schedule truncated: {len(historical.data)}")
    bad_times = [r.get("id") for r in historical.data if fixture_time(r) and not TZ.search(fixture_time(r))]
    if bad_times: raise SystemExit(f"NBL_SOURCE_ACCEPTANCE_FAIL timezone-ambiguous fixtures: {bad_times[:5]}")

    report = {
        "ok": True, "season_year": args.season_year, "season_rows": len(seasons.data), "team_rows": len(teams.data),
        "schedule_rows": len(schedule.data), "historical_2025_schedule_rows": len(historical.data),
        "schedule_keys": sorted(schedule.data[0].keys()) if schedule.data else [], "team_stats_rows": len(team_stats.data),
        "team_stats_keys": sorted(team_stats.data[0].keys()) if team_stats.data else [],
        "schedule_complete_request": bool(schedule.receipt.get("complete_schedule_request")),
    }
    if schedule.data:
        match = schedule.data[0]; home = match.get("home_team") if isinstance(match.get("home_team"), dict) else {}; away = match.get("away_team") if isinstance(match.get("away_team"), dict) else {}
        report["sample_fixture"] = {"id": match.get("id"), "home": home.get("name"), "away": away.get("name"), "start_time": fixture_time(match), "status": match.get("match_status")}
        if home.get("id"):
            roster = c.roster(str(home["id"]), args.season_year); report["sample_roster_rows"] = len(roster.data)
            if roster.data:
                p = roster.data[0].get("player") if isinstance(roster.data[0].get("player"), dict) else {}
                if p.get("id"):
                    stats = c.player_stats(str(p["id"])); logs = c.player_boxscores(str(p["id"]), args.season_year, "regular")
                    report["sample_player_stats_rows"] = len(stats.data); report["sample_player_log_rows"] = len(logs.data)
                    report["sample_player_stats_keys"] = sorted(stats.data[0].keys()) if stats.data else []; report["sample_player_log_keys"] = sorted(logs.data[0].keys()) if logs.data else []
    print(json.dumps(report, sort_keys=True)); print("NBL_SOURCE_ACCEPTANCE=PASS"); return 0


if __name__ == "__main__": raise SystemExit(main())
