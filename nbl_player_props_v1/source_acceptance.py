#!/usr/bin/env python3
"""Live source acceptance for the free official NBL/Genius data surface."""
from __future__ import annotations

import argparse
import json

from source_client import RosettaClient


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season-year", type=int, default=2026)
    args = ap.parse_args()
    c = RosettaClient()
    seasons = c.seasons()
    teams = c.teams()
    schedule = c.schedule(args.season_year, "all")
    team_stats = c.team_stats(args.season_year, "regular")

    if not seasons.data:
        raise SystemExit("NBL_SOURCE_ACCEPTANCE_FAIL seasons empty")
    if not teams.data:
        raise SystemExit("NBL_SOURCE_ACCEPTANCE_FAIL teams empty")

    report = {
        "ok": True,
        "season_year": args.season_year,
        "season_rows": len(seasons.data),
        "team_rows": len(teams.data),
        "schedule_rows": len(schedule.data),
        "team_stats_rows": len(team_stats.data),
        "schedule_keys": sorted(schedule.data[0].keys()) if schedule.data else [],
        "team_stats_keys": sorted(team_stats.data[0].keys()) if team_stats.data else [],
    }

    # Deep probe one actual fixture when the new season schedule is published.
    if schedule.data:
        match = schedule.data[0]
        home = match.get("home_team") if isinstance(match.get("home_team"), dict) else {}
        away = match.get("away_team") if isinstance(match.get("away_team"), dict) else {}
        report["sample_fixture"] = {
            "id": match.get("id"), "home": home.get("name"), "away": away.get("name"),
            "start_time": match.get("start_time"), "status": match.get("match_status"),
        }
        if home.get("id"):
            roster = c.roster(str(home["id"]), args.season_year)
            report["sample_roster_rows"] = len(roster.data)
            if roster.data:
                p = roster.data[0].get("player") if isinstance(roster.data[0].get("player"), dict) else {}
                if p.get("id"):
                    stats = c.player_stats(str(p["id"]))
                    logs = c.player_boxscores(str(p["id"]), args.season_year, "regular")
                    report["sample_player_stats_rows"] = len(stats.data)
                    report["sample_player_log_rows"] = len(logs.data)
                    report["sample_player_stats_keys"] = sorted(stats.data[0].keys()) if stats.data else []
                    report["sample_player_log_keys"] = sorted(logs.data[0].keys()) if logs.data else []

    print(json.dumps(report, sort_keys=True))
    print("NBL_SOURCE_ACCEPTANCE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
