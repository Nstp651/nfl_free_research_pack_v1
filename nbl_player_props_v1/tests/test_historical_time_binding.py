from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "historical"))

from build_player_games import canonical_player_games, result_identity_maps  # noqa: E402


def team_rows() -> pd.DataFrame:
    base = {
        "season": "2025-2026", "match_time": None,
        "field_goals_made": 30, "field_goals_attempted": 70,
        "three_pointers_made": 8, "three_pointers_attempted": 25,
        "free_throws_made": 15, "free_throws_attempted": 20,
        "rebounds_offensive": 10, "rebounds_defensive": 25,
        "rebounds_total": 35, "assists": 20, "turnovers": 12, "points": 83,
    }
    return pd.DataFrame([
        {**base, "match_id": "uuid-1", "name": "Sydney Kings", "opp_name": "Perth Wildcats"},
        {**base, "match_id": "uuid-1", "name": "Perth Wildcats", "opp_name": "Sydney Kings"},
    ])


def player_rows() -> pd.DataFrame:
    return pd.DataFrame([{
        "match_id": "uuid-1", "season": "2025-2026", "match_time": None,
        "team_name": "Sydney Kings", "opp_name": "Perth Wildcats",
        "first_name": "Test", "family_name": "Guard", "player_id": "p1",
        "seconds": 1800, "minutes": "30:00", "assists": 6, "rebounds_total": 4,
        "rebounds_offensive": 1, "rebounds_defensive": 3, "turnovers": 2,
        "field_goals_attempted": 10, "field_goals_made": 5,
        "three_pointers_attempted": 4, "points": 13, "starter": True,
        "playing_position": "G", "home_away": "home",
    }])


def results_rows(season: str = "2025-2026") -> pd.DataFrame:
    return pd.DataFrame([{
        "match_id": "uuid-1", "season": season,
        "match_time": "2025-09-18T19:30:00+10:00",
        "match_time_utc": "2025-09-18T09:30:00",
    }])


def test_blank_player_time_recovers_from_results_uuid():
    games, _ = canonical_player_games(player_rows(), team_rows(), results_rows())
    assert len(games) == 1
    assert games.iloc[0]["match_time"].isoformat() == "2025-09-18T09:30:00+00:00"
    assert games.iloc[0]["minutes"] == pytest.approx(30.0)


def test_minutes_falls_back_row_by_row_when_seconds_column_exists_but_value_is_blank():
    rows = player_rows()
    rows.loc[0, "seconds"] = None
    rows.loc[0, "minutes"] = "31:30"
    games, _ = canonical_player_games(rows, team_rows(), results_rows())
    assert len(games) == 1
    assert games.iloc[0]["minutes"] == pytest.approx(31.5)


def test_seconds_remains_authoritative_when_both_minutes_fields_are_populated():
    rows = player_rows()
    rows.loc[0, "seconds"] = 1740
    rows.loc[0, "minutes"] = "31:30"
    games, _ = canonical_player_games(rows, team_rows(), results_rows())
    assert games.iloc[0]["minutes"] == pytest.approx(29.0)


def test_result_uuid_season_mismatch_fails_closed():
    with pytest.raises(RuntimeError, match="season mismatch"):
        canonical_player_games(player_rows(), team_rows(), results_rows("2024-2025"))


def test_result_uuid_collision_fails_closed():
    bad = pd.concat([
        results_rows(),
        pd.DataFrame([{"match_id": "uuid-1", "season": "2025-2026", "match_time_utc": "2025-09-19T09:30:00"}]),
    ], ignore_index=True)
    with pytest.raises(RuntimeError, match="UUID collision"):
        result_identity_maps(bad)
