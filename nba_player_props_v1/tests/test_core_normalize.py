import pandas as pd
import pytest

from nba_player_props_v1.historical.core_normalize import normalize_player_box


def frame():
    base = {
        "game_id": [401000001, 401000001],
        "season": [2026, 2026],
        "season_type": [2, 2],
        "game_date_time": ["2026-01-05T00:30:00Z", "2026-01-05T00:30:00Z"],
        "athlete_id": [10, 11],
        "athlete_display_name": ["Player A", "Player B"],
        "team_id": [1, 1],
        "team_name": ["Team A", "Team A"],
        "team_abbreviation": ["AAA", "AAA"],
        "opponent_team_id": [2, 2],
        "opponent_team_name": ["Team B", "Team B"],
        "opponent_team_abbreviation": ["BBB", "BBB"],
        "home_away": ["home", "home"],
        "minutes": ["35:30", "0:00"],
        "starter": [True, False],
        "did_not_play": [False, True],
        "field_goals_made": [6, 0],
        "field_goals_attempted": [12, 0],
        "three_point_field_goals_made": [2, 0],
        "three_point_field_goals_attempted": [5, 0],
        "free_throws_made": [3, 0],
        "free_throws_attempted": [4, 0],
        "offensive_rebounds": [1, 0],
        "defensive_rebounds": [5, 0],
        "rebounds": [6, 0],
        "assists": [8, 0],
        "turnovers": [2, 0],
        "team_score": [110, 110],
        "opponent_team_score": [104, 104],
        "game_spread": [-4.5, -4.5],
    }
    return pd.DataFrame(base)


def test_normalizes_played_rows_and_drops_market_fields():
    out = normalize_player_box(frame())
    assert len(out) == 1
    assert out.loc[0, "player_id_espn"] == "10"
    assert abs(out.loc[0, "minutes"] - 35.5) < 1e-12
    assert out.loc[0, "game_date_et"] == "2026-01-04"
    assert bool(out.loc[0, "market_data"]) is False
    assert "game_spread" not in out.columns
    assert "game_spread" in out.loc[0, "source_market_columns_observed"]


def test_rejects_rebound_identity_failure():
    bad = frame()
    bad.loc[0, "rebounds"] = 7
    with pytest.raises(ValueError, match=r"ORB \+ DRB"):
        normalize_player_box(bad)


def test_rejects_duplicate_player_game():
    bad = frame().iloc[[0, 0]].copy()
    with pytest.raises(ValueError, match="duplicate canonical player-game"):
        normalize_player_box(bad)
