from __future__ import annotations

from typing import Iterable

import pandas as pd

CORE_INPUT_COLUMNS = (
    "game_id",
    "season",
    "season_type",
    "game_date_time",
    "athlete_id",
    "athlete_display_name",
    "team_id",
    "team_name",
    "team_abbreviation",
    "opponent_team_id",
    "opponent_team_name",
    "opponent_team_abbreviation",
    "home_away",
    "minutes",
    "starter",
    "did_not_play",
    "field_goals_made",
    "field_goals_attempted",
    "three_point_field_goals_made",
    "three_point_field_goals_attempted",
    "free_throws_made",
    "free_throws_attempted",
    "offensive_rebounds",
    "defensive_rebounds",
    "rebounds",
    "assists",
    "turnovers",
    "team_score",
    "opponent_team_score",
)

PROHIBITED_MARKET_COLUMNS = {
    "home_team_spread",
    "game_spread",
    "home_favorite",
    "game_spread_available",
    "over_under",
    "spread",
    "money_line",
    "provider_name",
    "odds",
}

COUNT_COLUMNS = (
    "field_goals_made",
    "field_goals_attempted",
    "three_point_field_goals_made",
    "three_point_field_goals_attempted",
    "free_throws_made",
    "free_throws_attempted",
    "offensive_rebounds",
    "defensive_rebounds",
    "rebounds",
    "assists",
    "turnovers",
    "team_score",
    "opponent_team_score",
)


def _minutes(value) -> float:
    if pd.isna(value):
        return 0.0
    if isinstance(value, str) and ":" in value:
        minutes, seconds = value.split(":", 1)
        return float(minutes) + float(seconds) / 60.0
    return float(value)


def _require_columns(frame: pd.DataFrame, columns: Iterable[str]) -> None:
    missing = [c for c in columns if c not in frame.columns]
    if missing:
        raise ValueError(f"missing player-box columns: {missing}")


def normalize_player_box(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize one or more SportsDataverse/hoopR NBA player-box seasons.

    Output grain is one played NBA player x game. No market-derived source field is
    permitted into the canonical table.
    """
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        raise ValueError("non-empty player-box frame required")
    _require_columns(frame, CORE_INPUT_COLUMNS)

    leaked = sorted(PROHIBITED_MARKET_COLUMNS.intersection(frame.columns))
    # Source frames may contain unrelated columns, but known market fields are never
    # selected below. Keep the audit explicit so a future schema change is visible.

    out = frame.loc[:, CORE_INPUT_COLUMNS].copy()
    out["game_id_espn"] = out.pop("game_id").astype("string")
    out["player_id_espn"] = out.pop("athlete_id").astype("string")
    out["player_name"] = out.pop("athlete_display_name").astype("string").str.strip()
    out["team_id_espn"] = out.pop("team_id").astype("string")
    out["opponent_team_id_espn"] = out.pop("opponent_team_id").astype("string")

    out["game_start_utc"] = pd.to_datetime(out.pop("game_date_time"), utc=True, errors="raise")
    out["game_date_et"] = out["game_start_utc"].dt.tz_convert("America/New_York").dt.strftime("%Y-%m-%d")
    out["minutes"] = out["minutes"].map(_minutes).astype(float)
    out["starter"] = out["starter"].fillna(False).astype(bool)
    out["did_not_play"] = out["did_not_play"].fillna(False).astype(bool)
    out["is_home"] = out["home_away"].astype("string").str.lower().eq("home")

    for column in COUNT_COLUMNS:
        out[column] = pd.to_numeric(out[column], errors="raise")

    out = out[(~out["did_not_play"]) & (out["minutes"] > 0)].copy()
    if out.empty:
        raise ValueError("no played player-games after normalization")

    if out[["game_id_espn", "player_id_espn", "game_start_utc"]].isna().any().any():
        raise ValueError("null canonical identity/timestamp field")
    if (out["minutes"] < 0).any() or (out["minutes"] > 65).any():
        raise ValueError("invalid minutes detected")
    if (out[list(COUNT_COLUMNS)] < 0).any().any():
        raise ValueError("negative count detected")
    if (out["offensive_rebounds"] + out["defensive_rebounds"] != out["rebounds"]).any():
        raise ValueError("ORB + DRB != REB")

    dup = out.duplicated(["game_id_espn", "player_id_espn"], keep=False)
    if dup.any():
        sample = out.loc[dup, ["game_id_espn", "player_id_espn"]].head(10).to_dict("records")
        raise ValueError(f"duplicate canonical player-game rows: {sample}")

    out["market_data"] = False
    out["source_schema"] = "sportsdataverse_espn_nba_player_box"
    out["source_market_columns_observed"] = ",".join(leaked)

    ordered = [
        "season",
        "season_type",
        "game_id_espn",
        "game_start_utc",
        "game_date_et",
        "player_id_espn",
        "player_name",
        "team_id_espn",
        "team_name",
        "team_abbreviation",
        "opponent_team_id_espn",
        "opponent_team_name",
        "opponent_team_abbreviation",
        "is_home",
        "starter",
        "minutes",
        "assists",
        "rebounds",
        "offensive_rebounds",
        "defensive_rebounds",
        "turnovers",
        "field_goals_made",
        "field_goals_attempted",
        "three_point_field_goals_made",
        "three_point_field_goals_attempted",
        "free_throws_made",
        "free_throws_attempted",
        "team_score",
        "opponent_team_score",
        "market_data",
        "source_schema",
        "source_market_columns_observed",
    ]
    return out.loc[:, ordered].sort_values(["game_start_utc", "game_id_espn", "team_id_espn", "player_id_espn"]).reset_index(drop=True)
