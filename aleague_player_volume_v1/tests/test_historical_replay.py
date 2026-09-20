import unittest
from dataclasses import replace

from aleague_player_volume_v1.historical_replay import (
    generate_conditional_distribution_replay,
    require_full_prematch_replay,
)
from aleague_player_volume_v1.model_core import ModelIntegrityError
from aleague_player_volume_v1.qbase import GoalkeeperMatch, PlayerMatchShooting, TeamMatchShooting


def p(fixture, kickoff, player, team, opp, minutes, shots, sot, started=True):
    return PlayerMatchShooting(fixture, kickoff, "2025-26", player, team, opp, minutes, started, shots, sot)


def t(fixture, kickoff, team, opp, home, sf, sotf, sa, sota):
    return TeamMatchShooting(fixture, kickoff, "2025-26", team, opp, home, sf, sotf, sa, sota)


def g(fixture, kickoff, player, team, opp, minutes, faced, saves, goals):
    return GoalkeeperMatch(fixture, kickoff, "2025-26", player, team, opp, minutes, faced, saves, goals)


class HistoricalReplayTests(unittest.TestCase):
    def fixture_rows(self):
        kicks = {
            "f1": "2025-10-01T08:00:00Z",
            "f2": "2025-10-08T08:00:00Z",
            "f3": "2025-10-15T08:00:00Z",
        }
        players = [
            p("f1", kicks["f1"], "ha", "H", "A", 80, 3, 1),
            p("f1", kicks["f1"], "aa", "A", "H", 70, 2, 1),
            p("f2", kicks["f2"], "ha", "H", "A", 75, 4, 2),
            p("f2", kicks["f2"], "aa", "A", "H", 65, 1, 0),
            p("f3", kicks["f3"], "ha", "H", "A", 60, 8, 4),
            p("f3", kicks["f3"], "aa", "A", "H", 90, 5, 2),
        ]
        teams = [
            t("f1", kicks["f1"], "H", "A", True, 12, 4, 10, 3),
            t("f1", kicks["f1"], "A", "H", False, 10, 3, 12, 4),
            t("f2", kicks["f2"], "H", "A", True, 14, 6, 9, 3),
            t("f2", kicks["f2"], "A", "H", False, 9, 3, 14, 6),
            t("f3", kicks["f3"], "H", "A", True, 20, 9, 18, 7),
            t("f3", kicks["f3"], "A", "H", False, 18, 7, 20, 9),
        ]
        keepers = [
            g("f1", kicks["f1"], "hg", "H", "A", 90, 3, 2, 1),
            g("f1", kicks["f1"], "ag", "A", "H", 90, 4, 3, 1),
            g("f2", kicks["f2"], "hg", "H", "A", 90, 3, 3, 0),
            g("f2", kicks["f2"], "ag", "A", "H", 90, 6, 4, 2),
            g("f3", kicks["f3"], "hg", "H", "A", 90, 7, 5, 2),
            g("f3", kicks["f3"], "ag", "A", "H", 90, 9, 6, 3),
        ]
        return players, teams, keepers

    @staticmethod
    def observation_map(replay):
        return {(o.fixture_id, o.player_id, o.head): o for o in replay["observations"]}

    def test_future_fixture_cannot_change_earlier_replay(self):
        players, teams, keepers = self.fixture_rows()
        two = generate_conditional_distribution_replay(players[:4], teams[:4], keepers[:4])
        three = generate_conditional_distribution_replay(players, teams, keepers)
        left = self.observation_map(two)
        right = self.observation_map(three)
        for key, earlier in left.items():
            later = right[key]
            self.assertAlmostEqual(earlier.mean, later.mean, places=12)
            self.assertAlmostEqual(earlier.baseline_mean, later.baseline_mean, places=12)

    def test_target_minutes_and_counts_do_not_enter_same_match_mean(self):
        players, teams, keepers = self.fixture_rows()
        base = generate_conditional_distribution_replay(players[:4], teams[:4], keepers[:4])
        changed_players = list(players[:4])
        changed_players[2] = replace(changed_players[2], minutes=5, shots=20, shots_on_target=10)
        changed = generate_conditional_distribution_replay(changed_players, teams[:4], keepers[:4])
        a = self.observation_map(base)
        b = self.observation_map(changed)
        self.assertAlmostEqual(a[("f2", "ha", "SHOTS")].mean, b[("f2", "ha", "SHOTS")].mean, places=12)
        self.assertAlmostEqual(a[("f2", "ha", "SOT")].mean, b[("f2", "ha", "SOT")].mean, places=12)
        self.assertNotEqual(a[("f2", "ha", "SHOTS")].actual_count, b[("f2", "ha", "SHOTS")].actual_count)

    def test_conditional_replay_cannot_satisfy_production_edge_gate(self):
        players, teams, keepers = self.fixture_rows()
        replay = generate_conditional_distribution_replay(players[:4], teams[:4], keepers[:4])
        self.assertEqual(replay["selection_integrity"], "INSUFFICIENT_FOR_PRODUCTION_EDGE_ACCEPTANCE")
        self.assertIn("PRODUCTION_READY_GATE", replay["prohibited_uses"])
        with self.assertRaises(ModelIntegrityError):
            require_full_prematch_replay(replay)

    def test_replay_observation_timestamps_are_strictly_prematch(self):
        players, teams, keepers = self.fixture_rows()
        replay = generate_conditional_distribution_replay(players[:4], teams[:4], keepers[:4])
        for observation in replay["observations"]:
            observation.validate()


if __name__ == "__main__":
    unittest.main()
