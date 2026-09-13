from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "model"))

from market_ranking import classify_market_threshold, validate_threshold_policy  # noqa: E402
from tail_policy import canonical_sha256  # noqa: E402


def load_artifact(head: str) -> dict:
    return json.loads((ROOT / f"data/model/qbase_{head}_v0.1.0.json").read_text())


def test_shipped_tail_policies_match_evidence_derived_ranges():
    assists = load_artifact("assists")["probability_contract"]
    rebounds = load_artifact("rebounds")["probability_contract"]
    assert validate_threshold_policy(assists["threshold_validation_policy"], assists["max_count"])["direct_validated_thresholds"] == list(range(2, 10))
    assert assists["threshold_validation_policy"]["tail_supported_thresholds"] == [1]
    assert assists["threshold_validation_policy"]["extreme_tail_thresholds"][0] == 10
    assert validate_threshold_policy(rebounds["threshold_validation_policy"], rebounds["max_count"])["direct_validated_thresholds"] == list(range(3, 13))
    assert rebounds["threshold_validation_policy"]["tail_supported_thresholds"] == [1, 2, 13]
    assert rebounds["threshold_validation_policy"]["extreme_tail_thresholds"][0] == 14


def test_integer_line_uses_both_tail_boundaries_and_fails_to_worse_state():
    policy = load_artifact("assists")["probability_contract"]["threshold_validation_policy"]
    head = {"qbase_anchor": {"max_count": 20, "threshold_validation_policy": policy}}
    assert classify_market_threshold(head, 8.5)["threshold_validation"] == "DIRECT_VALIDATED"
    assert classify_market_threshold(head, 9.0)["validation_event_thresholds"] == [9, 10]
    assert classify_market_threshold(head, 9.0)["threshold_validation"] == "EXTREME_TAIL"


def test_legacy_frozen_qbase_receipt_resolves_committed_policy():
    head = {"qbase_anchor": {
        "qbase_sha256": "8e714c693f0a1eddfd3989c6717f120079ec3fa0e1c42e1eaf5c1d670d265eab",
        "max_count": 20,
    }}
    direct = classify_market_threshold(head, 8.5)
    extreme = classify_market_threshold(head, 11.5)
    assert direct["threshold_validation"] == "DIRECT_VALIDATED"
    assert direct["threshold_validation_evidence_sha256"] == "a77126faacc0304962060b76caae79a358de2723d10210c2be3ff67adcd0d446"
    assert extreme["threshold_validation"] == "EXTREME_TAIL"
    assert extreme["threshold_best_single_supported"] is False


def test_committed_tail_evidence_receipts_are_self_verifying():
    evidence = json.loads((ROOT / "evidence/qbase_tail_validation_v0.1.0.json").read_text())
    for head in evidence["heads"].values():
        claimed = head["evidence_sha256"]
        payload = copy.deepcopy(head)
        del payload["evidence_sha256"]
        del payload["policy"]["evidence_sha256"]
        assert canonical_sha256(payload) == claimed
