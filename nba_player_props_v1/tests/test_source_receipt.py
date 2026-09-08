from nba_player_props_v1.source_receipt import build_source_receipt, validate_source_receipt


def make_receipt():
    return build_source_receipt(
        built_at_utc="2026-09-08T03:00:00Z",
        builder_commit="a" * 40,
        upstream_assets=[{
            "source": "sportsdataverse",
            "immutable_id": "espn_nba_player_boxscores/player_box_2026.rds",
            "url": "https://github.com/sportsdataverse/sportsdataverse-data/releases/download/espn_nba_player_boxscores/player_box_2026.rds",
            "sha256": "b" * 64,
            "bytes": 123,
        }],
        normalized_player_games={"sha256": "c" * 64, "rows": 1000},
        identity_audit={
            "game_resolution_rate": 1.0,
            "player_resolution_rate": 0.999,
            "timestamp_non_null_rate": 1.0,
            "duplicate_canonical_player_games": 0,
        },
        specialist_metrics={
            "touches": {"status": "PARTIAL", "coverage": 0.8},
            "minutes": {"status": "AVAILABLE", "coverage": 1.0},
        },
        seasons=[2024, 2025, 2026],
        latest_completed_game_utc="2026-06-20T02:00:00Z",
    )


def test_receipt_is_self_verifying():
    receipt = make_receipt()
    validate_source_receipt(receipt)
    assert len(receipt["source_receipt_sha256"]) == 64


def test_tamper_is_rejected():
    receipt = make_receipt()
    receipt["normalized_player_games"]["rows"] += 1
    try:
        validate_source_receipt(receipt)
    except ValueError as exc:
        assert "hash mismatch" in str(exc)
    else:
        raise AssertionError("tampered receipt should fail")
