from nba_player_props_v1.historical.final_box_adjudication import (
    _adjudicate_field,
    derive_final_box_stats,
)


def _payload():
    keys = [
        "minutes", "points", "fieldGoalsMade-fieldGoalsAttempted",
        "threePointFieldGoalsMade-threePointFieldGoalsAttempted",
        "freeThrowsMade-freeThrowsAttempted", "rebounds", "assists", "turnovers",
        "steals", "blocks", "offensiveRebounds", "defensiveRebounds", "fouls", "plusMinus",
    ]
    return {
        "boxscore": {
            "teams": [
                {
                    "team": {"id": "4"},
                    "statistics": [
                        {"name": "fieldGoalsMade-fieldGoalsAttempted", "displayValue": "10-20"},
                        {"name": "threePointFieldGoalsMade-threePointFieldGoalsAttempted", "displayValue": "4-9"},
                        {"name": "freeThrowsMade-freeThrowsAttempted", "displayValue": "7-8"},
                        {"name": "totalRebounds", "displayValue": "12"},
                        {"name": "offensiveRebounds", "displayValue": "4"},
                        {"name": "defensiveRebounds", "displayValue": "8"},
                        {"name": "assists", "displayValue": "7"},
                    ],
                },
                {
                    "team": {"id": "8"},
                    "statistics": [
                        {"name": "fieldGoalsMade-fieldGoalsAttempted", "displayValue": "8-18"},
                        {"name": "threePointFieldGoalsMade-threePointFieldGoalsAttempted", "displayValue": "3-8"},
                        {"name": "freeThrowsMade-freeThrowsAttempted", "displayValue": "5-6"},
                        {"name": "totalRebounds", "displayValue": "9"},
                        {"name": "offensiveRebounds", "displayValue": "2"},
                        {"name": "defensiveRebounds", "displayValue": "7"},
                        {"name": "assists", "displayValue": "6"},
                    ],
                },
            ],
            "players": [
                {
                    "team": {"id": "4"},
                    "statistics": [{
                        "keys": keys,
                        "athletes": [
                            {"didNotPlay": False, "stats": ["30", "15", "6-11", "2-5", "1-2", "6", "4", "1", "0", "0", "2", "4", "1", "+2"]},
                            {"didNotPlay": False, "stats": ["18", "16", "4-9", "2-4", "6-6", "5", "3", "1", "0", "0", "1", "4", "1", "+1"]},
                        ],
                    }],
                },
                {
                    "team": {"id": "8"},
                    "statistics": [{
                        "keys": keys,
                        "athletes": [
                            {"didNotPlay": False, "stats": ["32", "24", "8-18", "3-8", "5-6", "9", "6", "2", "1", "0", "2", "7", "2", "-2"]},
                        ],
                    }],
                },
            ],
        }
    }


def test_final_box_separates_player_and_team_rebounds():
    stats = derive_final_box_stats(_payload())["4"]
    assert stats["player"]["assists"] == 7
    assert stats["player"]["field_goals_made"] == 10
    assert stats["player"]["field_goals_attempted"] == 20
    assert stats["player"]["rebounds"] == 11
    assert stats["team"]["rebounds"] == 12
    assert stats["team_minus_player_rebounds"] == {
        "rebounds": 1,
        "offensive_rebounds": 1,
        "defensive_rebounds": 0,
    }


def test_release_decisions_have_no_tolerance():
    final = derive_final_box_stats(_payload())["4"]
    core = _adjudicate_field(
        "assists", {"raw": 6.0, "team": 7.0}, final
    )
    assert core["decision"] == "TEAM_RELEASE_CONFIRMED_PLAYER_RELEASE_STALE"

    rebound = _adjudicate_field(
        "rebounds", {"raw": 11.0, "team": 12.0}, final
    )
    assert rebound["decision"] == "FINAL_PLAYER_AND_TEAM_RELEASES_CONFIRMED_TEAM_REBOUND_ACCOUNTING"

    unresolved = _adjudicate_field(
        "assists", {"raw": 8.0, "team": 9.0}, final
    )
    assert unresolved["decision"] == "UNRESOLVED"


def test_internal_final_box_mismatch_requires_rebuild():
    final = derive_final_box_stats(_payload())["4"]
    final["team"]["assists"] = 6
    decision = _adjudicate_field(
        "assists", {"raw": 7.0, "team": 6.0}, final
    )
    assert decision["decision"] == "FINAL_BOX_INTERNAL_ACCOUNTING_MISMATCH_REBUILD_REQUIRED"
