import math
import unittest

from aleague_player_volume_v1.model_core import (
    ModelIntegrityError,
    PlayerShotProjection,
    allocation_audit,
    assert_market_blind,
    build_at_least_ladder,
    expected_goalkeeper_saves,
    expected_player_shots,
    expected_player_sot,
    negative_binomial_pmf,
    shrink_binomial_rate,
)


class ModelCoreTests(unittest.TestCase):
    def test_market_blind_payload_passes(self):
        assert_market_blind({"fixture_id": "a", "players": [{"shots_per90": 2.4}]})

    def test_market_field_rejected_recursively(self):
        with self.assertRaises(ModelIntegrityError):
            assert_market_blind({"research": {"player": {"decimal_price": 2.1}}})

    def test_shrink_rate(self):
        value = shrink_binomial_rate(10, 20, prior_rate=0.30, prior_strength=10)
        self.assertAlmostEqual(value, 13 / 30)

    def test_nb_pmf_sums_close_to_one(self):
        total = sum(negative_binomial_pmf(k, mean=3.2, dispersion=4.0) for k in range(60))
        self.assertAlmostEqual(total, 1.0, places=9)

    def test_ladder_monotonic(self):
        ladder = build_at_least_ladder(mean=2.4, dispersion=3.0, max_threshold=8)
        values = list(ladder.values())
        self.assertTrue(all(a >= b for a, b in zip(values, values[1:])))

    def test_player_shot_projection(self):
        projection = PlayerShotProjection(
            player_id="p1",
            minutes_mean=90,
            normalized_shot_share=0.20,
            role_multiplier=1.10,
        )
        self.assertAlmostEqual(expected_player_shots(15.0, projection), 3.3)

    def test_sot_cannot_exceed_shots_in_mean(self):
        mu_shots = 3.3
        mu_sot = expected_player_sot(mu_shots, 0.4)
        self.assertLessEqual(mu_sot, mu_shots)
        self.assertAlmostEqual(mu_sot, 1.32)

    def test_keeper_saves(self):
        self.assertAlmostEqual(expected_goalkeeper_saves(5.0, 0.72, 90), 3.6)

    def test_allocation_audit_passes(self):
        allocation_audit(10.0, [2.0, 3.0, 4.0], 1.0)

    def test_allocation_audit_fails(self):
        with self.assertRaises(ModelIntegrityError):
            allocation_audit(10.0, [2.0, 3.0], 1.0)


if __name__ == "__main__":
    unittest.main()
