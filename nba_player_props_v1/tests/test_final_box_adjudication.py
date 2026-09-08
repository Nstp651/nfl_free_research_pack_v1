from nba_player_props_v1.historical.final_box_adjudication import (
    _adjudicate_field,
    derive_pbp_team_stats,
)


def test_final_pbp_separates_player_and_team_rebounds():
    payload = {
        "plays": [
            {"team.id": "4", "type.text": "Driving Layup Shot", "shootingPlay": True,
             "scoringPlay": True, "pointsAttempted": 2, "scoreValue": 2,
             "participants.0.athlete.id": "a", "participants.1.athlete.id": "b"},
            {"team.id": "4", "type.text": "Jump Shot", "shootingPlay": True,
             "scoringPlay": False, "pointsAttempted": 3, "scoreValue": 0,
             "participants.0.athlete.id": "a"},
            {"team.id": "4", "type.text": "Free Throw - 1 of 1", "shootingPlay": True,
             "scoringPlay": True, "pointsAttempted": 1, "scoreValue": 1,
             "participants.0.athlete.id": "a"},
            {"team.id": "4", "type.text": "Defensive Rebound", "participants.0.athlete.id": "a"},
            {"team.id": "4", "type.text": "Offensive Rebound", "participants.0.athlete.id": None},
        ]
    }
    stats = derive_pbp_team_stats(payload)["4"]
    assert stats["assists"] == 1
    assert stats["field_goals_made"] == 1
    assert stats["field_goals_attempted"] == 2
    assert stats["three_point_field_goals_attempted"] == 1
    assert stats["free_throws_made"] == 1
    assert stats["free_throws_attempted"] == 1
    assert stats["player_rebounds"] == 1
    assert stats["team_rebounds"] == 1


def test_release_decisions_have_no_tolerance():
    core = _adjudicate_field(
        "assists", {"raw": 4.0, "team": 5.0}, {"assists": 5}
    )
    assert core["decision"] == "TEAM_RELEASE_CONFIRMED_PLAYER_RELEASE_STALE"
    rebound = _adjudicate_field(
        "rebounds",
        {"raw": 4.0, "team": 5.0},
        {"player_rebounds": 4, "team_rebounds": 1},
    )
    assert rebound["decision"] == "TEAM_REBOUND_ACCOUNTING_CONFIRMED"
