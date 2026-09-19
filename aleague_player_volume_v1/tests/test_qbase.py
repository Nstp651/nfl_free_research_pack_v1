import unittest

from aleague_player_volume_v1.qbase import (
    GoalkeeperMatch,
    PlayerMatchShooting,
    TeamMatchShooting,
    build_keeper_prematch_priors,
    build_player_prematch_priors,
    build_team_prematch_priors,
)


class QbaseLeakageTests(unittest.TestCase):
    def _player_rows(self):
        return [
            PlayerMatchShooting("f1", "2025-10-01T09:00:00Z", "2025-26", "p1", "t1", "t2", 90, True, 4, 2),
            PlayerMatchShooting("f2", "2025-10-08T09:00:00Z", "2025-26", "p1", "t1", "t3", 90, True, 2, 1),
            PlayerMatchShooting("f3", "2025-10-15T09:00:00Z", "2025-26", "p1", "t1", "t4", 60, True, 1, 0),
        ]

    def test_player_snapshot_is_prematch(self):
        priors = build_player_prematch_priors(self._player_rows())
        self.assertEqual(priors[0]["history_matches"], 0)
        self.assertEqual(priors[1]["history_matches"], 1)
        self.assertEqual(priors[1]["history_minutes"], 90)

    def test_future_row_does_not_change_earlier_player_prior(self):
        rows = self._player_rows()
        base = build_player_prematch_priors(rows[:2])
        extended = build_player_prematch_priors(rows)
        self.assertEqual(base[0], extended[0])
        self.assertEqual(base[1], extended[1])

    def test_keeper_prior_uses_only_history(self):
        rows = [
            GoalkeeperMatch("f1", "2025-10-01T09:00:00Z", "2025-26", "g1", "t1", "t2", 90, 5, 4, 1),
            GoalkeeperMatch("f2", "2025-10-08T09:00:00Z", "2025-26", "g1", "t1", "t3", 90, 4, 2, 2),
        ]
        priors = build_keeper_prematch_priors(rows, league_save_rate_prior=0.70, save_prior_sot=20)
        self.assertAlmostEqual(priors[0]["p_save_given_sot_prior"], 0.70)
        self.assertAlmostEqual(priors[1]["p_save_given_sot_prior"], (4 + 14) / 25)

    def test_team_future_row_does_not_change_earlier_prior(self):
        rows = [
            TeamMatchShooting("f1", "2025-10-01T09:00:00Z", "2025-26", "t1", "t2", True, 15, 5, 10, 3),
            TeamMatchShooting("f2", "2025-10-08T09:00:00Z", "2025-26", "t1", "t3", False, 9, 3, 14, 6),
            TeamMatchShooting("f3", "2025-10-15T09:00:00Z", "2025-26", "t1", "t4", True, 20, 8, 8, 2),
        ]
        base = build_team_prematch_priors(rows[:2])
        extended = build_team_prematch_priors(rows)
        self.assertEqual(base[0], extended[0])
        self.assertEqual(base[1], extended[1])


if __name__ == "__main__":
    unittest.main()
