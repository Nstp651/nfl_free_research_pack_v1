from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from freeze_core import build_frozen_matchup, validate_frozen_matchup  # noqa: E402
from research_contract import validate_research_context  # noqa: E402

H = {
    "assist_server": "a" * 64,
    "rebound_server": "b" * 64,
    "low": "c" * 64,
    "base": "d" * 64,
    "high": "e" * 64,
    "rebound": "f" * 64,
    "prior": "1" * 64,
    "dispersion": "2" * 64,
}


def research_context():
    return {
        "schema_version": "nbl_fixture_research_v1",
        "market_data": False,
        "fixture_id": "fixture-1",
        "pack_revision": "pack-abc",
        "run_mode": "BOTH",
        "checked_at": "2026-09-06T01:00:00Z",
        "sources": {
            "official": {
                "url": "https://nbl.com.au/news/example",
                "title": "Official team update",
                "checked_at": "2026-09-06T00:55:00Z",
            },
            "report": {
                "url": "https://example.com/nbl/report",
                "title": "Current role report",
                "checked_at": "2026-09-06T00:58:00Z",
            },
        },
        "fixture_context": {"status": "scheduled", "source_ids": ["official"]},
        "players": [
            {
                "player_id": "p1",
                "player_name": "Test Guard",
                "team": "Sydney Kings",
                "availability_status": "ACTIVE",
                "availability_source_ids": ["official"],
                "projected_minutes": {
                    "low": 27.0,
                    "mean": 30.0,
                    "high": 33.0,
                    "source_ids": ["official", "report"],
                },
                "role": {
                    "state": "RETURNING_CHANGED",
                    "creation_role": "PRIMARY",
                    "frontcourt_role": "GUARD",
                    "source_ids": ["report"],
                },
                "stat_context": {
                    "assists": {"source_ids": ["report"], "notes": ["Primary initiator"]},
                    "rebounds": {"source_ids": ["report"], "notes": ["Guard rebound role stable"]},
                },
            }
        ],
    }


def qbase(stat: str):
    return {
        "model_name": f"Nick NBL {stat.upper()} QBASE",
        "model_version": "0.1.0",
        "feature_schema": "nbl_player_pregame_v1",
        "stat_type": stat,
        "market_data": False,
        "walk_forward": {"nb2_alpha_oos": 0.25},
        "probability_contract": {"max_count": 20 if stat == "assists" else 30},
    }


def projections():
    return [
        {
            "player_id": "p1",
            "player_name": "Test Guard",
            "team": "Sydney Kings",
            "heads": {
                "assists": {
                    "qbase_mean": 5.4,
                    "server_qbase_source": "SERVER_QBASE_RUNTIME_SCORE",
                    "server_qbase_receipt_sha256": H["assist_server"],
                    "server_player_prior_key": "testguard",
                    "confidence": "B",
                    "fragility": "MEDIUM",
                    "scenarios": [
                        {
                            "id": "low_minutes",
                            "weight": 0.2,
                            "mean": 4.7,
                            "method": "QBASE_MINUTES_RECOMPUTE",
                            "evidence_source_ids": ["official", "report"],
                            "assumptions": ["27 minute downside"],
                            "quant_input_receipt_sha256": H["low"],
                        },
                        {
                            "id": "base",
                            "weight": 0.6,
                            "mean": 5.6,
                            "method": "QBASE_RUNTIME_SCORE",
                            "evidence_source_ids": ["report"],
                            "assumptions": ["30 minute primary creator"],
                            "quant_input_receipt_sha256": H["base"],
                        },
                        {
                            "id": "high_minutes",
                            "weight": 0.2,
                            "mean": 6.2,
                            "method": "QBASE_MINUTES_RECOMPUTE",
                            "evidence_source_ids": ["official", "report"],
                            "assumptions": ["33 minute upside"],
                            "quant_input_receipt_sha256": H["high"],
                        },
                    ],
                },
                "rebounds": {
                    "qbase_mean": 4.1,
                    "server_qbase_source": "SERVER_QBASE_RUNTIME_SCORE",
                    "server_qbase_receipt_sha256": H["rebound_server"],
                    "server_player_prior_key": "testguard",
                    "confidence": "B",
                    "fragility": "LOW",
                    "scenarios": [
                        {
                            "id": "base",
                            "weight": 1.0,
                            "mean": 4.2,
                            "method": "QBASE_RUNTIME_SCORE",
                            "evidence_source_ids": ["report"],
                            "assumptions": ["Rebound role stable"],
                            "quant_input_receipt_sha256": H["rebound"],
                        }
                    ],
                },
            },
        }
    ]


def test_research_context_passes_and_is_market_blind():
    assert validate_research_context(research_context())["market_data"] is False


def test_atomic_dual_head_freeze_and_hash_validation():
    frozen = build_frozen_matchup(
        research_context(),
        {"assists": qbase("assists"), "rebounds": qbase("rebounds")},
        projections(),
        frozen_at="2026-09-06T01:05:00Z",
    )
    assert frozen["status"] == "FROZEN"
    assert frozen["requested_heads"] == ["assists", "rebounds"]
    assert frozen["audits"]["atomic_requested_heads"] == "PASS"
    assert frozen["audits"]["server_qbase_authority"] == "PASS"
    assists = frozen["players"][0]["heads"]["assists"]
    assert assists["final_mean"] == pytest.approx(0.2 * 4.7 + 0.6 * 5.6 + 0.2 * 6.2)
    assert assists["server_quantitative_attestation"] == {
        "source": "SERVER_QBASE_RUNTIME_SCORE",
        "receipt_sha256": H["assist_server"],
        "player_prior_key": "testguard",
    }
    assert assists["dispersion_source"] == "QBASE_TEMPORAL_OOS"
    assert assists["probability_grid"]["half_point_grid"]
    for row in assists["probability_grid"]["integer_push_grid"]:
        assert row["over"] + row["push"] + row["under"] == pytest.approx(1.0)
    assert validate_frozen_matchup(frozen) is frozen


def test_both_mode_refuses_partial_head_freeze():
    p = projections()
    del p[0]["heads"]["rebounds"]
    with pytest.raises(ValueError, match="missing requested heads"):
        build_frozen_matchup(research_context(), {"assists": qbase("assists"), "rebounds": qbase("rebounds")}, p)


def test_market_field_contamination_fails_before_freeze():
    c = research_context()
    c["sportsbook_price"] = 2.10
    with pytest.raises(ValueError, match="market-boundary"):
        validate_research_context(c)


def test_scenario_weights_must_sum_exactly_to_one():
    p = projections()
    p[0]["heads"]["assists"]["scenarios"][0]["weight"] = 0.1
    with pytest.raises(ValueError, match="weights must sum"):
        build_frozen_matchup(research_context(), {"assists": qbase("assists"), "rebounds": qbase("rebounds")}, p)


def test_unknown_evidence_source_fails():
    p = projections()
    p[0]["heads"]["rebounds"]["scenarios"][0]["evidence_source_ids"] = ["not-a-source"]
    with pytest.raises(ValueError, match="unknown source ids"):
        build_frozen_matchup(research_context(), {"assists": qbase("assists"), "rebounds": qbase("rebounds")}, p)


def test_out_player_cannot_be_frozen():
    c = research_context()
    c["players"][0]["availability_status"] = "OUT"
    with pytest.raises(ValueError, match="cannot freeze modeled OUT player"):
        build_frozen_matchup(c, {"assists": qbase("assists"), "rebounds": qbase("rebounds")}, projections())


def test_server_attestation_and_scenario_receipts_are_mandatory():
    p = projections()
    del p[0]["heads"]["assists"]["server_qbase_source"]
    with pytest.raises(ValueError, match="server_qbase_source invalid"):
        build_frozen_matchup(research_context(), {"assists": qbase("assists"), "rebounds": qbase("rebounds")}, p)

    p = projections()
    del p[0]["heads"]["rebounds"]["scenarios"][0]["quant_input_receipt_sha256"]
    with pytest.raises(ValueError, match="quant input receipt required"):
        build_frozen_matchup(research_context(), {"assists": qbase("assists"), "rebounds": qbase("rebounds")}, p)


def test_prior_comp_translation_requires_widening_contract():
    p = projections()
    p[0]["heads"]["assists"] = {
        "qbase_mean": 5.8,
        "server_qbase_source": "PRIOR_COMP_TRANSLATION",
        "server_qbase_receipt_sha256": None,
        "server_player_prior_key": None,
        "confidence": "C",
        "fragility": "HIGH",
        "scenarios": [
            {
                "id": "translated",
                "weight": 1.0,
                "mean": 5.8,
                "method": "PRIOR_COMP_TRANSLATION",
                "evidence_source_ids": ["report"],
                "assumptions": ["Prior competition role translated to NBL"],
                "quant_input_receipt_sha256": H["prior"],
            }
        ],
        "dispersion_override": {
            "alpha": 0.5,
            "method": "MAX_QBASE_PRIOR_COMP",
            "receipt_sha256": H["dispersion"],
        },
    }
    frozen = build_frozen_matchup(
        research_context(), {"assists": qbase("assists"), "rebounds": qbase("rebounds")}, p
    )
    assists = frozen["players"][0]["heads"]["assists"]
    assert assists["dispersion_alpha"] == 0.5
    assert assists["dispersion_source"] == "MAX_QBASE_PRIOR_COMP"
    assert assists["server_quantitative_attestation"]["source"] == "PRIOR_COMP_TRANSLATION"

    p[0]["heads"]["assists"]["dispersion_override"]["alpha"] = 0.1
    with pytest.raises(ValueError, match="may not narrow QBASE"):
        build_frozen_matchup(research_context(), {"assists": qbase("assists"), "rebounds": qbase("rebounds")}, p)


def test_translated_head_cannot_claim_returning_player_receipt():
    p = projections()
    h = p[0]["heads"]["assists"]
    h["server_qbase_source"] = "PRIOR_COMP_TRANSLATION"
    h["server_qbase_receipt_sha256"] = H["assist_server"]
    h["server_player_prior_key"] = None
    with pytest.raises(ValueError, match="cannot claim server QBASE receipt"):
        build_frozen_matchup(research_context(), {"assists": qbase("assists"), "rebounds": qbase("rebounds")}, p)


def test_freeze_receipt_detects_mutation():
    frozen = build_frozen_matchup(
        research_context(),
        {"assists": qbase("assists"), "rebounds": qbase("rebounds")},
        projections(),
        frozen_at="2026-09-06T01:05:00Z",
    )
    mutated = copy.deepcopy(frozen)
    mutated["players"][0]["heads"]["assists"]["final_mean"] += 0.01
    with pytest.raises(ValueError, match="hash mismatch"):
        validate_frozen_matchup(mutated)
