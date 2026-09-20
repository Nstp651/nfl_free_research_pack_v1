import unittest

from aleague_player_volume_v1.ingest.api_football import (
    fixture_metadata,
    parse_fixture_players,
    parse_fixture_team_statistics,
    reconcile_fixture,
)


FIXTURE = {
    "fixture": {"id": 1001, "date": "2025-10-17T08:35:00+00:00", "status": {"short": "FT"}},
    "league": {"id": 188, "season": 2025},
    "teams": {
        "home": {"id": 1, "name": "Home FC"},
        "away": {"id": 2, "name": "Away FC"},
    },
}

PLAYERS = {
    "response": [
        {
            "team": {"id": 1, "name": "Home FC"},
            "players": [
                {"player": {"id": 11, "name": "Shooter One"}, "statistics": [{"games": {"minutes": 90, "position": "F", "substitute": False}, "shots": {"total": 3, "on": 1}, "goals": {"conceded": None, "saves": None}}]},
                {"player": {"id": 12, "name": "Home Keeper"}, "statistics": [{"games": {"minutes": 90, "position": "G", "substitute": False}, "shots": {"total": 0, "on": 0}, "goals": {"conceded": 1, "saves": 3}}]},
                {"player": {"id": 13, "name": "Other Home"}, "statistics": [{"games": {"minutes": 90, "position": "M", "substitute": False}, "shots": {"total": 7, "on": 3}, "goals": {"conceded": None, "saves": None}}]},
            ],
        },
        {
            "team": {"id": 2, "name": "Away FC"},
            "players": [
                {"player": {"id": 21, "name": "Away Keeper"}, "statistics": [{"games": {"minutes": 90, "position": "G", "substitute": False}, "shots": {"total": 0, "on": 0}, "goals": {"conceded": 2, "saves": 2}}]},
                {"player": {"id": 22, "name": "Away Shooter"}, "statistics": [{"games": {"minutes": 60, "position": "F", "substitute": False}, "shots": {"total": 6, "on": 4}, "goals": {"conceded": None, "saves": None}}]},
                {"player": {"id": 23, "name": "Away Other"}, "statistics": [{"games": {"minutes": 30, "position": "M", "substitute": True}, "shots": {"total": 2, "on": 0}, "goals": {"conceded": None, "saves": None}}]},
            ],
        },
    ]
}

TEAM_STATS = {
    "response": [
        {"team": {"id": 1}, "statistics": [{"type": "Total Shots", "value": 10}, {"type": "Shots on Goal", "value": 4}]},
        {"team": {"id": 2}, "statistics": [{"type": "Total Shots", "value": 8}, {"type": "Shots on Goal", "value": 4}]},
    ]
}


class ApiFootballIngestTests(unittest.TestCase):
    def setUp(self):
        self.meta = fixture_metadata(FIXTURE, 2025)

    def test_fixture_identity(self):
        self.assertEqual(self.meta["fixture_id"], "apif:1001")
        self.assertEqual(self.meta["season"], "2025-26")
        self.assertEqual(self.meta["home_team_id"], "apif_team:1")

    def test_player_keeper_parse(self):
        players, keepers, names = parse_fixture_players(self.meta, PLAYERS)
        self.assertEqual(len(players), 6)
        self.assertEqual(len(keepers), 2)
        home_keeper = next(row for row in keepers if row.player_id == "apif_player:12")
        self.assertEqual(home_keeper.saves, 3)
        self.assertEqual(home_keeper.shots_on_target_faced, 4)
        self.assertEqual(names["apif_player:11"], "Shooter One")

    def test_team_stats_parse(self):
        rows = parse_fixture_team_statistics(self.meta, TEAM_STATS)
        home = next(row for row in rows if row.is_home)
        self.assertEqual(home.shots_for, 10)
        self.assertEqual(home.sot_against, 4)

    def test_exact_reconciliation(self):
        players, keepers, _ = parse_fixture_players(self.meta, PLAYERS)
        teams = parse_fixture_team_statistics(self.meta, TEAM_STATS)
        receipt = reconcile_fixture(teams, players, keepers)
        self.assertTrue(receipt["exact_team_player_match"])
        self.assertTrue(receipt["exact_keeper_sota_match"])

    def test_partial_player_shots_fail_closed(self):
        broken = {"response": [dict(PLAYERS["response"][0]), PLAYERS["response"][1]]}
        broken["response"][0] = {"team": {"id": 1}, "players": [
            {"player": {"id": 11, "name": "Broken"}, "statistics": [{"games": {"minutes": 90, "position": "F", "substitute": False}, "shots": {"total": 3, "on": None}, "goals": {}}]}
        ]}
        with self.assertRaises(Exception):
            parse_fixture_players(self.meta, broken)


if __name__ == "__main__":
    unittest.main()
