import tempfile
import unittest
from pathlib import Path

from aleague_player_volume_v1.publication import build_manifest, sha256_bytes, verify_manifest, write_jsonl


class PublicationTests(unittest.TestCase):
    def test_jsonl_is_deterministic_and_hash_locked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            asset = write_jsonl(root / "data.jsonl", [
                {"fixture_id": "b", "kickoff_utc": "2025-02-02T00:00:00Z", "x": 2},
                {"fixture_id": "a", "kickoff_utc": "2025-01-01T00:00:00Z", "x": 1},
            ])
            relative = dict(asset)
            relative["path"] = "data.jsonl"
            manifest = build_manifest(source_id="test", season="2025-26", assets=[relative], source_receipt={"ok": True})
            verify_manifest(root, manifest)
            first = (root / "data.jsonl").read_bytes()
            asset2 = write_jsonl(root / "data2.jsonl", [
                {"fixture_id": "a", "kickoff_utc": "2025-01-01T00:00:00Z", "x": 1},
                {"fixture_id": "b", "kickoff_utc": "2025-02-02T00:00:00Z", "x": 2},
            ])
            self.assertEqual(asset["sha256"], asset2["sha256"])
            self.assertEqual(asset["sha256"], sha256_bytes(first))


if __name__ == "__main__":
    unittest.main()
