from __future__ import annotations

import numpy as np
import pandas as pd

SHARED_FEATURES = (
    "season_games_before",
    "team_games_before",
    "team_rest_days",
    "player_days_since_last_game",
    "team_changed_since_last_game",
    "starter_prev",
    "start_rate_l5",
    "start_rate_l10",
    "minutes_l3",
    "minutes_l5",
    "minutes_l10",
    "minutes_l20",
    "team_possessions_l5",
    "team_possessions_l10",
)

ASSISTS_FEATURES = SHARED_FEATURES + (
    "assists_l3",
    "assists_l5",
    "assists_l10",
    "assists_l20",
    "assists_per_min_l5",
    "assists_per_min_l10",
    "assist_share_l5",
    "assist_share_l10",
    "turnovers_l5",
    "fga_l5",
    "team_assists_l5",
    "team_assists_l10",
    "opponent_assists_allowed_l5",
    "opponent_assists_allowed_l10",
)

REBOUNDS_FEATURES = SHARED_FEATURES + (
    "rebounds_l3",
    "rebounds_l5",
    "rebounds_l10",
    "rebounds_l20",
    "offensive_rebounds_l5",
    "defensive_rebounds_l5",
    "rebounds_per_min_l5",
    "rebounds_per_min_l10",
    "rebound_share_l5",
    "rebound_share_l10",
    "team_rebounds_l5",
    "team_rebounds_l10",
    "opponent_rebounds_allowed_l5",
    "opponent_rebounds_allowed_l10",
)


def _shift_roll(frame: pd.DataFrame, groups: list[str], column: str, window: int) -> pd.Series:
    return frame.groupby(groups, sort=False, dropna=False)[column].transform(
        lambda s: s.shift(1).rolling(window=window, min_periods=1).mean()
    )


def _safe_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    denom = denominator.replace(0, np.nan)
    return numerator / denom


def _team_games(player_games: pd.DataFrame) -> pd.DataFrame:
    keys = ["season", "season_type", "game_id_espn", "game_start_utc", "team_id_espn", "opponent_team_id_espn"]
    numeric = {
        "field_goals_made": "sum",
        "field_goals_attempted": "sum",
        "free_throws_attempted": "sum",
        "offensive_rebounds": "sum",
        "defensive_rebounds": "sum",
        "rebounds": "sum",
        "assists": "sum",
        "turnovers": "sum",
    }
    team = player_games.groupby(keys, as_index=False, sort=False).agg(numeric)
    team = team.rename(columns={
        "field_goals_made": "team_fgm",
        "field_goals_attempted": "team_fga",
        "free_throws_attempted": "team_fta",
        "offensive_rebounds": "team_orb",
        "defensive_rebounds": "team_drb",
        "rebounds": "team_rebounds",
        "assists": "team_assists",
        "turnovers": "team_turnovers",
    })
    team["team_possessions_est"] = team["team_fga"] + 0.44 * team["team_fta"] - team["team_orb"] + team["team_turnovers"]

    opp = team[["game_id_espn", "team_id_espn", "team_rebounds", "team_assists", "team_possessions_est"]].rename(columns={
        "team_id_espn": "opponent_team_id_espn",
        "team_rebounds": "opponent_rebounds_current",
        "team_assists": "opponent_assists_current",
        "team_possessions_est": "opponent_possessions_current",
    })
    team = team.merge(opp, on=["game_id_espn", "opponent_team_id_espn"], how="left", validate="one_to_one")
    if team[["opponent_rebounds_current", "opponent_assists_current"]].isna().any().any():
        raise ValueError("opponent team-game join failed")

    team["game_possessions_est"] = (team["team_possessions_est"] + team["opponent_possessions_current"]) / 2.0
    team["assists_allowed_current"] = team["opponent_assists_current"]
    team["rebounds_allowed_current"] = team["opponent_rebounds_current"]
    team = team.sort_values(["team_id_espn", "game_start_utc", "game_id_espn"]).reset_index(drop=True)
    team["team_games_before"] = team.groupby(["season", "team_id_espn"], sort=False).cumcount()
    previous = team.groupby("team_id_espn", sort=False)["game_start_utc"].shift(1)
    team["team_rest_days"] = (team["game_start_utc"] - previous).dt.total_seconds() / 86400.0
    team["team_rest_days"] = (team["team_rest_days"] - 1.0).clip(lower=0, upper=14)

    for window in (5, 10):
        team[f"team_possessions_l{window}"] = _shift_roll(team, ["team_id_espn"], "game_possessions_est", window)
        team[f"team_assists_l{window}"] = _shift_roll(team, ["team_id_espn"], "team_assists", window)
        team[f"team_rebounds_l{window}"] = _shift_roll(team, ["team_id_espn"], "team_rebounds", window)
        team[f"assists_allowed_l{window}"] = _shift_roll(team, ["team_id_espn"], "assists_allowed_current", window)
        team[f"rebounds_allowed_l{window}"] = _shift_roll(team, ["team_id_espn"], "rebounds_allowed_current", window)
    return team


def build_pregame_features(player_games: pd.DataFrame) -> pd.DataFrame:
    required = {
        "season", "season_type", "game_id_espn", "game_start_utc", "player_id_espn", "team_id_espn", "opponent_team_id_espn",
        "starter", "minutes", "assists", "rebounds", "offensive_rebounds", "defensive_rebounds", "turnovers",
        "field_goals_made", "field_goals_attempted", "free_throws_attempted",
    }
    missing = sorted(required.difference(player_games.columns))
    if missing:
        raise ValueError(f"missing normalized columns: {missing}")
    if player_games.empty:
        raise ValueError("player_games is empty")
    if player_games.duplicated(["game_id_espn", "player_id_espn"]).any():
        raise ValueError("duplicate player-game rows")

    data = player_games.copy()
    data["game_start_utc"] = pd.to_datetime(data["game_start_utc"], utc=True, errors="raise")
    data = data.sort_values(["player_id_espn", "game_start_utc", "game_id_espn"]).reset_index(drop=True)

    team = _team_games(data)
    team_current = team[[
        "game_id_espn", "team_id_espn", "team_assists", "team_rebounds",
        "team_games_before", "team_rest_days", "team_possessions_l5", "team_possessions_l10",
        "team_assists_l5", "team_assists_l10", "team_rebounds_l5", "team_rebounds_l10",
    ]]
    data = data.merge(team_current, on=["game_id_espn", "team_id_espn"], how="left", validate="many_to_one")

    opp_context = team[[
        "game_id_espn", "team_id_espn", "assists_allowed_l5", "assists_allowed_l10", "rebounds_allowed_l5", "rebounds_allowed_l10",
    ]].rename(columns={
        "team_id_espn": "opponent_team_id_espn",
        "assists_allowed_l5": "opponent_assists_allowed_l5",
        "assists_allowed_l10": "opponent_assists_allowed_l10",
        "rebounds_allowed_l5": "opponent_rebounds_allowed_l5",
        "rebounds_allowed_l10": "opponent_rebounds_allowed_l10",
    })
    data = data.merge(opp_context, on=["game_id_espn", "opponent_team_id_espn"], how="left", validate="many_to_one")

    data = data.sort_values(["player_id_espn", "game_start_utc", "game_id_espn"]).reset_index(drop=True)
    data["season_games_before"] = data.groupby(["season", "player_id_espn"], sort=False).cumcount()
    prev_start = data.groupby("player_id_espn", sort=False)["game_start_utc"].shift(1)
    data["player_days_since_last_game"] = ((data["game_start_utc"] - prev_start).dt.total_seconds() / 86400.0).clip(upper=60)
    previous_team = data.groupby("player_id_espn", sort=False)["team_id_espn"].shift(1)
    data["team_changed_since_last_game"] = ((previous_team.notna()) & (previous_team != data["team_id_espn"])).astype(int)
    data["starter_num"] = data["starter"].astype(int)
    data["starter_prev"] = data.groupby("player_id_espn", sort=False)["starter_num"].shift(1)

    data["assists_per_min_current"] = _safe_ratio(data["assists"], data["minutes"])
    data["rebounds_per_min_current"] = _safe_ratio(data["rebounds"], data["minutes"])
    data["assist_share_current"] = _safe_ratio(data["assists"], data["team_assists"])
    data["rebound_share_current"] = _safe_ratio(data["rebounds"], data["team_rebounds"])

    for window in (3, 5, 10, 20):
        data[f"minutes_l{window}"] = _shift_roll(data, ["player_id_espn"], "minutes", window)
        data[f"assists_l{window}"] = _shift_roll(data, ["player_id_espn"], "assists", window)
        data[f"rebounds_l{window}"] = _shift_roll(data, ["player_id_espn"], "rebounds", window)
    for window in (5, 10):
        data[f"start_rate_l{window}"] = _shift_roll(data, ["player_id_espn"], "starter_num", window)
        data[f"assists_per_min_l{window}"] = _shift_roll(data, ["player_id_espn"], "assists_per_min_current", window)
        data[f"rebounds_per_min_l{window}"] = _shift_roll(data, ["player_id_espn"], "rebounds_per_min_current", window)
        data[f"assist_share_l{window}"] = _shift_roll(data, ["player_id_espn"], "assist_share_current", window)
        data[f"rebound_share_l{window}"] = _shift_roll(data, ["player_id_espn"], "rebound_share_current", window)
    data["turnovers_l5"] = _shift_roll(data, ["player_id_espn"], "turnovers", 5)
    data["fga_l5"] = _shift_roll(data, ["player_id_espn"], "field_goals_attempted", 5)
    data["offensive_rebounds_l5"] = _shift_roll(data, ["player_id_espn"], "offensive_rebounds", 5)
    data["defensive_rebounds_l5"] = _shift_roll(data, ["player_id_espn"], "defensive_rebounds", 5)

    return data.sort_values(["game_start_utc", "game_id_espn", "team_id_espn", "player_id_espn"]).reset_index(drop=True)


def head_feature_columns(head: str) -> tuple[str, ...]:
    if head == "assists":
        return ASSISTS_FEATURES
    if head == "rebounds":
        return REBOUNDS_FEATURES
    raise ValueError("head must be assists or rebounds")
