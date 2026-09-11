from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from nba_player_props_v1.source_receipt import canonical_json, sha256_bytes


def _need(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def accept_quarantined_history(final_source: dict, adjudication: dict, quarantine: dict) -> dict:
    _need(final_source.get("market_data") is False, "final source state must be market blind")
    _need(adjudication.get("market_data") is False, "adjudication must be market blind")
    _need(quarantine.get("market_data") is False, "quarantine must be market blind")
    _need(final_source.get("status") == "REBUILD_REQUIRED", "source state is not rebuild-required")
    _need(adjudication.get("status") == "PASS", "adjudication not PASS")
    _need(not adjudication.get("unresolved_units"), "unresolved source units remain")

    required_games = sorted(str(x) for x in final_source.get("rebuild_required_game_ids") or [])
    quarantined_games = sorted(str(x) for x in quarantine.get("quarantined_game_ids") or [])
    _need(required_games, "no rebuild-required games")
    _need(required_games == quarantined_games, "quarantine game set differs from adjudicated rebuild set")
    _need(int(quarantine.get("games_removed", -1)) == len(required_games), "quarantine game count mismatch")
    _need(int(quarantine.get("rows_removed", 0)) > 0, "quarantine removed no rows")
    _need(int(quarantine.get("rows_after", 0)) < int(quarantine.get("rows_before", 0)), "quarantine did not reduce history")
    _need(quarantine.get("source_history_sha256") == final_source.get("history_sha256"), "quarantine source history hash mismatch")
    accepted_sha = str(quarantine.get("accepted_history_sha256") or "")
    _need(len(accepted_sha) == 64, "accepted history SHA missing")

    rule = (
        "THE ACCEPTED MODEL HISTORY IS THE DETERMINISTIC PRE-MARKET HISTORY AFTER REMOVING THE ENTIRE GAME "
        "FOR EVERY FINAL-BOX-ADJUDICATED INCONSISTENT UNIT. NO INDIVIDUAL STAT PATCHING, TEAM-ONLY REMOVAL, "
        "OR HOLDOUT-DRIVEN MODEL-FAMILY RESELECTION IS PERMITTED."
    )
    stable_core = {
        "schema_version": "nba_source_acceptance_quarantined_v1",
        "market_data": False,
        "status": "PASS",
        "reason": "ALL_ADJUDICATED_INCONSISTENT_GAMES_REMOVED_AS_COMPLETE_GAMES",
        "canonical_runtime_identity": final_source.get("canonical_runtime_identity", "ESPN_ID"),
        "pre_quarantine_history_sha256": final_source.get("history_sha256"),
        "history_sha256": accepted_sha,
        "rebuild_required_game_ids": required_games,
        "games_removed": len(required_games),
        "rows_removed": int(quarantine.get("rows_removed", 0)),
        "rows_after": int(quarantine.get("rows_after", 0)),
        "identity_and_schedule_pass": bool(final_source.get("identity_and_schedule_pass")),
        "runtime_fixture_source_status": (final_source.get("runtime_fixture_source") or {}).get("status"),
        "training_quarantine_status": (final_source.get("training_quarantine_audit") or {}).get("status"),
        "specialist_metrics_required_for_base_v1": False,
        "acceptance_rule": rule,
    }
    _need(stable_core["identity_and_schedule_pass"] is True, "identity/schedule gate failed")
    _need(stable_core["runtime_fixture_source_status"] == "PASS", "runtime fixture source gate failed")
    _need(stable_core["training_quarantine_status"] == "PASS", "training quarantine gate failed")

    report = {
        **stable_core,
        "accepted_history_sha256": accepted_sha,
        "official_nba_id_crosswalk": copy.deepcopy(final_source.get("official_nba_id_crosswalk")),
        "source_state_receipt_sha256": final_source.get("receipt_sha256"),
        "adjudication_receipt_sha256": adjudication.get("receipt_sha256"),
        "quarantine_receipt_sha256": quarantine.get("receipt_sha256"),
        "runtime_fixture_source": copy.deepcopy(final_source.get("runtime_fixture_source")),
        "training_quarantine_audit": copy.deepcopy(final_source.get("training_quarantine_audit")),
        "receipt_rule": "receipt_sha256 hashes stable_core only; volatile source check timestamps and transport receipts remain lineage metadata but cannot churn promoted runtime assets",
    }
    report["receipt_sha256"] = sha256_bytes(canonical_json(stable_core))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--final-source", required=True); parser.add_argument("--adjudication", required=True); parser.add_argument("--quarantine", required=True); parser.add_argument("--output", required=True); args = parser.parse_args()
    report = accept_quarantined_history(json.loads(Path(args.final_source).read_text()), json.loads(Path(args.adjudication).read_text()), json.loads(Path(args.quarantine).read_text()))
    Path(args.output).write_bytes(canonical_json(report) + b"\n")
    print(json.dumps({"status": report["status"], "history_sha256": report["history_sha256"], "games_removed": report["games_removed"], "rows_removed": report["rows_removed"], "receipt_sha256": report["receipt_sha256"]}))


if __name__ == "__main__": main()
