import copy
import random

import pytest

from freeze_identity import (
    build_keyed_anchor_receipts,
    grid_sha256,
    qbase_anchor_sha256,
    validate_frozen_identity,
)


def grid(mu):
    return [
        {"line": 50.0, "over": .45, "push": .03, "under": .52},
        {"line": 50.5, "over": .45, "push": 0.0, "under": .55},
    ]


def research(gid, away, home):
    return {"game_id": gid, "fixture": {"away_team": away, "home_team": home}}


def qbase(gid, away, home, mu):
    g = {
        "game_id": gid,
        "away_team": away,
        "home_team": home,
        "expected_total_qbase": mu,
        "residual_bucket": "W0_1",
        "residual_sd": 13.7,
        "probability_grid": grid(mu),
    }
    g["qbase_anchor_sha256"] = qbase_anchor_sha256(g)
    return g


def frozen_from(q):
    return {
        "game_id": q["game_id"],
        "away_team": q["away_team"],
        "home_team": q["home_team"],
        "expected_total_qbase": q["expected_total_qbase"],
        "contextual_shift": 0.0,
        "expected_total_final": q["expected_total_qbase"],
        "distribution_changed": False,
        "qbase_anchor_sha256": q["qbase_anchor_sha256"],
        "qbase_probability_grid_sha256": grid_sha256(q["probability_grid"]),
        "probability_grid": copy.deepcopy(q["probability_grid"]),
    }


def base_data():
    r = [research("1", "A", "B"), research("2", "C", "D"), research("3", "E", "F")]
    q = [qbase("1", "A", "B", 41.1), qbase("2", "C", "D", 52.2), qbase("3", "E", "F", 63.3)]
    return r, q


def test_subset_filtering_cannot_create_positional_mismatch():
    r, q = base_data()
    receipts = build_keyed_anchor_receipts(r, q, ["3", "1"])
    assert [(x["game_id"], x["expected_total_qbase"]) for x in receipts] == [("3", 63.3), ("1", 41.1)]


def test_shuffled_qbase_order_maps_by_game_id():
    r, q = base_data()
    random.Random(7).shuffle(q)
    receipts = build_keyed_anchor_receipts(r, q, ["1", "2", "3"])
    assert [x["expected_total_qbase"] for x in receipts] == [41.1, 52.2, 63.3]


def test_duplicate_game_id_fails():
    r, q = base_data()
    with pytest.raises(ValueError, match="duplicate game_id"):
        build_keyed_anchor_receipts(r, q + [copy.deepcopy(q[0])], ["1"])


def test_missing_game_id_fails():
    r, q = base_data()
    with pytest.raises(ValueError, match="missing from QBASE"):
        build_keyed_anchor_receipts(r, q[:2], ["3"])


def test_team_identity_mismatch_fails():
    r, q = base_data()
    q[0]["home_team"] = "Wrong"
    q[0]["qbase_anchor_sha256"] = qbase_anchor_sha256(q[0])
    with pytest.raises(ValueError, match="team identity mismatch"):
        build_keyed_anchor_receipts(r, q, ["1"])


def test_zero_shift_anchor_mismatch_fails():
    r, q = base_data()
    f = [frozen_from(q[0])]
    f[0]["expected_total_final"] += 4.0
    with pytest.raises(ValueError, match="zero-shift anchor breach"):
        validate_frozen_identity(r, q, f)


def test_zero_shift_grid_hash_mismatch_fails():
    r, q = base_data()
    f = [frozen_from(q[0])]
    f[0]["probability_grid"][0]["over"] = .44
    f[0]["probability_grid"][0]["under"] = .53
    with pytest.raises(ValueError, match="zero-shift probability-grid breach"):
        validate_frozen_identity(r, q, f)


def test_valid_zero_shift_freeze_passes_with_identity_receipt():
    r, q = base_data()
    f = [frozen_from(q[2]), frozen_from(q[0])]
    receipt = validate_frozen_identity(r, list(reversed(q)), f)
    assert receipt["status"] == "PASS"
    assert receipt["game_count"] == 2
    assert len(receipt["identity_receipt_sha256"]) == 64
