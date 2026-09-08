from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from nba_player_props_v1.source_receipt import canonical_json, sha256_bytes

ALLOWED_PLAYER_CONFIRMED_DECISIONS = {
    "BOTH_RELEASES_CONFIRMED",
    "PLAYER_RELEASE_CONFIRMED_TEAM_RELEASE_STALE",
    "FINAL_PLAYER_AND_TEAM_RELEASES_CONFIRMED_TEAM_REBOUND_ACCOUNTING",
}


def _need(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def finalize_source_acceptance(candidate: dict, adjudication: dict) -> dict:
    _need(candidate.get("market_data") is False, "candidate must be market blind")
    _need(adjudication.get("market_data") is False, "adjudication must be market blind")
    _need(candidate.get("identity_and_schedule_pass") is True, "identity/schedule gate failed")
    _need(
        (candidate.get("runtime_fixture_source") or {}).get("status") == "PASS",
        "runtime fixture source gate failed",
    )
    _need(
        (candidate.get("training_quarantine_audit") or {}).get("status") == "PASS",
        "training quarantine audit failed",
    )
    _need(adjudication.get("status") == "PASS", "final box adjudication failed")
    _need(not adjudication.get("unresolved_units"), "unresolved final box units remain")

    adjudicated_fields = 0
    player_confirmed_fields = 0
    for unit in adjudication.get("adjudications") or []:
        fields = unit.get("fields") or {}
        _need(fields, "adjudication unit has no fields")
        for detail in fields.values():
            adjudicated_fields += 1
            decision = str(detail.get("decision") or "")
            if bool(detail.get("raw_player_release_confirmed")):
                player_confirmed_fields += 1
            if decision == "TEAM_RELEASE_CONFIRMED_PLAYER_RELEASE_STALE":
                continue
            _need(
                decision in ALLOWED_PLAYER_CONFIRMED_DECISIONS,
                f"unsupported adjudication decision {decision}",
            )
            _need(
                detail.get("raw_player_release_confirmed") is True,
                "accepted adjudication did not confirm player release",
            )

    stale_player_units = adjudication.get("stale_player_release_units") or []
    if stale_player_units:
        status = "REBUILD_REQUIRED"
        reason = "FINAL_BOX_CONFIRMED_STALE_PLAYER_RELEASE_UNITS"
    else:
        status = "PASS"
        reason = "PLAYER_RELEASE_CONFIRMED_FOR_ALL_RECONCILIATION_MISMATCHES"

    report = {
        "schema_version": "nba_source_acceptance_final_v1",
        "market_data": False,
        "status": status,
        "reason": reason,
        "canonical_runtime_identity": "ESPN_ID",
        "official_nba_id_crosswalk": candidate.get("official_nba_id_crosswalk"),
        "history_sha256": candidate.get("history_sha256"),
        "candidate_receipt_sha256": candidate.get("receipt_sha256"),
        "historical_receipt_sha256": candidate.get("historical_receipt_sha256"),
        "adjudication_receipt_sha256": adjudication.get("receipt_sha256"),
        "runtime_fixture_source": copy.deepcopy(candidate.get("runtime_fixture_source")),
        "training_quarantine_audit": copy.deepcopy(candidate.get("training_quarantine_audit")),
        "identity_and_schedule_pass": True,
        "specialist_metrics_required_for_base_v1": False,
        "adjudicated_mismatch_game_team_units": int(
            adjudication.get("mismatch_game_team_units", 0)
        ),
        "adjudicated_fields": adjudicated_fields,
        "player_release_confirmed_fields": player_confirmed_fields,
        "stale_player_release_units": copy.deepcopy(stale_player_units),
        "stale_team_release_units": copy.deepcopy(
            adjudication.get("stale_team_release_units") or []
        ),
        "acceptance_rule": (
            "PLAYER PROP HISTORY IS ACCEPTED ONLY WHEN EVERY RELEASE MISMATCH IS "
            "ADJUDICATED AGAINST THE FINAL PER-GAME PLAYER AND TEAM BOX. TEAM-ONLY "
            "REBOUNDS ARE NOT PLAYER REBOUND ERRORS. ANY FINAL-BOX-CONFIRMED STALE "
            "PLAYER RELEASE UNIT REQUIRES A DETERMINISTIC HISTORY REBUILD."
        ),
    }
    report["receipt_sha256"] = sha256_bytes(canonical_json(report))
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--adjudication", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    candidate = json.loads(Path(args.candidate).read_text())
    adjudication = json.loads(Path(args.adjudication).read_text())
    report = finalize_source_acceptance(candidate, adjudication)
    Path(args.output).write_bytes(canonical_json(report) + b"\n")
    print(
        json.dumps(
            {
                "status": report["status"],
                "reason": report["reason"],
                "stale_player_release_units": report["stale_player_release_units"],
                "receipt_sha256": report["receipt_sha256"],
            }
        )
    )


if __name__ == "__main__":
    main()
