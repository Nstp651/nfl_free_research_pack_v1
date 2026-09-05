import pytest

from model.integrate_market import integrate, validate_frozen


def frozen_fixture():
    return {
        "schema_version": "1.1.0",
        "p_model_status": "FROZEN",
        "frozen_at": "2026-09-05T09:00:00Z",
        "games": [
            {
                "game_id": "401234567",
                "home_team": "Alpha State",
                "away_team": "Beta University",
                "commence_time": "2026-09-06T02:30:00Z",
                "confidence": "B+",
                "fragility": "LOW",
                "frozen_thesis": "Test-only frozen thesis",
                "probability_grid": [
                    {"line": 49.0, "over": 0.50, "push": 0.04, "under": 0.46},
                    {"line": 49.5, "over": 0.48, "push": 0.0, "under": 0.52},
                ],
            }
        ],
    }


def market_board():
    return {
        "service": "NCAAF_TOTALS_MARKET_GATEWAY",
        "version": "0.1.0",
        "sport_key": "americanfootball_ncaaf",
        "region": "au",
        "market_group": "ncaaf-totals",
        "market_key": "totals",
        "retrieved_at": "2026-09-05T09:20:00Z",
        "board_revision": "0123456789abcdef",
        "games": [
            {
                "event_id": "odds-event-1",
                "home_team": "Alpha State",
                "away_team": "Beta University",
                "commence_time": "2026-09-06T02:30:00+00:00",
                "bookmakers": [
                    {
                        "key": "tab",
                        "title": "TAB",
                        "last_update": "2026-09-05T09:18:00Z",
                        "totals": [
                            {"name": "Over", "point": 49.0, "price": 1.95},
                            {"name": "Under", "point": 49.0, "price": 1.95},
                            {"name": "Over", "point": 49.5, "price": 2.05},
                            {"name": "Under", "point": 49.5, "price": 1.80},
                        ],
                    },
                    {
                        "key": "sportsbet",
                        "title": "Sportsbet",
                        "last_update": "2026-09-05T09:00:00Z",
                        "totals": [
                            {"name": "Over", "point": 49.0, "price": 2.00},
                            {"name": "Under", "point": 49.0, "price": 1.90},
                        ],
                    },
                ],
            }
        ],
    }


def test_integer_line_uses_push_aware_math_and_best_price():
    out = integrate(frozen_fixture(), market_board())
    row = next(x for x in out["all_mapped_selections"] if x["side"] == "Over" and x["line"] == 49.0)
    assert row["bookmaker"] == "Sportsbet"  # price wins before recency
    assert row["odds"] == pytest.approx(2.00)
    assert row["p_win"] == pytest.approx(0.50)
    assert row["p_push"] == pytest.approx(0.04)
    assert row["p_break_even_win"] == pytest.approx(0.48)
    assert row["fair_price"] == pytest.approx(1.92)
    assert row["price_edge"] == pytest.approx(0.02)
    assert row["expected_roi"] == pytest.approx(0.04)
    assert row["freshness"] == "CURRENT"


def test_half_point_uses_standard_math():
    out = integrate(frozen_fixture(), market_board())
    row = next(x for x in out["all_mapped_selections"] if x["side"] == "Over" and x["line"] == 49.5)
    assert row["p_push"] == 0
    assert row["p_break_even_win"] == pytest.approx(1 / 2.05)
    assert row["expected_roi"] == pytest.approx(0.48 * 2.05 - 1)


def test_no_post_market_interpolation():
    board = market_board()
    board["games"][0]["bookmakers"][0]["totals"].append({"name": "Over", "point": 50.0, "price": 9.0})
    out = integrate(frozen_fixture(), board)
    assert all(x["line"] != 50.0 for x in out["all_mapped_selections"])


def test_fixture_match_is_fail_closed():
    board = market_board()
    board["games"][0]["home_team"] = "Different State"
    out = integrate(frozen_fixture(), board)
    assert out["matched_selection_count"] == 0
    assert out["unmatched_fixtures"][0]["reason"] == "NO_EXACT_MARKET_FIXTURE_MATCH"


def test_unfrozen_or_invalid_partition_rejected():
    f = frozen_fixture()
    f["p_model_status"] = "DRAFT"
    with pytest.raises(ValueError):
        validate_frozen(f)

    f = frozen_fixture()
    f["games"][0]["probability_grid"][0]["push"] = 0.20
    with pytest.raises(ValueError):
        validate_frozen(f)
