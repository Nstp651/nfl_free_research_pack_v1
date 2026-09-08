from nba_player_props_v1.historical.finalize_source_acceptance import (
    finalize_source_acceptance,
)


def _candidate():
    return {
        "market_data": False,
        "identity_and_schedule_pass": True,
        "runtime_fixture_source": {"status": "PASS"},
        "training_quarantine_audit": {"status": "PASS"},
        "history_sha256": "a" * 64,
        "receipt_sha256": "b" * 64,
        "historical_receipt_sha256": "c" * 64,
        "official_nba_id_crosswalk": "OPTIONAL_ENRICHMENT_GATE_NOT_BASE_V1_DEPENDENCY",
    }


def test_source_passes_when_every_player_release_mismatch_is_confirmed():
    adjudication = {
        "market_data": False,
        "status": "PASS",
        "receipt_sha256": "d" * 64,
        "mismatch_game_team_units": 1,
        "unresolved_units": [],
        "stale_player_release_units": [],
        "stale_team_release_units": [{"game_id_espn": "1", "team_id_espn": "4"}],
        "adjudications": [{
            "fields": {
                "assists": {
                    "decision": "PLAYER_RELEASE_CONFIRMED_TEAM_RELEASE_STALE",
                    "raw_player_release_confirmed": True,
                },
                "rebounds": {
                    "decision": "FINAL_PLAYER_AND_TEAM_RELEASES_CONFIRMED_TEAM_REBOUND_ACCOUNTING",
                    "raw_player_release_confirmed": True,
                },
            }
        }],
    }
    result = finalize_source_acceptance(_candidate(), adjudication)
    assert result["status"] == "PASS"
    assert result["player_release_confirmed_fields"] == 2


def test_stale_player_release_requires_rebuild_not_acceptance():
    adjudication = {
        "market_data": False,
        "status": "PASS",
        "receipt_sha256": "d" * 64,
        "mismatch_game_team_units": 1,
        "unresolved_units": [],
        "stale_player_release_units": [{"game_id_espn": "1", "team_id_espn": "4"}],
        "stale_team_release_units": [],
        "adjudications": [{
            "fields": {
                "assists": {
                    "decision": "TEAM_RELEASE_CONFIRMED_PLAYER_RELEASE_STALE",
                    "raw_player_release_confirmed": False,
                }
            }
        }],
    }
    result = finalize_source_acceptance(_candidate(), adjudication)
    assert result["status"] == "REBUILD_REQUIRED"
