#!/usr/bin/env python3
"""Leak-safe shared pregame features for NBL assists and rebounds heads.

All player/team/opponent rolling statistics are shifted one completed game before
exposure to a target row. Target-game assists, rebounds, minutes, shots and team
box-score environment can become history only for future predictions.
"""
from __future__ import annotations

import math
import numpy as np
import pandas as pd

COMMON_FEATURES = [
    "player_games_prior", "player_season_games_prior",
    "player_minutes_mean_3", "player_minutes_mean_5", "player_minutes_mean_10",
    "player_minutes_sd_5", "player_minutes_sd_10",
    "player_start_rate_5", "player_start_rate_10", "player_days_rest",
    "team_games_prior", "team_season_games_prior", "team_days_rest", "opponent_days_rest",
    "team_points_mean_5", "team_points_mean_10",
    "opponent_points_allowed_mean_5", "opponent_points_allowed_mean_10",
    "team_possessions_mean_5", "team_possessions_mean_10",
    "opponent_possessions_mean_5", "opponent_possessions_mean_10",
    "home_flag",
]
HEAD_FEATURES = {
    "assists": COMMON_FEATURES + [
        "player_assists_mean_3", "player_assists_mean_5", "player_assists_mean_10",
        "player_assists_per_min_mean_5", "player_assists_per_min_mean_10",
        "player_turnovers_mean_5", "player_turnovers_mean_10",
        "player_fga_mean_5", "player_fga_mean_10",
        "team_assists_mean_5", "team_assists_mean_10",
        "team_fgm_mean_5", "team_fgm_mean_10",
        "opponent_assists_allowed_mean_5", "opponent_assists_allowed_mean_10",
        "opponent_fgm_allowed_mean_5", "opponent_fgm_allowed_mean_10",
    ],
    "rebounds": COMMON_FEATURES + [
        "player_rebounds_mean_3", "player_rebounds_mean_5", "player_rebounds_mean_10",
        "player_rebounds_per_min_mean_5", "player_rebounds_per_min_mean_10",
        "player_orb_mean_5", "player_orb_mean_10", "player_drb_mean_5", "player_drb_mean_10",
        "team_rebounds_mean_5", "team_rebounds_mean_10",
        "team_missed_fg_mean_5", "team_missed_fg_mean_10",
        "opponent_missed_fg_mean_5", "opponent_missed_fg_mean_10",
        "opponent_rebounds_allowed_mean_5", "opponent_rebounds_allowed_mean_10",
    ],
}

PLAYER_OPTIONAL_NUMERIC = [
    "points", "rebounds_offensive", "rebounds_defensive", "turnovers",
    "field_goals_attempted", "field_goals_made", "three_pointers_attempted",
]
TEAM_ENV_NUMERIC = [
    "team_points_box", "team_assists_box", "team_rebounds_box", "team_fgm", "team_fga",
    "team_missed_fg", "team_possessions_est", "opp_points_box", "opp_assists_box",
    "opp_rebounds_box", "opp_fgm", "opp_fga", "opp_missed_fg", "opp_possessions_est",
    "game_possessions_est",
]


def _starter_bool(value: object) -> float:
    s = str(value or "").strip().lower()
    if s in {"1", "true", "t", "yes", "y", "starter", "start"}:
        return 1.0
    if s in {"0", "false", "f", "no", "n", "bench"}:
        return 0.0
    return math.nan


def _roll(grouped, window: int, min_periods: int = 1) -> pd.Series:
    return grouped.transform(lambda s: s.shift(1).rolling(window, min_periods=min_periods).mean())


def _roll_sd(grouped, window: int, min_periods: int = 2) -> pd.Series:
    return grouped.transform(lambda s: s.shift(1).rolling(window, min_periods=min_periods).std(ddof=1))


def _ensure_numeric(df: pd.DataFrame, cols: list[str]) -> None:
    for c in cols:
        if c not in df:
            df[c] = np.nan
        else:
            df[c] = pd.to_numeric(df[c], errors="coerce")


def build_feature_frame(raw: pd.DataFrame) -> pd.DataFrame:
    required = {"match_id", "season", "player_key", "team", "opponent", "assists", "rebounds", "minutes", "match_time"}
    missing = sorted(required - set(raw.columns))
    if missing:
        raise ValueError(f"canonical historical table missing {missing}")
    df = raw.copy()
    for c in ("match_id", "season", "player_key", "team", "opponent"):
        df[c] = df[c].astype(str)
    df["match_time"] = pd.to_datetime(df["match_time"], errors="coerce", utc=True)
    _ensure_numeric(df, ["assists", "rebounds", "minutes"] + PLAYER_OPTIONAL_NUMERIC + TEAM_ENV_NUMERIC)
    df["starter_num"] = df.get("starter", pd.Series(index=df.index, dtype=object)).map(_starter_bool)
    if "home_away" in df:
        h = df["home_away"].astype(str).str.lower().str.strip()
        df["home_flag"] = h.isin({"1", "home", "h"}).astype(float)
    else:
        df["home_flag"] = np.nan
    df = df.sort_values(["match_time", "match_id", "team", "player_key"], na_position="last").reset_index(drop=True)

    team_game = df.groupby(["match_id", "season", "team"], as_index=False).agg(
        match_time=("match_time", "first"), opponent=("opponent", "first"),
        player_sum_assists=("assists", "sum"), player_sum_rebounds=("rebounds", "sum"),
        player_sum_points=("points", "sum"),
        team_points_box=("team_points_box", "first"), team_assists_box=("team_assists_box", "first"),
        team_rebounds_box=("team_rebounds_box", "first"), team_fgm=("team_fgm", "first"),
        team_fga=("team_fga", "first"), team_missed_fg=("team_missed_fg", "first"),
        team_possessions_est=("team_possessions_est", "first"),
        allowed_points_game=("opp_points_box", "first"), allowed_assists_game=("opp_assists_box", "first"),
        allowed_rebounds_game=("opp_rebounds_box", "first"), fgm_allowed_game=("opp_fgm", "first"),
    )
    team_game["team_points"] = team_game["team_points_box"].combine_first(team_game["player_sum_points"])
    team_game["team_assists"] = team_game["team_assists_box"].combine_first(team_game["player_sum_assists"])
    team_game["team_rebounds"] = team_game["team_rebounds_box"].combine_first(team_game["player_sum_rebounds"])

    # Older/synthetic rows may lack explicit opponent team-box columns. Reconstruct
    # what each defense allowed from the opposing team's exact same-game totals.
    # This fallback uses only completed historical game facts and is shifted before
    # becoming a predictor for any later target game.
    opponent_actual = team_game[[
        "match_id", "team", "team_points", "team_assists", "team_rebounds", "team_fgm"
    ]].rename(columns={
        "team": "opponent",
        "team_points": "fallback_allowed_points",
        "team_assists": "fallback_allowed_assists",
        "team_rebounds": "fallback_allowed_rebounds",
        "team_fgm": "fallback_fgm_allowed",
    })
    team_game = team_game.merge(opponent_actual, on=["match_id", "opponent"], how="left")
    team_game["allowed_points_game"] = team_game["allowed_points_game"].combine_first(team_game["fallback_allowed_points"])
    team_game["allowed_assists_game"] = team_game["allowed_assists_game"].combine_first(team_game["fallback_allowed_assists"])
    team_game["allowed_rebounds_game"] = team_game["allowed_rebounds_game"].combine_first(team_game["fallback_allowed_rebounds"])
    team_game["fgm_allowed_game"] = team_game["fgm_allowed_game"].combine_first(team_game["fallback_fgm_allowed"])
    team_game = team_game.drop(columns=[
        "fallback_allowed_points", "fallback_allowed_assists", "fallback_allowed_rebounds", "fallback_fgm_allowed"
    ])

    team_game = team_game.sort_values(["team", "match_time", "match_id"]).reset_index(drop=True)
    tg = team_game.groupby("team", sort=False)
    tsg = team_game.groupby(["team", "season"], sort=False)
    team_game["team_games_prior"] = tg.cumcount().astype(float)
    team_game["team_season_games_prior"] = tsg.cumcount().astype(float)
    roll_map = {
        "team_assists": "team_assists_mean", "team_rebounds": "team_rebounds_mean",
        "team_points": "team_points_mean", "team_fgm": "team_fgm_mean",
        "team_missed_fg": "team_missed_fg_mean", "team_possessions_est": "team_possessions_mean",
        "allowed_assists_game": "assists_allowed_mean", "allowed_rebounds_game": "rebounds_allowed_mean",
        "allowed_points_game": "points_allowed_mean", "fgm_allowed_game": "fgm_allowed_mean",
    }
    for n in (5, 10):
        for raw_col, stem in roll_map.items():
            team_game[f"{stem}_{n}"] = _roll(tg[raw_col], n)
    team_game["team_prev_time"] = tg["match_time"].shift(1)
    team_game["team_days_rest"] = (team_game["match_time"] - team_game["team_prev_time"]).dt.total_seconds() / 86400.0

    own_cols = [
        "match_id", "team", "team_games_prior", "team_season_games_prior", "team_days_rest",
        "team_assists_mean_5", "team_assists_mean_10", "team_rebounds_mean_5", "team_rebounds_mean_10",
        "team_points_mean_5", "team_points_mean_10", "team_fgm_mean_5", "team_fgm_mean_10",
        "team_missed_fg_mean_5", "team_missed_fg_mean_10", "team_possessions_mean_5", "team_possessions_mean_10",
    ]
    df = df.merge(team_game[own_cols], on=["match_id", "team"], how="left")

    opp_cols = [
        "match_id", "team", "team_days_rest", "team_possessions_mean_5", "team_possessions_mean_10",
        "team_missed_fg_mean_5", "team_missed_fg_mean_10", "assists_allowed_mean_5", "assists_allowed_mean_10",
        "rebounds_allowed_mean_5", "rebounds_allowed_mean_10", "points_allowed_mean_5", "points_allowed_mean_10",
        "fgm_allowed_mean_5", "fgm_allowed_mean_10",
    ]
    opp_features = team_game[opp_cols].rename(columns={
        "team": "opponent", "team_days_rest": "opponent_days_rest",
        "team_possessions_mean_5": "opponent_possessions_mean_5", "team_possessions_mean_10": "opponent_possessions_mean_10",
        "team_missed_fg_mean_5": "opponent_missed_fg_mean_5", "team_missed_fg_mean_10": "opponent_missed_fg_mean_10",
        "assists_allowed_mean_5": "opponent_assists_allowed_mean_5", "assists_allowed_mean_10": "opponent_assists_allowed_mean_10",
        "rebounds_allowed_mean_5": "opponent_rebounds_allowed_mean_5", "rebounds_allowed_mean_10": "opponent_rebounds_allowed_mean_10",
        "points_allowed_mean_5": "opponent_points_allowed_mean_5", "points_allowed_mean_10": "opponent_points_allowed_mean_10",
        "fgm_allowed_mean_5": "opponent_fgm_allowed_mean_5", "fgm_allowed_mean_10": "opponent_fgm_allowed_mean_10",
    })
    df = df.merge(opp_features, on=["match_id", "opponent"], how="left")

    pg = df.groupby("player_key", sort=False)
    psg = df.groupby(["player_key", "season"], sort=False)
    df["player_games_prior"] = pg.cumcount().astype(float)
    df["player_season_games_prior"] = psg.cumcount().astype(float)
    for n in (3, 5, 10):
        df[f"player_minutes_mean_{n}"] = _roll(pg["minutes"], n)
        df[f"player_assists_mean_{n}"] = _roll(pg["assists"], n)
        df[f"player_rebounds_mean_{n}"] = _roll(pg["rebounds"], n)
    for n in (5, 10):
        df[f"player_minutes_sd_{n}"] = _roll_sd(pg["minutes"], n)
        df[f"player_start_rate_{n}"] = _roll(pg["starter_num"], n)
        df[f"player_turnovers_mean_{n}"] = _roll(pg["turnovers"], n)
        df[f"player_fga_mean_{n}"] = _roll(pg["field_goals_attempted"], n)
        df[f"player_orb_mean_{n}"] = _roll(pg["rebounds_offensive"], n)
        df[f"player_drb_mean_{n}"] = _roll(pg["rebounds_defensive"], n)
    safe_minutes = df["minutes"].where(df["minutes"] > 0)
    df["assists_per_min"] = df["assists"] / safe_minutes
    df["rebounds_per_min"] = df["rebounds"] / safe_minutes
    pg = df.groupby("player_key", sort=False)
    for n in (5, 10):
        df[f"player_assists_per_min_mean_{n}"] = _roll(pg["assists_per_min"], n)
        df[f"player_rebounds_per_min_mean_{n}"] = _roll(pg["rebounds_per_min"], n)
    df["player_prev_time"] = pg["match_time"].shift(1)
    df["player_days_rest"] = (df["match_time"] - df["player_prev_time"]).dt.total_seconds() / 86400.0

    forbidden = {
        "assists", "rebounds", "minutes", "points", "starter_num", "assists_per_min", "rebounds_per_min",
        "turnovers", "field_goals_attempted", "rebounds_offensive", "rebounds_defensive",
        "team_points_box", "team_assists_box", "team_rebounds_box", "team_fgm", "team_fga",
        "team_missed_fg", "team_possessions_est",
    }
    for head, cols in HEAD_FEATURES.items():
        overlap = forbidden.intersection(cols)
        if overlap:
            raise AssertionError(f"{head} feature leakage aliases {sorted(overlap)}")
    return df


def feature_columns(head: str) -> list[str]:
    if head not in HEAD_FEATURES:
        raise ValueError(f"Unknown head {head}")
    return list(HEAD_FEATURES[head])
