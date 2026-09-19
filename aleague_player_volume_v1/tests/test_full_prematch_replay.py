import unittest
from dataclasses import replace

from aleague_player_volume_v1.full_prematch_replay import generate_snapshot_participant_replay
from aleague_player_volume_v1.prematch_snapshot import PrematchParticipant, PrematchSnapshot
from aleague_player_volume_v1.qbase import GoalkeeperMatch, PlayerMatchShooting, TeamMatchShooting


def p(fixture, kickoff, player, team, opp, minutes, shots, sot):
    return PlayerMatchShooting(fixture, kickoff, "2025-26", player, team, opp, minutes, True, shots, sot)


def t(fixture, kickoff, team, opp, home, sf, sotf, sa, sota):
    return TeamMatchShooting(fixture, kickoff, "2025-26", team, opp, home, sf, sotf, sa, sota)


def g(fixture, kickoff, player, team, opp, minutes, faced, saves, goals):
    return GoalkeeperMatch(fixture, kickoff, "2025-26", player, team, opp, minutes, faced, saves, goals)


class FullPrematchReplayTests(unittest.TestCase):
    def data(self):
        k1 = "2025-10-01T08:00:00Z"
        k2 = "2025-10-08T08:00:00Z"
        players = [
            p("f1", k1, "h1", "H", "A", 80, 3, 1),
            p("f1", k1, "a1", "A", "H", 75, 2, 1),
            p("f2", k2, "h1", "H", "A", 50, 9, 5),
            p("f2", k2, "a1", "A", "H", 90, 4, 2),
        ]
        teams = [
            t("f1", k1, "H", "A", True, 12, 4, 10, 3),
            t("f1", k1, "A", "H", False, 10, 3, 12, 4),
            t("f2", k2, "H", "A", True, 20, 10, 18, 8),
            t("f2", k2, "A", "H", False, 18, 8, 20, 10),
        ]
        keepers = [
            g("f1", k1, "hg", "H", "A", 90, 3, 2, 1),
            g("f1", k1, "ag", "A", "H", 90, 4, 3, 1),
            g("f2", k2, "hg", "H", "A", 90, 8, 6, 2),
            g("f2", k2, "ag", "A", "H", 90, 10, 7, 3),
        ]
        source = {"s": {"title": "Official team news", "url": "https://example.com/team", "checked_at_utc": "2025-10-08T01:00:00Z"}}
        snapshot = PrematchSnapshot(
            fixture_id="f2",
            kickoff_utc=k2,
            captured_at_utc="2025-10-08T02:00:00Z",
            home_team_id="H",
            away_team_id="A",
            source_type="PERSISTED_PREMATCH_RESEARCH_SNAPSHOT",
            source_revision="r1",
            evidence_sources=source,
            participants=(
                PrematchParticipant("h1", "Home One", "H", "OUTFIELD", "EXPECTED_ACTIVE", 65, 78, 90, ("s",)),
                PrematchParticipant("h2", "Home Two", "H", "OUTFIELD", "EXPECTED_BENCH", 10, 20, 35, ("s",)),
                PrematchParticipant("hg", "Home GK", "H", "GOALKEEPER", "EXPECTED_ACTIVE", 90, 90, 90, ("s",)),
                PrematchParticipant("a1", "Away One", "A", "OUTFIELD", "EXPECTED_ACTIVE", 65, 80, 90, ("s",)),
                PrematchParticipant("ag", "Away GK", "A", "GOALKEEPER", "EXPECTED_ACTIVE", 90, 90, 90, ("s",)),
            ),
        )
        return players, teams, keepers, snapshot

    @staticmethod
    def obs_map(replay):
        return {(o.fixture_id, o.player_id, o.head): o for o in replay["observations"]}

    def test_target_actuals_do_not_change_same_match_forecast(self):
        players, teams, keepers, snapshot = self.data()
        base = generate_snapshot_participant_replay([snapshot], players, teams, keepers)
        changed_players = list(players)
        changed_players[2] = replace(changed_players[2], minutes=5, shots=20, shots_on_target=10)
        changed = generate_snapshot_participant_replay([snapshot], changed_players, teams, keepers)
        a = self.obs_map(base)[("f2", "h1", "SHOTS")]
        b = self.obs_map(changed)[("f2", "h1", "SHOTS")]
        self.assertAlmostEqual(a.mean, b.mean, places=12)
        self.assertNotEqual(a.actual_count, b.actual_count)

    def test_snapshot_minutes_do_change_forecast(self):
        players, teams, keepers, snapshot = self.data()
        base = generate_snapshot_participant_replay([snapshot], players, teams, keepers)
        participants = list(snapshot.participants)
        participants[0] = replace(participants[0], minutes_low=85, minutes_mean=90, minutes_high=90)
        changed_snapshot = replace(snapshot, participants=tuple(participants))
        changed = generate_snapshot_participant_replay([changed_snapshot], players, teams, keepers)
        a = self.obs_map(base)[("f2", "h1", "SHOTS")]
        b = self.obs_map(changed)[("f2", "h1", "SHOTS")]
        self.assertNotAlmostEqual(a.mean, b.mean, places=8)
        self.assertEqual(a.forecast_created_utc, snapshot.captured_at_utc)

    def test_prematch_selected_dnp_is_void_not_zero_loss(self):
        players, teams, keepers, snapshot = self.data()
        replay = generate_snapshot_participant_replay([snapshot], players, teams, keepers)
        self.assertTrue(any(v["player_id"] == "h2" for v in replay["void_participants"]))
        self.assertFalse(any(o.player_id == "h2" for o in replay["observations"]))
        self.assertEqual(replay["selection_integrity"], "FULL_PREMATCH_PARTICIPANT_SET_ONLY")
        self.assertEqual(replay["production_edge_acceptance"], "BLOCKED_REQUIRES_PERSISTED_PREMATCH_MODEL_INPUTS")

    def test_target_team_stats_do_not_change_forecast_environment(self):
        players, teams, keepers, snapshot = self.data()
        base = generate_snapshot_participant_replay([snapshot], players, teams, keepers)
        changed_teams = list(teams)
        changed_teams[2] = replace(changed_teams[2], shots_for=50, sot_for=30, shots_against=40, sot_against=20)
        changed_teams[3] = replace(changed_teams[3], shots_for=40, sot_for=20, shots_against=50, sot_against=30)
        changed = generate_snapshot_participant_replay([snapshot], players, changed_teams, keepers)
        self.assertAlmostEqual(
            self.obs_map(base)[("f2", "h1", "SHOTS")].mean,
            self.obs_map(changed)[("f2", "h1", "SHOTS")].mean,
            places=12,
        )


if __name__ == "__main__":
    unittest.main()
