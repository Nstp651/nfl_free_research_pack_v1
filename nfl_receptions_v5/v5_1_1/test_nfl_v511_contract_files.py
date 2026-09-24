import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class ContractFileTests(unittest.TestCase):
    def test_control_openapi_is_valid_json_and_exposes_full_freeze(self):
        spec = json.loads((ROOT / "openapi_builder_v511.json").read_text())
        freeze = spec["components"]["schemas"]["Freeze"]
        self.assertIn("source_to_parameter_ledger", freeze["properties"])
        self.assertIn("players", freeze["properties"])
        op = spec["paths"]["/v1/runs/{run_id}/freeze"]["get"]
        self.assertEqual(op["operationId"], "getNflReceptionsFrozenArtifactV5")

    def test_control_operation_ids_remain_v5_compatible(self):
        spec = json.loads((ROOT / "openapi_builder_v511.json").read_text())
        blob = json.dumps(spec)
        for op in [
            "createNflReceptionsRunV5", "getNflReceptionsResearchV5",
            "checkpointNflReceptionsResearchV5", "computeNflReceptionsFreezeV5",
            "getNflReceptionsFrozenArtifactV5", "getNflReceptionsFrozenPlayerV5",
        ]:
            self.assertIn(op, blob)

    def test_market_schema_exposes_complete_board_fields(self):
        text = (ROOT / "market_openapi_v511.yaml").read_text()
        for token in ["best_prices:", "mapped_selection_count:", "reception_threshold:", "last_update:", "positive_edge_ranked:"]:
            self.assertIn(token, text)
        self.assertIn("audit view only", text)

    def test_builder_revision_fits_field_and_requires_registry(self):
        text = (ROOT / "GPT_INSTRUCTIONS_BUILDER_V5.1.1_R2.md").read_text()
        self.assertLess(len(text), 8000)
        self.assertIn("selection_eligibility.<player_id>", text)
        self.assertIn("best_prices", text)
        self.assertIn("MARKET INPUT REQUIRED", text)

    def test_builder_has_no_universal_50_percent_core_floor(self):
        text = (ROOT / "GPT_INSTRUCTIONS_BUILDER_V5.1.1_R2.md").read_text()
        self.assertNotIn("p>=.50", text)
        self.assertNotIn("P_model >= 50%", text)
        self.assertIn("p>=.30", text)
        self.assertIn(".20<=p<.30", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
