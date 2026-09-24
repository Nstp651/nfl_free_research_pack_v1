import json
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
TRACKER = HERE.parent / "tracker_openapi_builder_v2.json"


class TrackerContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = json.loads(TRACKER.read_text())

    def test_existing_model_name_remains_compatible(self):
        req = self.spec["components"]["schemas"]["CreateModelRunRequest"]
        self.assertEqual(req["properties"]["model_name"]["enum"], ["NFL Receptions V5"])

    def test_selection_fields_can_separate_registry_from_recommendation(self):
        sel = self.spec["components"]["schemas"]["ModelSelectionInput"]
        self.assertIn("final_play", sel["required"])
        self.assertIn("final_rank", sel["properties"])
        self.assertIn("ranking_score", sel["properties"])
        self.assertIn("notes", sel["properties"])

    def test_frozen_selection_ensure_operation_exists(self):
        op = self.spec["paths"]["/tracker/model-runs/{model_run_id}/selections/ensure"]["post"]
        self.assertEqual(op["operationId"], "ensureNflReceptionsFrozenSelection")
        req = self.spec["components"]["schemas"]["EnsureFrozenSelectionRequest"]
        self.assertEqual(set(req["required"]), {"v5_run_id", "freeze_receipt_sha256", "player_id", "threshold"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
