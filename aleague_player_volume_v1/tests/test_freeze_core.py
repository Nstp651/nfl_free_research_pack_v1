import unittest

from aleague_player_volume_v1.freeze_core import build_frozen_fixture
from aleague_player_volume_v1.model_core import ModelIntegrityError
from aleague_player_volume_v1.research_contract import SCHEMA_VERSION, validate_research_context


H = "a" * 64


def research_context():
    source = {"title": "Official team report", "url": "https://example.com/report", "checked_at": "2026-10-10T00:00:00Z"}
    return {
        "schema_version": SCHEMA_VERSION,
        "market_data": False,
        "run_mode": "ALL",
        "fixture_id": "fixture-1",
        "pack_revision": "pack-123",
        "checked_at": "2026-10-10T00:00:00Z",
        "sources": {"s1": source},
        "fixture_context": {
            "home_team_id": "t1", "away_team_id": "t2", "kickoff_utc": "2026-10-16T08:00:00Z", "status": "SCHEDULED", "source_ids": ["s1"]
        },
        "teams": [
            {"team_id": "t1", "team_name": "Home", "source_ids": ["s1"], "notes": ["Current attacking context researched"]},
            {"team_id": "t2", "team_name": "Away", "source_ids": ["s1"], "notes": ["Current defensive context researched"]},
        ],
        "players": [
            {"player_id": "p1", "player_name": "Home Shooter", "team_id": "t1", "player_type": "OUTFIELD", "availability_status": "ACTIVE", "availability_source_ids": ["s1"], "projected_minutes": {"low": 75, "mean": 85, "high": 90, "source_ids": ["s1"]}, "role": {"state": "RETURNING_SAME", "position_role": "CF", "source_ids": ["s1"], "notes": ["Starting striker"]}, "stat_context": {"shots": {"source_ids": ["s1"], "notes": ["Primary shooter"]}, "shots_on_target": {"source_ids": ["s1"], "notes": ["Stable shot accuracy"]}}},
            {"player_id": "p2", "player_name": "Away Shooter", "team_id": "t2", "player_type": "OUTFIELD", "availability_status": "ACTIVE", "availability_source_ids": ["s1"], "projected_minutes": {"low": 70, "mean": 80, "high": 90, "source_ids": ["s1"]}, "role": {"state": "RETURNING_CHANGED", "position_role": "WIDE_FORWARD", "source_ids": ["s1"], "notes": ["More advanced current role"]}, "stat_context": {"shots": {"source_ids": ["s1"], "notes": ["Shot role reviewed"]}, "shots_on_target": {"source_ids": ["s1"], "notes": ["SOT profile reviewed"]}}},
            {"player_id": "g1", "player_name": "Home Keeper", "team_id": "t1", "player_type": "GOALKEEPER", "availability_status": "ACTIVE", "availability_source_ids": ["s1"], "projected_minutes": {"low": 90, "mean": 90, "high": 90, "source_ids": ["s1"]}, "role": {"state": "RETURNING_SAME", "position_role": "GK", "source_ids": ["s1"], "notes": ["Confirmed first-choice keeper"]}, "stat_context": {"saves": {"source_ids": ["s1"], "notes": ["Save opportunity researched"]}}},
            {"player_id": "g2", "player_name": "Away Keeper", "team_id": "t2", "player_type": "GOALKEEPER", "availability_status": "ACTIVE", "availability_source_ids": ["s1"], "projected_minutes": {"low": 90, "mean": 90, "high": 90, "source_ids": ["s1"]}, "role": {"state": "RETURNING_SAME", "position_role": "GK", "source_ids": ["s1"], "notes": ["Confirmed first-choice keeper"]}, "stat_context": {"saves": {"source_ids": ["s1"], "notes": ["Save profile researched"]}}},
        ],
    }


def team_models():
    return [
        {"team_id": "t1", "shot_mean": 14.0, "shot_dispersion": 7.0, "unmodelled_weight": 7.0, "unmodelled_p_sot": 0.32, "evidence_source_ids": ["s1"], "quant_input_receipt_sha256": H},
        {"team_id": "t2", "shot_mean": 10.0, "shot_dispersion": 6.0, "unmodelled_weight": 6.0, "unmodelled_p_sot": 0.31, "evidence_source_ids": ["s1"], "quant_input_receipt_sha256": H},
    ]


def outfield_models():
    return [
        {"player_id": "p1", "team_id": "t1", "shots_per90_prior": 3.6, "role_multiplier": 1.1, "p_sot_given_shot": 0.40, "shot_dispersion": 4.0, "confidence": "A", "fragility": "LOW", "evidence_source_ids": ["s1"], "quant_input_receipt_sha256": H},
        {"player_id": "p2", "team_id": "t2", "shots_per90_prior": 2.7, "role_multiplier": 1.15, "p_sot_given_shot": 0.35, "shot_dispersion": 3.5, "confidence": "B", "fragility": "MEDIUM", "evidence_source_ids": ["s1"], "quant_input_receipt_sha256": H},
    ]


def keeper_models():
    return [
        {"player_id": "g1", "team_id": "t1", "p_save_given_sot": 0.72, "save_dispersion": 5.0, "confidence": "B", "fragility": "LOW", "evidence_source_ids": ["s1"], "quant_input_receipt_sha256": H},
        {"player_id": "g2", "team_id": "t2", "p_save_given_sot": 0.70, "save_dispersion": 5.0, "confidence": "B", "fragility": "LOW", "evidence_source_ids": ["s1"], "quant_input_receipt_sha256": H},
    ]


class FreezeCoreTests(unittest.TestCase):
    def test_research_contract_market_blind(self):
        context = research_context()
        context["odds"] = 2.0
        with self.assertRaises(Exception):
            validate_research_context(context)

    def test_freeze_is_coherent_and_deterministic(self):
        kwargs = dict(
            research_context=research_context(), team_models=team_models(), outfield_models=outfield_models(), goalkeeper_models=keeper_models(), frozen_at="2026-10-10T01:00:00Z"
        )
        first = build_frozen_fixture(**kwargs)
        second = build_frozen_fixture(**kwargs)
        self.assertEqual(first["freeze_receipt_sha256"], second["freeze_receipt_sha256"])
        self.assertEqual(first["market_data"], False)
        self.assertEqual(len(first["outfield_players"]), 2)
        self.assertEqual(len(first["goalkeepers"]), 2)
        for team in first["team_environment"].values():
            self.assertLessEqual(team["sot_mean"], team["shot_mean"])
        for player in first["outfield_players"]:
            shots = player["heads"]["PLAYER_SHOTS"]
            sot = player["heads"]["PLAYER_SHOTS_ON_TARGET"]
            self.assertLessEqual(sot["mean"], shots["mean"])
            self.assertGreaterEqual(sot["at_least"]["1"], sot["at_least"]["2"])

    def test_keeper_uses_opponent_frozen_sot(self):
        frozen = build_frozen_fixture(research_context(), team_models(), outfield_models(), keeper_models(), frozen_at="2026-10-10T01:00:00Z")
        home_keeper = next(row for row in frozen["goalkeepers"] if row["team_id"] == "t1")
        saves = home_keeper["heads"]["GOALKEEPER_SAVES"]
        self.assertAlmostEqual(saves["opponent_sot_mean"], frozen["team_environment"]["t2"]["sot_mean"])
        self.assertAlmostEqual(saves["mean"], saves["opponent_sot_mean"] * 0.72)

    def test_market_input_rejected_pre_freeze(self):
        models = team_models()
        models[0]["price"] = 2.1
        with self.assertRaises(Exception):
            build_frozen_fixture(research_context(), models, outfield_models(), keeper_models(), frozen_at="2026-10-10T01:00:00Z")

    def test_out_player_cannot_freeze(self):
        context = research_context()
        context["players"][0]["availability_status"] = "OUT"
        with self.assertRaises(ModelIntegrityError):
            build_frozen_fixture(context, team_models(), outfield_models(), keeper_models(), frozen_at="2026-10-10T01:00:00Z")


if __name__ == "__main__":
    unittest.main()
