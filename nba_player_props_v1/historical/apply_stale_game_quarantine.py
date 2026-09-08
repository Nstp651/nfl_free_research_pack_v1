from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from nba_player_props_v1.source_receipt import canonical_json, sha256_bytes, sha256_file


def apply_quarantine(history_path: str, adjudication_path: str, output_path: str, receipt_path: str) -> dict:
    history = pd.read_csv(
        history_path,
        dtype={
            "game_id_espn": str,
            "player_id_espn": str,
            "team_id_espn": str,
            "opponent_team_id_espn": str,
        },
    )
    adjudication = json.loads(Path(adjudication_path).read_text())
    rebuild_units = adjudication.get("rebuild_required_units") or adjudication.get("stale_player_release_units") or []
    game_ids = sorted({str(row["game_id_espn"]) for row in rebuild_units})
    if not game_ids:
        raise ValueError("no rebuild-required games to quarantine")

    before_rows = len(history)
    before_games = history.game_id_espn.nunique()
    removed = history[history.game_id_espn.isin(game_ids)].copy()
    accepted = history[~history.game_id_espn.isin(game_ids)].copy()
    if removed.empty:
        raise ValueError("adjudicated rebuild-required games were absent from history")
    if set(removed.game_id_espn.astype(str)) != set(game_ids):
        raise ValueError("not every rebuild-required game was present in history")

    # Remove full games, never one team only: this preserves opponent/team temporal symmetry.
    for game_id, group in removed.groupby("game_id_espn"):
        if group.team_id_espn.nunique() != 2:
            raise ValueError(f"quarantined game {game_id} does not contain two teams")
        if set(group.team_id_espn.astype(str)) != set(group.opponent_team_id_espn.astype(str)):
            raise ValueError(f"quarantined game {game_id} opponent identity mismatch")
    if accepted.duplicated(["game_id_espn", "player_id_espn"]).any():
        raise ValueError("accepted history contains duplicate player-games")

    accepted = accepted.sort_values(
        ["game_start_utc", "game_id_espn", "team_id_espn", "player_id_espn"]
    ).reset_index(drop=True)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    accepted.to_csv(output_path, index=False, lineterminator="\n", float_format="%.12g")
    receipt = {
        "schema_version": "nba_source_rebuild_game_quarantine_v2",
        "market_data": False,
        "source_history_sha256": sha256_file(history_path),
        "adjudication_receipt_sha256": adjudication.get("receipt_sha256"),
        "quarantine_rule": "REMOVE_ENTIRE_GAME_FOR_ANY_FINAL_BOX_REBUILD_REQUIRED_UNIT",
        "rebuild_required_units": rebuild_units,
        "stale_player_release_units": adjudication.get("stale_player_release_units") or [],
        "quarantined_game_ids": game_ids,
        "rows_before": before_rows,
        "rows_removed": len(removed),
        "rows_after": len(accepted),
        "games_before": int(before_games),
        "games_removed": len(game_ids),
        "games_after": int(accepted.game_id_espn.nunique()),
        "accepted_history_sha256": sha256_file(output_path),
    }
    receipt["receipt_sha256"] = sha256_bytes(canonical_json(receipt))
    Path(receipt_path).write_bytes(canonical_json(receipt) + b"\n")
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--history", required=True)
    parser.add_argument("--adjudication", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--receipt", required=True)
    args = parser.parse_args()
    receipt = apply_quarantine(args.history, args.adjudication, args.output, args.receipt)
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
