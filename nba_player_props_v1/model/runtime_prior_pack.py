from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from nba_player_props_v1.source_receipt import canonical_json, sha256_bytes, sha256_file


def _mean_tail(frame: pd.DataFrame, col: str, n: int) -> float | None:
    values = pd.to_numeric(frame[col], errors="coerce").dropna().tail(n)
    return None if values.empty else float(values.mean())


def _safe_ratio(a: pd.Series, b: pd.Series) -> pd.Series:
    return pd.to_numeric(a, errors="coerce") / pd.to_numeric(b, errors="coerce").replace(0, np.nan)


def _season_counts(frame: pd.DataFrame) -> dict[str, int]:
    return {str(int(k)): int(v) for k, v in frame.groupby("season").size().items()}


def build_runtime_prior_pack(history: pd.DataFrame, *, history_sha256: str) -> dict:
    required = {
        "season", "game_id_espn", "game_start_utc", "player_id_espn", "team_id_espn",
        "opponent_team_id_espn", "starter", "minutes", "assists", "rebounds",
        "offensive_rebounds", "defensive_rebounds", "turnovers", "field_goals_attempted",
        "field_goals_made", "free_throws_attempted",
    }
    missing = sorted(required.difference(history.columns))
    if missing:
        raise ValueError(f"missing runtime prior columns: {missing}")
    data = history.copy()
    data["game_start_utc"] = pd.to_datetime(data["game_start_utc"], utc=True, errors="raise")
    data = data.sort_values(["game_start_utc", "game_id_espn", "team_id_espn", "player_id_espn"]).reset_index(drop=True)
    if data.duplicated(["game_id_espn", "player_id_espn"]).any():
        raise ValueError("duplicate player-games")

    team_keys = ["season", "game_id_espn", "game_start_utc", "team_id_espn", "opponent_team_id_espn"]
    team = data.groupby(team_keys, as_index=False).agg(
        team_fga=("field_goals_attempted", "sum"),
        team_fta=("free_throws_attempted", "sum"),
        team_orb=("offensive_rebounds", "sum"),
        team_rebounds=("rebounds", "sum"),
        team_assists=("assists", "sum"),
        team_turnovers=("turnovers", "sum"),
    )
    team["team_possessions_est"] = team.team_fga + 0.44 * team.team_fta - team.team_orb + team.team_turnovers
    opp = team[["game_id_espn", "team_id_espn", "team_rebounds", "team_assists", "team_possessions_est"]].rename(columns={
        "team_id_espn": "opponent_team_id_espn",
        "team_rebounds": "opponent_rebounds_current",
        "team_assists": "opponent_assists_current",
        "team_possessions_est": "opponent_possessions_current",
    })
    team = team.merge(opp, on=["game_id_espn", "opponent_team_id_espn"], how="left", validate="one_to_one")
    if team[["opponent_rebounds_current", "opponent_assists_current", "opponent_possessions_current"]].isna().any().any():
        raise ValueError("runtime prior opponent join failed")
    team["game_possessions_est"] = (team.team_possessions_est + team.opponent_possessions_current) / 2.0
    team = team.sort_values(["team_id_espn", "game_start_utc", "game_id_espn"])

    team_totals = team[["game_id_espn", "team_id_espn", "team_assists", "team_rebounds"]]
    data = data.merge(team_totals, on=["game_id_espn", "team_id_espn"], how="left", validate="many_to_one")
    data["assist_share_current"] = _safe_ratio(data.assists, data.team_assists)
    data["rebound_share_current"] = _safe_ratio(data.rebounds, data.team_rebounds)
    data["assists_per_min_current"] = _safe_ratio(data.assists, data.minutes)
    data["rebounds_per_min_current"] = _safe_ratio(data.rebounds, data.minutes)

    players = {}
    for player_id, rows in data.groupby("player_id_espn", sort=True):
        rows = rows.sort_values(["game_start_utc", "game_id_espn"])
        last = rows.iloc[-1]
        features = {
            "starter_prev": float(bool(last.starter)), "start_rate_l5": _mean_tail(rows, "starter", 5), "start_rate_l10": _mean_tail(rows, "starter", 10),
            "minutes_l3": _mean_tail(rows, "minutes", 3), "minutes_l5": _mean_tail(rows, "minutes", 5), "minutes_l10": _mean_tail(rows, "minutes", 10), "minutes_l20": _mean_tail(rows, "minutes", 20),
            "assists_l3": _mean_tail(rows, "assists", 3), "assists_l5": _mean_tail(rows, "assists", 5), "assists_l10": _mean_tail(rows, "assists", 10), "assists_l20": _mean_tail(rows, "assists", 20),
            "assists_per_min_l5": _mean_tail(rows, "assists_per_min_current", 5), "assists_per_min_l10": _mean_tail(rows, "assists_per_min_current", 10),
            "assist_share_l5": _mean_tail(rows, "assist_share_current", 5), "assist_share_l10": _mean_tail(rows, "assist_share_current", 10),
            "turnovers_l5": _mean_tail(rows, "turnovers", 5), "fga_l5": _mean_tail(rows, "field_goals_attempted", 5),
            "rebounds_l3": _mean_tail(rows, "rebounds", 3), "rebounds_l5": _mean_tail(rows, "rebounds", 5), "rebounds_l10": _mean_tail(rows, "rebounds", 10), "rebounds_l20": _mean_tail(rows, "rebounds", 20),
            "offensive_rebounds_l5": _mean_tail(rows, "offensive_rebounds", 5), "defensive_rebounds_l5": _mean_tail(rows, "defensive_rebounds", 5),
            "rebounds_per_min_l5": _mean_tail(rows, "rebounds_per_min_current", 5), "rebounds_per_min_l10": _mean_tail(rows, "rebounds_per_min_current", 10),
            "rebound_share_l5": _mean_tail(rows, "rebound_share_current", 5), "rebound_share_l10": _mean_tail(rows, "rebound_share_current", 10),
        }
        players[str(player_id)] = {
            "player_id": str(player_id), "last_team_id": str(last.team_id_espn), "last_opponent_team_id": str(last.opponent_team_id_espn),
            "last_game_start_utc": last.game_start_utc.isoformat(), "last_season": int(last.season), "career_games": int(len(rows)),
            "games_by_season": _season_counts(rows), "features": features,
        }

    teams = {}
    for team_id, rows in team.groupby("team_id_espn", sort=True):
        rows = rows.sort_values(["game_start_utc", "game_id_espn"])
        last = rows.iloc[-1]
        teams[str(team_id)] = {
            "team_id": str(team_id), "last_game_start_utc": last.game_start_utc.isoformat(), "last_season": int(last.season),
            "games_by_season": _season_counts(rows),
            "features": {
                "team_possessions_l5": _mean_tail(rows, "game_possessions_est", 5), "team_possessions_l10": _mean_tail(rows, "game_possessions_est", 10),
                "team_assists_l5": _mean_tail(rows, "team_assists", 5), "team_assists_l10": _mean_tail(rows, "team_assists", 10),
                "team_rebounds_l5": _mean_tail(rows, "team_rebounds", 5), "team_rebounds_l10": _mean_tail(rows, "team_rebounds", 10),
                "assists_allowed_l5": _mean_tail(rows, "opponent_assists_current", 5), "assists_allowed_l10": _mean_tail(rows, "opponent_assists_current", 10),
                "rebounds_allowed_l5": _mean_tail(rows, "opponent_rebounds_current", 5), "rebounds_allowed_l10": _mean_tail(rows, "opponent_rebounds_current", 10),
            },
        }

    pack = {
        "schema_version": "nba_runtime_prior_pack_v1", "market_data": False, "history_sha256": history_sha256,
        "max_history_season": int(data.season.max()), "player_count": len(players), "team_count": len(teams), "players": players, "teams": teams,
        "feature_semantics": "END_OF_ACCEPTED_HISTORY_ROLLING_PRIORS_MATCHING_QBASE_TRAINING_FEATURE_DEFINITIONS",
    }
    pack["pack_sha256"] = sha256_bytes(canonical_json(pack))
    return pack


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--history", required=True); parser.add_argument("--output", required=True); args = parser.parse_args()
    history = pd.read_csv(args.history, dtype={"game_id_espn": str, "player_id_espn": str, "team_id_espn": str, "opponent_team_id_espn": str})
    pack = build_runtime_prior_pack(history, history_sha256=sha256_file(args.history)); Path(args.output).parent.mkdir(parents=True, exist_ok=True); Path(args.output).write_bytes(canonical_json(pack) + b"\n")
    print(json.dumps({"player_count": pack["player_count"], "team_count": pack["team_count"], "history_sha256": pack["history_sha256"], "pack_sha256": pack["pack_sha256"]}))


if __name__ == "__main__": main()
