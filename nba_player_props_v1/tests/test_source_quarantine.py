from __future__ import annotations

import pandas as pd

from nba_player_props_v1.historical.source_acceptance import (
    quarantine_transform_audit,
    reconcile_raw_player_to_team,
)

FIELDS = (
    "assists", "rebounds", "offensive_rebounds", "defensive_rebounds",
    "field_goals_made", "field_goals_attempted", "three_point_field_goals_made",
    "three_point_field_goals_attempted", "free_throws_made", "free_throws_attempted",
)


def _raw():
    rows = []
    for team, opp in (("1", "2"), ("2", "1")):
        base = {"season": 2026, "game_id": "99", "team_id": team, "opponent_team_id": opp}
        rows.append({**base, "athlete_id": f"{team}a", "minutes_parsed": 30.0, "dnp_parsed": False, "positive_stat_sum": 20,
                     "assists": 4, "rebounds": 5, "offensive_rebounds": 1, "defensive_rebounds": 4,
                     "field_goals_made": 5, "field_goals_attempted": 10, "three_point_field_goals_made": 2,
                     "three_point_field_goals_attempted": 5, "free_throws_made": 3, "free_throws_attempted": 4})
        rows.append({**base, "athlete_id": f"{team}b", "minutes_parsed": 0.0, "dnp_parsed": False, "positive_stat_sum": 2,
                     "assists": 1, "rebounds": 1, "offensive_rebounds": 0, "defensive_rebounds": 1,
                     "field_goals_made": 0, "field_goals_attempted": 0, "three_point_field_goals_made": 0,
                     "three_point_field_goals_attempted": 0, "free_throws_made": 0, "free_throws_attempted": 0})
    return pd.DataFrame(rows)


def _history():
    rows = []
    for team, opp in (("1", "2"), ("2", "1")):
        rows.append({"season": 2026, "game_id_espn": "99", "team_id_espn": team, "opponent_team_id_espn": opp,
                     "assists": 4, "rebounds": 5, "offensive_rebounds": 1, "defensive_rebounds": 4,
                     "field_goals_made": 5, "field_goals_attempted": 10, "three_point_field_goals_made": 2,
                     "three_point_field_goals_attempted": 5, "free_throws_made": 3, "free_throws_attempted": 4})
    return pd.DataFrame(rows)


def _team():
    raw = _raw()
    rows = []
    for (season, game, team), g in raw.groupby(["season", "game_id", "team_id"]):
        row = {"season": season, "game_id": game, "team_id": team, "opponent_team_id": g.opponent_team_id.iloc[0]}
        row.update({field: float(g[field].sum()) for field in FIELDS})
        rows.append(row)
    return pd.DataFrame(rows)


def test_raw_player_sums_reconcile_exactly_to_team_box():
    result = reconcile_raw_player_to_team(_raw(), _team())
    assert result["status"] == "PASS"
    assert all(value["rate"] == 1.0 for value in result["exact_fields"].values())


def test_quarantine_exactly_explains_training_difference():
    result = quarantine_transform_audit(_history(), _raw())
    assert result["quarantined_positive_stat_rows"] == 2
    assert result["quarantined_target_units"] == {"assists": 2.0, "rebounds": 2.0}
    # Synthetic fixture is intentionally too contaminated to be production-accepted,
    # but the transformation accounting itself must be exact.
    assert all(value["rate"] == 1.0 for value in result["training_plus_quarantine_equals_raw"].values())
    assert result["status"] == "FAIL"
