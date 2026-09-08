from __future__ import annotations

import pandas as pd

from nba_player_props_v1.historical.source_acceptance import reconcile


def _history():
    rows = []
    for team, opp, score, opp_score, asts in (("1", "2", 100, 90, [2, 3]), ("2", "1", 90, 100, [1, 2])):
        for i, ast in enumerate(asts):
            rows.append({
                "game_id_espn": "99", "team_id_espn": team, "opponent_team_id_espn": opp,
                "game_start_utc": "2026-01-01T00:00:00Z", "player_id_espn": f"{team}{i}",
                "assists": ast, "field_goals_made": 5 + i, "field_goals_attempted": 10 + i,
                "three_point_field_goals_made": 2, "three_point_field_goals_attempted": 5,
                "free_throws_made": 3, "free_throws_attempted": 4,
                "team_score": score, "opponent_team_score": opp_score,
            })
    return pd.DataFrame(rows)


def _team_box():
    history = _history()
    out = []
    for (game, team), g in history.groupby(["game_id_espn", "team_id_espn"]):
        out.append({
            "game_id": game, "season": 2026, "season_type": 2, "team_id": team,
            "opponent_team_id": g.opponent_team_id_espn.iloc[0],
            "team_score": g.team_score.iloc[0], "opponent_team_score": g.opponent_team_score.iloc[0],
            **{f: int(g[f].sum()) for f in (
                "assists", "field_goals_made", "field_goals_attempted",
                "three_point_field_goals_made", "three_point_field_goals_attempted",
                "free_throws_made", "free_throws_attempted")},
        })
    return pd.DataFrame(out)


def _schedule():
    return pd.DataFrame([{
        "game_id": "99", "season": 2026, "season_type": 2,
        "game_date_time": pd.Timestamp("2026-01-01T00:00:00Z"),
        "home_team_id": "1", "away_team_id": "2",
    }])


def test_reconcile_passes_exact_independent_tables():
    result = reconcile(_history(), _team_box(), _schedule())
    assert result["status"] == "PASS"
    assert result["schedule_team_identity_rate"] == 1.0
    assert result["team_score_rate"] == 1.0
    assert all(v["rate"] == 1.0 for v in result["exact_core_fields"].values())


def test_reconcile_fails_material_box_disagreement():
    team = _team_box()
    team.loc[0, "assists"] += 1
    result = reconcile(_history(), team, _schedule())
    assert result["status"] == "FAIL"
    assert result["exact_core_fields"]["assists"]["rate"] < 0.999
