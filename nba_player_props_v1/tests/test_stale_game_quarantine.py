import json
from pathlib import Path

import pandas as pd

from nba_player_props_v1.historical.apply_stale_game_quarantine import apply_quarantine


def test_stale_unit_removes_entire_game(tmp_path: Path):
    history = pd.DataFrame([
        {"game_id_espn": "1", "player_id_espn": "a", "team_id_espn": "4", "opponent_team_id_espn": "8", "game_start_utc": "2026-01-01T00:00:00Z"},
        {"game_id_espn": "1", "player_id_espn": "b", "team_id_espn": "8", "opponent_team_id_espn": "4", "game_start_utc": "2026-01-01T00:00:00Z"},
        {"game_id_espn": "2", "player_id_espn": "c", "team_id_espn": "4", "opponent_team_id_espn": "8", "game_start_utc": "2026-01-02T00:00:00Z"},
        {"game_id_espn": "2", "player_id_espn": "d", "team_id_espn": "8", "opponent_team_id_espn": "4", "game_start_utc": "2026-01-02T00:00:00Z"},
    ])
    history_path = tmp_path / "history.csv"
    adjudication_path = tmp_path / "adjudication.json"
    output = tmp_path / "accepted.csv"
    receipt = tmp_path / "receipt.json"
    history.to_csv(history_path, index=False)
    adjudication_path.write_text(json.dumps({
        "receipt_sha256": "a" * 64,
        "stale_player_release_units": [{"game_id_espn": "1", "team_id_espn": "4"}],
    }))
    result = apply_quarantine(str(history_path), str(adjudication_path), str(output), str(receipt))
    accepted = pd.read_csv(output, dtype={"game_id_espn": str})
    assert set(accepted.game_id_espn) == {"2"}
    assert result["rows_removed"] == 2
    assert result["games_removed"] == 1
