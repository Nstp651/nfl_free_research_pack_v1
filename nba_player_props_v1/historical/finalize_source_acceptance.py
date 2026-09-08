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
    "FINAL_BOX_INTERNAL_ACCOUNTING_MISMATCH_REBUILD_REQUIRED",
}


def _need(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def _unit_games(rows: list[dict]) -> list[str]:
    return sorted({str(row["game_id_espn"]) for row in rows})


def finalize_source_acceptance(
    candidate: dict,
    adjudication: dict,
    history_quarantine: dict | None = None,
) -> dict:
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
    rebuild_required_units = adjudication.get("rebuild_required_units") or []
    rebuild_games = _unit_games(rebuild_required_units)
    accepted_history_sha256 = candidate.get("history_sha256")
    quarantine_receipt_sha256 = None

    if rebuild_games:
        if history_quarantine is None:
            status = "REBUILD_REQUIRED"
            reason = "FINAL_BOX_REQUIRES_FULL_GAME_HISTORY_QUARANTINE"
        else:
            _need(history_quarantine.get("market_data") is False, "history quarantine must be market blind")
            _need(
                history_quarantine.get("source_history_sha256") == candidate.get("history_sha256"),
                "history quarantine source hash mismatch",
            )
            _need(
                history_quarantine.get("adjudication_receipt_sha256") == adjudication.get("receipt_sha256"),
                "history quarantine adjudication receipt mismatch",
            )
            _need(
                sorted(map(str, history_quarantine.get("quarantined_game_ids") or [])) == rebuild_games,
                "history quarantine does not exactly cover rebuild-required games",
            )
            accepted_history_sha256 = history_quarantine.get("accepted_history_sha256")
            _need(
                isinstance(accepted_history_sha256, str) and len(accepted_history_sha256) == 64,
                "accepted history hash missing",
            )
            quarantine_receipt_sha256 = history_quarantine.get("receipt_sha256")
            status = "PASS"
            reason = "FINAL_BOX_REBUILD_GAMES_QUARANTINED_AND_ACCEPTED_HISTORY_LOCKED"
    else:
        status = "PASS"
        reason = "PLAYER_RELEASE_CONFIRMED_FOR_ALL_RECONCILIATION_MISMATCHES"

    report = {
        "schema_version": "nba_source_acceptance_final_v2",
        "market_data": False,
        "status": status,
        "reason": reason,
        "canonical_runtime_identity": "ESPN_ID",
        "official_nba_id_crosswalk": candidate.get("official_nba_id_crosswalk"),
        "source_history_sha256": candidate.get("history_sha256"),
        "history_sha256": accepted_history_sha256,
        "candidate_receipt_sha256": candidate.get("receipt_sha256"),
        "historical_receipt_sha256": candidate.get("historical_receipt_sha256"),
        "adjudication_receipt_sha256": adjudication.get("receipt_sha256"),
        "history_quarantine_receipt_sha256": quarantine_receipt_sha256,
        "runtime_fixture_source": copy.deepcopy(candidate.get("runtime_fixture_source")),
        "training_quarantine_audit": copy.deepcopy(candidate.get("training_quarantine_audit")),
        "identity_and_schedule_pass": True,
        "specialist_metrics_required_for_base_v1": False,
        "adjudicated_mismatch_game_team_units": int(adjudication.get("mismatch_game_team_units", 0)),
        "adjudicated_fields": adjudicated_fields,
        "player_release_confirmed_fields": player_confirmed_fields,
        "stale_player_release_units": copy.deepcopy(stale_player_units),
        "stale_team_release_units": copy.deepcopy(adjudication.get("stale_team_release_units") or []),
        "rebuild_required_units": copy.deepcopy(rebuild_required_units),
        "rebuild_required_game_ids": rebuild_games,
        "acceptance_rule": (
            "PLAYER PROP HISTORY IS ACCEPTED ONLY WHEN EVERY RELEASE MISMATCH IS "
            "ADJUDICATED AGAINST THE FINAL PER-GAME PLAYER AND TEAM BOX. TEAM-ONLY "
            "REBOUNDS ARE NOT PLAYER REBOUND ERRORS. ANY STALE PLAYER RELEASE OR "
            "INTERNALLY INCONSISTENT FINAL BOX REQUIRES DETERMINISTIC FULL-GAME "
            "QUARANTINE BEFORE THE ACCEPTED HISTORY HASH CAN PASS."
        ),
    }
    report["receipt_sha256"] = sha256_bytes(canonical_json(report))
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--adjudication", required=True)
    parser.add_argument("--history-quarantine-receipt")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    candidate = json.loads(Path(args.candidate).read_text())
    adjudication = json.loads(Path(args.adjudication).read_text())
    quarantine = (
        json.loads(Path(args.history_quarantine_receipt).read_text())
        if args.history_quarantine_receipt
        else None
    )
    report = finalize_source_acceptance(candidate, adjudication, quarantine)
    Path(args.output).write_bytes(canonical_json(report) + b"\n")
    print(
        json.dumps(
            {
                "status": report["status"],
                "reason": report["reason"],
                "rebuild_required_game_ids": report["rebuild_required_game_ids"],
                "history_sha256": report["history_sha256"],
                "receipt_sha256": report["receipt_sha256"],
            }
        )
    )


if __name__ == "__main__":
    main()
