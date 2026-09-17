import json
import unittest
from nfl_v511_adapter import normalize_v511_inputs, execute_v511
from nfl_v511_selector import select

RID = "a" * 64
REC = "b" * 64


def elig(pid, **kw):
    base = {
        "v": 1,
        "position": "WR",
        "include": "INCLUDE",
        "receiver_class": "PRIMARY TARGET EARNER",
        "role": "STABLE",
        "pathway_usable": True,
        "evidence_score": 14,
        "availability_score": 2,
        "role_score": 2,
        "threshold_fragility": {"3": "LOW", "4": "LOW", "5": "LOW"},
    }
    base.update(kw)
    return {
        "parameter_path": f"selection_eligibility.{pid}",
        "evidence_ids": ["E1"],
        "rationale": json.dumps(base, separators=(",", ":"), sort_keys=True),
    }


def freeze_response():
    return {
        "run_id": RID,
        "p_model_status": "FROZEN",
        "freeze": {
            "freeze_receipt_sha256": REC,
            "players": [
                {"player_id": "AAA", "player_name": "Alpha", "team": "BUF", "confidence": "HIGH", "fragility": "LOW", "ladder": {"3": .55, "4": .36, "5": .18}},
                {"player_id": "BBB", "player_name": "Beta", "team": "DET", "confidence": "HIGH", "fragility": "LOW", "ladder": {"3": .50, "4": .25, "5": .10}},
            ],
            "source_to_parameter_ledger": [
                {"parameter_path": "selection_policy.research_quality_permission", "evidence_ids": ["E1"], "rationale": '{"permission":"YES","v":1}'},
                elig("AAA"),
                elig("BBB", position="TE"),
            ],
        },
    }


def market_response():
    return {
        "run_id": RID,
        "freeze_receipt_sha256": REC,
        "mapped_selection_count": 3,
        "best_prices": [
            {"player_id":"AAA","reception_threshold":3,"p_model":.55,"price":2.1,"bookmaker_key":"bet365","bookmaker":"Bet365","last_update":"2026-09-17T20:00:00Z","market_key":"player_receptions"},
            {"player_id":"AAA","reception_threshold":4,"p_model":.36,"price":3.4,"bookmaker_key":"sportsbet","bookmaker":"Sportsbet","last_update":"2026-09-17T20:00:00Z","market_key":"player_receptions_alternate"},
            {"player_id":"BBB","reception_threshold":4,"p_model":.25,"price":5.0,"bookmaker_key":"tab","bookmaker":"TAB","last_update":"2026-09-17T20:00:00Z","market_key":"player_receptions_alternate"},
        ],
    }


class AdapterTests(unittest.TestCase):
    def test_normalizes_actual_worker_shapes(self):
        x = normalize_v511_inputs(freeze_response(), market_response(), now_epoch=1789675800)
        self.assertTrue(x["integrity_verified"])
        self.assertEqual(len(x["rows"]), 3)
        self.assertEqual(x["players"]["BBB"]["position"], "TE")

    def test_end_to_end_selector(self):
        result = execute_v511(freeze_response(), market_response(), now_epoch=1789675800)
        self.assertEqual(result["decision"], "BET")
        self.assertEqual(result["selected_player"], "AAA")

    def test_receipt_conflict_blocks(self):
        m = market_response(); m["freeze_receipt_sha256"] = "c" * 64
        with self.assertRaises(RuntimeError):
            normalize_v511_inputs(freeze_response(), m, now_epoch=1789675800)

    def test_registry_must_cover_every_frozen_player(self):
        f = freeze_response(); f["freeze"]["source_to_parameter_ledger"] = f["freeze"]["source_to_parameter_ledger"][:-1]
        with self.assertRaises(ValueError):
            normalize_v511_inputs(f, market_response(), now_epoch=1789675800)

    def test_market_count_must_match_board(self):
        m = market_response(); m["mapped_selection_count"] = 99
        with self.assertRaises(ValueError):
            normalize_v511_inputs(freeze_response(), m, now_epoch=1789675800)

    def test_missing_quote_time_cannot_create_recommendation(self):
        m = market_response()
        for row in m["best_prices"]: row["last_update"] = None
        self.assertEqual(execute_v511(freeze_response(), m, now_epoch=1789675800)["decision"], "MARKET INPUT REQUIRED")

    def test_research_permission_no_blocks(self):
        f = freeze_response(); f["freeze"]["source_to_parameter_ledger"][0]["rationale"] = '{"permission":"NO","v":1}'
        x = normalize_v511_inputs(f, market_response(), now_epoch=1789675800)
        self.assertFalse(x["research_permission"])
        self.assertEqual(execute_v511(f, market_response(), now_epoch=1789675800)["decision"], "RESEARCH QUALITY BLOCKED")

    def test_threshold_fragility_transfers(self):
        x = normalize_v511_inputs(freeze_response(), market_response(), now_epoch=1789675800)
        a4 = next(r for r in x["rows"] if r["player_id"] == "AAA" and r["k"] == 4)
        self.assertEqual(a4["threshold_fragility"], "LOW")

    def test_invalid_registry_enum_blocks(self):
        f = freeze_response()
        f["freeze"]["source_to_parameter_ledger"][1] = elig("AAA", position="QB")
        with self.assertRaises(ValueError):
            normalize_v511_inputs(f, market_response(), now_epoch=1789675800)

    def test_market_player_outside_freeze_blocks(self):
        m = market_response(); m["best_prices"][0]["player_id"] = "CCC"
        with self.assertRaises(RuntimeError):
            normalize_v511_inputs(freeze_response(), m, now_epoch=1789675800)


if __name__ == "__main__":
    unittest.main(verbosity=2)
