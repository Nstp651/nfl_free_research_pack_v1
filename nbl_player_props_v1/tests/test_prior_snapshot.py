from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "historical"))

from build_prior_snapshot import build_snapshot  # noqa: E402


def frame():
    rows = []
    for i in range(4):
        rows.append({
            "season": "2025-2026",
            "match_id": f"m{i}",
            "match_time": f"2026-01-{i+1:02d}T10:00:00Z",
            "player_key": "testguard",
            "source_player_id": f"id{i % 2}",
            "team": "Sydney Kings",
            "opponent": "Perth Wildcats",
            "assists": float(i + 1),
            "rebounds": float(4 + i),
            "minutes": float(20 + i),
            "starter": "true",
            "turnovers": 2.0,
            "field_goals_attempted": 8.0 + i,
            "rebounds_offensive": 1.0,
            "rebounds_defensive": 3.0 + i,
            "team_points_box": 90.0 + i,
            "team_assists_box": 20.0 + i,
            "team_rebounds_box": 35.0 + i,
            "team_fgm": 32.0 + i,
            "team_missed_fg": 40.0 - i,
            "team_possessions_est": 78.0 + i,
            "opp_points_box": 85.0 + i,
            "opp_assists_box": 18.0 + i,
            "opp_rebounds_box": 34.0 + i,
            "opp_fgm": 31.0 + i,
            "opp_missed_fg": 39.0 - i,
            "opp_possessions_est": 77.0 + i,
        })
    return pd.DataFrame(rows)


def test_prior_snapshot_includes_latest_completed_game():
    snap = build_snapshot(frame(), {"market_data": False, "source": "unit"})
    p = snap["players"]["testguard"]
    # Final three completed assists are 2,3,4. A stale shift(1) row would be wrong.
    assert p["features"]["player_assists_mean_3"] == pytest.approx(3.0)
    assert p["features"]["player_minutes_mean_3"] == pytest.approx(22.0)
    assert p["features"]["player_games_prior"] == 4.0
    assert p["last_match_time"].startswith("2026-01-04")
    assert p["source_player_ids"] == ["id0", "id1"]


def test_team_prior_is_one_row_per_completed_team_game():
    snap = build_snapshot(frame())
    team = snap["teams"]["Sydney Kings"]
    assert team["features"]["team_games_prior"] == 4.0
    assert team["features"]["team_points_mean_5"] == pytest.approx(91.5)
    assert team["features"]["assists_allowed_mean_5"] == pytest.approx(19.5)
    assert snap["market_data"] is False
    assert len(snap["snapshot_revision"]) == 20
