import unittest

from aleague_player_volume_v1.model_core import ModelIntegrityError
from aleague_player_volume_v1.prematch_snapshot import (
    PrematchParticipant,
    PrematchSnapshot,
    snapshot_from_dict,
    validate_snapshot_series,
)


class PrematchSnapshotTests(unittest.TestCase):
    def snapshot(self):
        source = {
            "official": {
                "title": "Official squad update",
                "url": "https://example.com/squad",
                "checked_at_utc": "2026-10-01T00:30:00Z",
            }
        }
        participants = (
            PrematchParticipant("h1", "Home Forward", "H", "OUTFIELD", "EXPECTED_ACTIVE", 65, 78, 90, ("official",)),
            PrematchParticipant("hg", "Home Keeper", "H", "GOALKEEPER", "EXPECTED_ACTIVE", 90, 90, 90, ("official",)),
            PrematchParticipant("a1", "Away Forward", "A", "OUTFIELD", "EXPECTED_ACTIVE", 60, 75, 88, ("official",)),
            PrematchParticipant("ag", "Away Keeper", "A", "GOALKEEPER", "EXPECTED_ACTIVE", 90, 90, 90, ("official",)),
        )
        return PrematchSnapshot(
            fixture_id="fixture-1",
            kickoff_utc="2026-10-02T08:00:00Z",
            captured_at_utc="2026-10-01T01:00:00Z",
            home_team_id="H",
            away_team_id="A",
            source_type="PERSISTED_PREMATCH_RESEARCH_SNAPSHOT",
            source_revision="research-rev-1",
            evidence_sources=source,
            participants=participants,
        )

    def test_roundtrip_receipt(self):
        value = self.snapshot().to_dict()
        self.assertRegex(value["snapshot_receipt_sha256"], r"^[0-9a-f]{64}$")
        parsed = snapshot_from_dict(value)
        self.assertEqual(parsed.fixture_id, "fixture-1")
        self.assertEqual(len(parsed.participants), 4)

    def test_snapshot_must_preexist_kickoff(self):
        snapshot = self.snapshot()
        broken = PrematchSnapshot(**{**snapshot.__dict__, "captured_at_utc": snapshot.kickoff_utc})
        with self.assertRaises(ModelIntegrityError):
            broken.validate()

    def test_market_leakage_rejected(self):
        snapshot = self.snapshot()
        broken_sources = dict(snapshot.evidence_sources)
        broken_sources["official"] = {**broken_sources["official"], "odds": 2.10}
        broken = PrematchSnapshot(**{**snapshot.__dict__, "evidence_sources": broken_sources})
        with self.assertRaises(ModelIntegrityError):
            broken.validate()

    def test_out_player_must_have_zero_minutes(self):
        snapshot = self.snapshot()
        players = list(snapshot.participants)
        players[0] = PrematchParticipant("h1", "Home Forward", "H", "OUTFIELD", "OUT", 0, 5, 10, ("official",))
        broken = PrematchSnapshot(**{**snapshot.__dict__, "participants": tuple(players)})
        with self.assertRaises(ModelIntegrityError):
            broken.validate()

    def test_receipt_tamper_fails(self):
        value = self.snapshot().to_dict()
        value["participants"][0]["minutes_mean"] = 89
        with self.assertRaises(ModelIntegrityError):
            snapshot_from_dict(value)

    def test_duplicate_fixture_snapshot_fails(self):
        snapshot = self.snapshot()
        with self.assertRaises(ModelIntegrityError):
            validate_snapshot_series([snapshot, snapshot])


if __name__ == "__main__":
    unittest.main()
