import pytest

from nba_player_props_v1.historical.accept_quarantined_history import accept_quarantined_history


def _inputs():
    final_source = {
        "market_data": False,
        "status": "REBUILD_REQUIRED",
        "history_sha256": "a" * 64,
        "receipt_sha256": "b" * 64,
        "rebuild_required_game_ids": ["2", "1"],
        "canonical_runtime_identity": "ESPN_ID",
        "official_nba_id_crosswalk": "OPTIONAL_ENRICHMENT_GATE_NOT_BASE_V1_DEPENDENCY",
        "identity_and_schedule_pass": True,
        "runtime_fixture_source": {"status": "PASS"},
        "training_quarantine_audit": {"status": "PASS"},
    }
    adjudication = {
        "market_data": False,
        "status": "PASS",
        "receipt_sha256": "c" * 64,
        "unresolved_units": [],
    }
    quarantine = {
        "market_data": False,
        "source_history_sha256": "a" * 64,
        "accepted_history_sha256": "d" * 64,
        "receipt_sha256": "e" * 64,
        "quarantined_game_ids": ["1", "2"],
        "games_removed": 2,
        "rows_removed": 20,
        "rows_before": 1000,
        "rows_after": 980,
    }
    return final_source, adjudication, quarantine


def test_accepts_exact_full_game_quarantine_chain():
    final_source, adjudication, quarantine = _inputs()
    result = accept_quarantined_history(final_source, adjudication, quarantine)
    assert result["status"] == "PASS"
    assert result["history_sha256"] == "d" * 64
    assert result["rebuild_required_game_ids"] == ["1", "2"]


def test_rejects_partial_or_different_quarantine_set():
    final_source, adjudication, quarantine = _inputs()
    quarantine["quarantined_game_ids"] = ["1"]
    quarantine["games_removed"] = 1
    with pytest.raises(ValueError, match="quarantine game set differs"):
        accept_quarantined_history(final_source, adjudication, quarantine)


def test_rejects_wrong_source_history_hash():
    final_source, adjudication, quarantine = _inputs()
    quarantine["source_history_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="source history hash mismatch"):
        accept_quarantined_history(final_source, adjudication, quarantine)
