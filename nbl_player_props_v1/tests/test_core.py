from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from build_match_pack import resolve_fixture  # noqa: E402
from market_adapters import MarketRecord, best_price, from_screenshot_rows  # noqa: E402
from source_client import market_key_hits  # noqa: E402


def test_fixture_resolution_is_orientation_tolerant():
    schedule = [{
        "id": "m1",
        "home_team": {"id": "h", "name": "Sydney Kings"},
        "away_team": {"id": "a", "name": "Melbourne United"},
    }]
    assert resolve_fixture(schedule, None, "Sydney Kings", "Melbourne United")["id"] == "m1"
    assert resolve_fixture(schedule, None, "Melbourne United", "Sydney Kings")["id"] == "m1"
    assert resolve_fixture(schedule, "m1", None, None)["id"] == "m1"


def test_market_boundary_audit():
    clean = {"player": {"assists": 5, "rebounds": 7}, "market_data": False}
    assert market_key_hits(clean) == []
    dirty = {"sportsbook_odds": 1.9}
    assert market_key_hits(dirty)


def test_screenshot_adapter_and_best_price():
    rows = [
        {"player_name": "Example Guard", "stat_type": "assists", "side": "over",
         "threshold": 5.5, "decimal_price": 1.90, "bookmaker": "Book A"},
        {"player_name": "Example Guard", "stat_type": "assists", "side": "over",
         "threshold": 5.5, "decimal_price": 2.05, "bookmaker": "Book B"},
    ]
    recs = from_screenshot_rows("fx1", rows, "2026-09-06T00:00:00+00:00")
    assert len(recs) == 2
    best = best_price(recs)
    assert len(best) == 1
    assert best[0].decimal_price == 2.05
    assert best[0].source_type == "screenshot"


def test_market_record_rejects_invalid_stat():
    try:
        MarketRecord(
            fixture_id="x", player_name="P", stat_type="points", side="over",
            threshold=10.5, decimal_price=2.0, bookmaker="B",
            captured_at="2026-09-06T00:00:00+00:00", source_type="screenshot",
        ).validate()
    except ValueError:
        return
    raise AssertionError("invalid stat accepted")
