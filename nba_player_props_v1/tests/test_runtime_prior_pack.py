import pandas as pd
import pytest

from nba_player_props_v1.model.runtime_prior_pack import build_runtime_prior_pack


def history():
    rows = []
    games = [
        ("4010000001", "2025-10-20T00:00:00Z", 2026, {"2": ("18", 20, 6, 2), "18": ("2", 18, 4, 1)}),
        ("4010000002", "2025-10-22T00:00:00Z", 2026, {"2": ("18", 24, 8, 3), "18": ("2", 22, 5, 2)}),
    ]
    pid = {"2": "100", "18": "200"}
    for game_id, start, season, teams in games:
        for team_id, (opp, assists, rebounds, orb) in teams.items():
            rows.append({
                "season": season, "game_id_espn": game_id, "game_start_utc": start,
                "player_id_espn": pid[team_id], "team_id_espn": team_id, "opponent_team_id_espn": opp,
                "starter": True, "minutes": 30.0, "assists": assists, "rebounds": rebounds,
                "offensive_rebounds": orb, "defensive_rebounds": rebounds - orb, "turnovers": 2,
                "field_goals_attempted": 15, "field_goals_made": 7, "free_throws_attempted": 4,
            })
    return pd.DataFrame(rows)


def test_runtime_pack_carries_season_counts_and_exact_recent_priors():
    pack = build_runtime_prior_pack(history(), history_sha256="a" * 64)
    assert pack["market_data"] is False
    assert pack["player_count"] == 2
    assert pack["team_count"] == 2
    assert pack["players"]["100"]["games_by_season"] == {"2026": 2}
    assert pack["teams"]["2"]["games_by_season"] == {"2026": 2}
    assert pack["players"]["100"]["features"]["assists_l5"] == 22.0
    assert pack["players"]["100"]["features"]["rebounds_l5"] == 7.0
    assert len(pack["pack_sha256"]) == 64


def test_runtime_pack_rejects_duplicate_player_game_rows():
    data = history()
    data = pd.concat([data, data.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate player-games"):
        build_runtime_prior_pack(data, history_sha256="a" * 64)
