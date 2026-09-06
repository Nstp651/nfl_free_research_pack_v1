from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "model"))

from freeze_core import sha256_json  # noqa: E402
from market_adapters import MarketRecord  # noqa: E402
from market_evaluate import evaluate_markets  # noqa: E402
from distribution import probability_grid  # noqa: E402


def frozen():
    core = {
        "schema_version": "nbl_dual_head_freeze_v1",
        "market_data": False,
        "status": "FROZEN",
        "run_mode": "ASSISTS_ONLY",
        "requested_heads": ["assists"],
        "fixture_id": "fixture-1",
        "pack_revision": "pack-1",
        "research_context_sha256": "a" * 64,
        "qbase_sha256": {"assists": "b" * 64},
        "frozen_at": "2026-09-06T01:00:00Z",
        "players": [
            {
                "player_id": "p1",
                "player_name": "Test Guard",
                "team": "Sydney Kings",
                "heads": {
                    "assists": {
                        "confidence": "B",
                        "fragility": "LOW",
                        "probability_grid": probability_grid(5.0, 0.2, 20),
                    }
                },
            }
        ],
        "audits": {"market_boundary": "PASS"},
    }
    return {**core, "freeze_receipt_sha256": sha256_json(core)}


def market(*, threshold=4.5, side="over", price=2.0, book="Book A", fixture="fixture-1"):
    return MarketRecord(
        fixture_id=fixture,
        player_id="p1",
        player_name="Test Guard",
        stat_type="assists",
        side=side,
        threshold=threshold,
        decimal_price=price,
        bookmaker=book,
        captured_at="2026-09-06T01:05:00Z",
        source_type="screenshot",
    )


def test_half_point_ev_uses_exact_frozen_probability_and_does_not_mutate_model():
    f = frozen(); before = copy.deepcopy(f)
    result = evaluate_markets(f, [market(threshold=4.5, side="over", price=2.1)])
    row = result["evaluated"][0]
    assert row["p_push"] == 0.0
    assert row["ev_per_unit"] == pytest.approx(row["p_win"] * 2.1 - 1.0)
    assert f == before


def test_integer_line_is_push_aware():
    result = evaluate_markets(frozen(), [market(threshold=5.0, side="over", price=2.0)])
    row = result["evaluated"][0]
    assert row["p_push"] > 0
    assert row["p_win"] + row["p_push"] + row["p_loss"] == pytest.approx(1.0)
    assert row["ev_per_unit"] == pytest.approx(row["p_win"] - row["p_loss"])
    assert row["fair_decimal_price"] == pytest.approx((1.0 - row["p_push"]) / row["p_win"])


def test_best_price_dedup_keeps_highest_exact_market():
    records = [market(price=1.9, book="Book A"), market(price=2.15, book="Book B")]
    result = evaluate_markets(frozen(), records)
    assert result["market_records_evaluated"] == 1
    assert result["evaluated"][0]["bookmaker"] == "Book B"
    assert result["evaluated"][0]["decimal_price"] == 2.15


def test_exact_threshold_required_no_nearest_line_substitution():
    with pytest.raises(ValueError, match="exact frozen threshold"):
        evaluate_markets(frozen(), [market(threshold=20.5)])


def test_fixture_mismatch_fails_closed():
    with pytest.raises(ValueError, match="does not match frozen fixture"):
        evaluate_markets(frozen(), [market(fixture="wrong-fixture")])


def test_no_positive_edge_means_no_forced_bet():
    result = evaluate_markets(frozen(), [market(threshold=19.5, side="over", price=1.1)])
    assert result["positive_edges"] == []
    assert result["best_single"] is None
    assert result["no_forced_bet"] is True
