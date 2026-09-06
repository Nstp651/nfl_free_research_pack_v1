from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model"))

from current_features import PriorTranslationRequired, TeamPriorMissing, assemble_feature_vector  # noqa: E402


def qbase():
    return {
        "selected_model": {
            "features": [
                "player_games_prior", "player_season_games_prior",
                "player_minutes_mean_3", "player_days_rest",
                "team_games_prior", "team_season_games_prior", "team_days_rest",
                "opponent_days_rest", "team_points_mean_5",
                "opponent_points_allowed_mean_5", "team_possessions_mean_5",
                "opponent_possessions_mean_5", "home_flag",
                "player_assists_mean_3", "team_assists_mean_5",
                "opponent_assists_allowed_mean_5",
            ]
        }
    }


def snapshot():
    return {
        "market_data": False,
        "snapshot_revision": "abc123",
        "players": {
            "testguard": {
                "player_key": "testguard",
                "last_team": "Old Team",
                "last_season_start": 2025,
                "last_match_time": "2026-02-10T10:00:00+00:00",
                "features": {
                    "player_games_prior": 50.0,
                    "player_last_season_games": 30.0,
                    "player_minutes_mean_3": 28.0,
                    "player_assists_mean_3": 5.0,
                },
            }
        },
        "teams": {
            "Sydney Kings": {
                "team": "Sydney Kings",
                "last_season_start": 2025,
                "last_match_time": "2026-02-11T10:00:00+00:00",
                "features": {
                    "team_games_prior": 100.0,
                    "team_last_season_games": 30.0,
                    "team_points_mean_5": 92.0,
                    "team_possessions_mean_5": 80.0,
                    "team_assists_mean_5": 21.0,
                },
            },
            "Perth Wildcats": {
                "team": "Perth Wildcats",
                "last_season_start": 2025,
                "last_match_time": "2026-02-12T10:00:00+00:00",
                "features": {
                    "team_games_prior": 110.0,
                    "team_last_season_games": 31.0,
                    "team_possessions_mean_5": 82.0,
                    "points_allowed_mean_5": 88.0,
                    "assists_allowed_mean_5": 19.0,
                },
            },
        },
    }


def test_next_season_resets_season_counts_but_preserves_career_history():
    out = assemble_feature_vector(
        qbase(), snapshot(), player_name="Test Guard", team="Sydney Kings",
        opponent="Perth Wildcats", target_season_start=2026,
        target_time="2026-09-20T10:00:00+00:00", home_flag=True,
    )
    f = out["features"]
    assert f["player_games_prior"] == 50.0
    assert f["player_season_games_prior"] == 0.0
    assert f["team_games_prior"] == 100.0
    assert f["team_season_games_prior"] == 0.0
    assert f["home_flag"] == 1.0
    assert f["opponent_points_allowed_mean_5"] == 88.0
    assert f["opponent_possessions_mean_5"] == 82.0
    assert f["opponent_assists_allowed_mean_5"] == 19.0
    assert f["player_days_rest"] > f["team_days_rest"] > f["opponent_days_rest"]


def test_same_season_uses_completed_games_as_prior_counts():
    s = snapshot()
    s["players"]["testguard"]["last_season_start"] = 2026
    s["teams"]["Sydney Kings"]["last_season_start"] = 2026
    out = assemble_feature_vector(
        qbase(), s, player_name="Test Guard", team="Sydney Kings",
        opponent="Perth Wildcats", target_season_start=2026,
        target_time="2026-09-20T10:00:00+00:00", home_flag=0,
    )
    assert out["features"]["player_season_games_prior"] == 30.0
    assert out["features"]["team_season_games_prior"] == 30.0


def test_new_to_nbl_player_routes_to_translation_not_median_imputation():
    with pytest.raises(PriorTranslationRequired, match="prior-competition translation required"):
        assemble_feature_vector(
            qbase(), snapshot(), player_name="Brand New Import", team="Sydney Kings",
            opponent="Perth Wildcats", target_season_start=2026,
            target_time="2026-09-20T10:00:00+00:00", home_flag=1,
        )


def test_unknown_team_fails_closed():
    with pytest.raises(TeamPriorMissing):
        assemble_feature_vector(
            qbase(), snapshot(), player_name="Test Guard", team="Unknown Club",
            opponent="Perth Wildcats", target_season_start=2026,
            target_time="2026-09-20T10:00:00+00:00", home_flag=1,
        )


def test_missing_optional_feature_is_reported_not_fabricated():
    q = qbase()
    q["selected_model"]["features"].append("opponent_fgm_allowed_mean_10")
    out = assemble_feature_vector(
        q, snapshot(), player_name="Test Guard", team="Sydney Kings",
        opponent="Perth Wildcats", target_season_start=2026,
        target_time="2026-09-20T10:00:00+00:00", home_flag=1,
    )
    assert "opponent_fgm_allowed_mean_10" in out["missing_features"]
    assert "opponent_fgm_allowed_mean_10" not in out["features"]
