from datetime import datetime, timezone

import pytest

from nba_player_props_v1.research_contract import validate_research_checkpoint


def payload():
    return {
        "schema_version": "nba_game_research_v1",
        "market_data": False,
        "run_mode": "BOTH",
        "game_id": "0022600001",
        "slate_date_et": "2026-10-20",
        "evidence": [
            {
                "evidence_id": "e1",
                "url": "https://official.nba.com/example",
                "title": "Official status report",
                "checked_at": "2026-10-20T12:00:00Z",
                "published_at": "2026-10-20T11:30:00Z",
                "source_tier": 0,
                "evidence_type": "STATUS",
            },
            {
                "evidence_id": "e2",
                "url": "https://www.nba.com/example",
                "title": "Team role update",
                "checked_at": "2026-10-20T12:00:00Z",
                "source_tier": 1,
                "evidence_type": "ROLE",
            },
        ],
        "specialist_metrics": {
            "touches": {"status": "AVAILABLE", "evidence_ids": ["e2"]},
            "potential_assists": {"status": "PARTIAL", "evidence_ids": []},
        },
        "players": [
            {
                "player_id": "2544",
                "availability": "ACTIVE",
                "role_state": "RETURNING_CHANGED",
                "projected_minutes": {"low": 32, "mean": 35, "high": 38},
                "evidence_ids": ["e1", "e2"],
                "confidence_inputs": {"role_evidence": "strong"},
                "fragility_inputs": {"minutes_band_width": 6},
                "stat_context": {
                    "assists": {"causal_pathway": "minutes -> creation -> finishing -> assists", "evidence_ids": ["e2"]},
                    "rebounds": {"causal_pathway": "minutes -> miss environment -> chances -> rebounds", "evidence_ids": ["e2"]},
                },
            }
        ],
    }


def test_accepts_complete_market_blind_checkpoint():
    result = validate_research_checkpoint(payload(), now=datetime(2026, 10, 20, 13, tzinfo=timezone.utc))
    assert result.ok
    assert result.player_count == 1
    assert result.evidence_count == 2


def test_rejects_market_token():
    p = payload()
    p["notes"] = "sportsbook projection"
    with pytest.raises(ValueError, match="market leakage"):
        validate_research_checkpoint(p, now=datetime(2026, 10, 20, 13, tzinfo=timezone.utc))


def test_rejects_available_metric_without_evidence():
    p = payload()
    p["specialist_metrics"]["touches"] = {"status": "AVAILABLE", "evidence_ids": []}
    with pytest.raises(ValueError, match="AVAILABLE metric requires evidence"):
        validate_research_checkpoint(p, now=datetime(2026, 10, 20, 13, tzinfo=timezone.utc))


def test_rejects_invalid_minutes_band():
    p = payload()
    p["players"][0]["projected_minutes"] = {"low": 39, "mean": 35, "high": 38}
    with pytest.raises(ValueError, match="invalid minutes band"):
        validate_research_checkpoint(p, now=datetime(2026, 10, 20, 13, tzinfo=timezone.utc))
