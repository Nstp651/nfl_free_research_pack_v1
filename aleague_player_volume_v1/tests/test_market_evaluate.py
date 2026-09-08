import copy
import unittest

from aleague_player_volume_v1.freeze_core import build_frozen_fixture
from aleague_player_volume_v1.market_adapters import from_screenshot_rows
from aleague_player_volume_v1.market_evaluate import MarketEvaluationError, evaluate_markets, validate_frozen_fixture
from aleague_player_volume_v1.tests.test_freeze_core import keeper_models, outfield_models, research_context, team_models


def frozen_fixture():
    return build_frozen_fixture(
        research_context(),
        team_models(),
        outfield_models(),
        keeper_models(),
        frozen_at="2026-10-10T01:00:00Z",
    )


class MarketEvaluationTests(unittest.TestCase):
    def test_screenshot_aliases_and_best_price(self):
        frozen = frozen_fixture()
        rows = from_screenshot_rows(
            "fixture-1",
            [
                {"player_id": "p1", "player_name": "Home Shooter", "stat_type": "shots", "side": "milestone", "threshold": 2, "decimal_price": 2.00, "bookmaker": "Book A"},
                {"player_id": "p1", "player_name": "Home Shooter", "stat_type": "PLAYER_SHOTS", "side": "AT_LEAST", "threshold": 2, "decimal_price": 2.20, "bookmaker": "Bet365"},
                {"player_id": "p1", "player_name": "Home Shooter", "stat_type": "sot", "side": "over", "threshold": 0.5, "decimal_price": 1.90, "bookmaker": "Bet365"},
                {"player_id": "g1", "player_name": "Home Keeper", "stat_type": "saves", "side": "over", "threshold": 2.5, "decimal_price": 2.10, "bookmaker": "Bet365"},
            ],
            captured_at="2026-10-16T07:00:00Z",
        )
        result = evaluate_markets(frozen, rows)
        self.assertEqual(result["market_records_evaluated"], 3)
        shots = next(row for row in result["evaluated"] if row["stat_type"] == "PLAYER_SHOTS")
        self.assertEqual(shots["decimal_price"], 2.20)
        self.assertEqual(shots["bookmaker"], "Bet365")

    def test_half_point_and_integer_push_are_exact(self):
        frozen = frozen_fixture()
        rows = from_screenshot_rows(
            "fixture-1",
            [
                {"player_id": "p1", "player_name": "Home Shooter", "stat_type": "shots", "side": "over", "threshold": 1.5, "decimal_price": 2.00, "bookmaker": "A"},
                {"player_id": "p1", "player_name": "Home Shooter", "stat_type": "shots", "side": "over", "threshold": 2.0, "decimal_price": 2.50, "bookmaker": "B"},
            ],
            captured_at="2026-10-16T07:00:00Z",
        )
        result = evaluate_markets(frozen, rows)
        integer = next(row for row in result["evaluated"] if row["threshold"] == 2.0)
        self.assertGreaterEqual(integer["p_push"], 0.0)
        self.assertAlmostEqual(integer["p_win"] + integer["p_push"] + integer["p_loss"], 1.0)

    def test_under_can_be_evaluated_but_is_not_default_selection(self):
        frozen = frozen_fixture()
        rows = from_screenshot_rows(
            "fixture-1",
            [{"player_id": "p1", "player_name": "Home Shooter", "stat_type": "shots", "side": "under", "threshold": 7.5, "decimal_price": 10.0, "bookmaker": "A"}],
            captured_at="2026-10-16T07:00:00Z",
        )
        result = evaluate_markets(frozen, rows)
        self.assertEqual(len(result["evaluated"]), 1)
        self.assertFalse(result["evaluated"][0]["selection_eligible"])
        self.assertEqual(result["positive_edges"], [])

    def test_unfrozen_threshold_fails_closed(self):
        frozen = frozen_fixture()
        rows = from_screenshot_rows(
            "fixture-1",
            [{"player_id": "p1", "player_name": "Home Shooter", "stat_type": "sot", "side": "over", "threshold": 5.5, "decimal_price": 100.0, "bookmaker": "A"}],
            captured_at="2026-10-16T07:00:00Z",
        )
        with self.assertRaises(MarketEvaluationError):
            evaluate_markets(frozen, rows)

    def test_unknown_player_fails_closed(self):
        frozen = frozen_fixture()
        rows = from_screenshot_rows(
            "fixture-1",
            [{"player_id": "missing", "player_name": "Missing", "stat_type": "shots", "side": "AT_LEAST", "threshold": 1, "decimal_price": 2.0, "bookmaker": "A"}],
            captured_at="2026-10-16T07:00:00Z",
        )
        with self.assertRaises(MarketEvaluationError):
            evaluate_markets(frozen, rows)

    def test_tampered_freeze_receipt_fails(self):
        frozen = frozen_fixture()
        tampered = copy.deepcopy(frozen)
        tampered["team_environment"]["t1"]["shot_mean"] += 1
        with self.assertRaises(MarketEvaluationError):
            validate_frozen_fixture(tampered)

    def test_market_evaluation_does_not_mutate_freeze(self):
        frozen = frozen_fixture()
        before = copy.deepcopy(frozen)
        rows = from_screenshot_rows(
            "fixture-1",
            [{"player_id": "g1", "player_name": "Home Keeper", "stat_type": "saves", "side": "AT_LEAST", "threshold": 2, "decimal_price": 2.0, "bookmaker": "A"}],
            captured_at="2026-10-16T07:00:00Z",
        )
        evaluate_markets(frozen, rows)
        self.assertEqual(frozen, before)


if __name__ == "__main__":
    unittest.main()
