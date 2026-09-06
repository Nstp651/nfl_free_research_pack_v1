#!/usr/bin/env python3
"""Build leak-safe historical NBL player-game source table for assists/rebounds.

Uses the free nblR/nblr_data GitHub release CSVs. The raw canonical table retains
player role/box-score facts plus exact team and opponent game environment. Model
features are constructed later with strict shift(1), so no target-game box score
can enter its own pregame prediction.

Release files use stable public GitHub download URLs directly. We intentionally do
not call GitHub's unauthenticated release API in CI because its shared-runner rate
limit is not a data-quality signal. Every downloaded byte stream is SHA-256 hashed
and recorded in the source receipt instead.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

import pandas as pd
import requests

REPO = "JaseZiv/nblr_data"
RELEASE_BASE = f"https://github.com/{REPO}/releases/download"
ASSETS = {
    "player": ("box_player", "box_player.csv"),
    "team": ("box_team", "box_team.csv"),
    "results": ("match_results", "results_wide.csv"),
}


def release_asset(tag: str, name: str) -> dict[str, Any]:
    return {
        "tag": tag,
        "name": name,
        "url": f"{RELEASE_BASE}/{tag}/{name}",
        "source_repository": f"https://github.com/{REPO}",
        "discovery": "stable_release_download_url",
    }


def download_csv(asset: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    r = requests.get(asset["url"], timeout=120, headers={"user-agent": "nick-nbl-model/0.1"})
    r.raise_for_status()
    raw = r.content
    actual = "sha256:" + hashlib.sha256(raw).hexdigest()
    receipt = {
        **asset,
        "sha256": actual,
        "bytes": len(raw),
        "etag": r.headers.get("ETag"),
        "last_modified": r.headers.get("Last-Modified"),
    }
    return pd.read_csv(pd.io.common.BytesIO(raw), low_memory=False), receipt


def first_col(df: pd.DataFrame, *names: str) -> str | None:
    lower = {str(c).lower(): c for c in df.columns}
    for name in names:
        if name in df.columns:
            return name
        if name.lower() in lower:
            return str(lower[name.lower()])
    return None


def numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def ncol(df: pd.DataFrame, *names: str) -> pd.Series:
    c = first_col(df, *names)
    return numeric(df[c]) if c else pd.Series(math.nan, index=df.index, dtype=float)


def parse_minutes(value: Any) -> float:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return math.nan
    text = str(value).strip()
    if not text:
        return math.nan
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        return float(text)
    parts = text.split(":")
    try:
        if len(parts) == 2:
            return float(parts[0]) + float(parts[1]) / 60.0
        if len(parts) == 3:
            return float(parts[0]) * 60.0 + float(parts[1]) + float(parts[2]) / 60.0
    except ValueError:
        return math.nan
    return math.nan


def normalized_name_key(df: pd.DataFrame) -> pd.Series:
    """Stable identity across legacy rows that predate player UUIDs."""
    first = first_col(df, "first_name", "firstname")
    family = first_col(df, "family_name", "last_name", "surname")
    scoreboard = first_col(df, "scoreboard_name", "player_name", "name")
    if first and family:
        raw = df[first].fillna("").astype(str).str.strip() + " " + df[family].fillna("").astype(str).str.strip()
        fallback = df[scoreboard].fillna("").astype(str) if scoreboard else pd.Series("", index=df.index)
        raw = raw.where(raw.str.strip().ne(""), fallback)
    elif scoreboard:
        raw = df[scoreboard].fillna("").astype(str)
    else:
        raise RuntimeError("Historical player data has no usable player identity columns")
    return (raw.str.lower().str.normalize("NFKD")
            .str.encode("ascii", errors="ignore").str.decode("ascii")
            .str.replace(r"[^a-z0-9]+", "", regex=True).replace("", pd.NA))


def canonical_team_environment(team: pd.DataFrame) -> pd.DataFrame:
    match = first_col(team, "match_id")
    name = first_col(team, "name", "team_name")
    opp = first_col(team, "opp_name", "opponent")
    if not match or not name or not opp:
        raise RuntimeError("Historical team box source missing match/team/opponent identity")
    env = pd.DataFrame({
        "match_id": team[match].astype(str),
        "team": team[name].astype(str),
        "opponent": team[opp].astype(str),
        "team_points_box": ncol(team, "points", "score"),
        "team_fgm": ncol(team, "field_goals_made"),
        "team_fga": ncol(team, "field_goals_attempted"),
        "team_3pm": ncol(team, "three_pointers_made"),
        "team_3pa": ncol(team, "three_pointers_attempted"),
        "team_ftm": ncol(team, "free_throws_made"),
        "team_fta": ncol(team, "free_throws_attempted"),
        "team_orb": ncol(team, "rebounds_offensive"),
        "team_drb": ncol(team, "rebounds_defensive"),
        "team_rebounds_box": ncol(team, "rebounds_total"),
        "team_assists_box": ncol(team, "assists"),
        "team_turnovers": ncol(team, "turnovers", "turnovers_team"),
    })
    env["team_missed_fg"] = (env["team_fga"] - env["team_fgm"]).clip(lower=0)
    env["team_possessions_est"] = (
        env["team_fga"] - env["team_orb"] + env["team_turnovers"] + 0.44 * env["team_fta"]
    )
    if env.duplicated(["match_id", "team"]).any():
        raise RuntimeError("Duplicate historical team-game rows")
    oppenv = env.drop(columns=["opponent"]).rename(columns={
        "team": "opponent",
        **{c: f"opp_{c[5:]}" for c in env.columns if c.startswith("team_")},
    })
    merged = env.merge(oppenv, on=["match_id", "opponent"], how="left")
    if "opp_possessions_est" in merged:
        merged["game_possessions_est"] = merged[["team_possessions_est", "opp_possessions_est"]].mean(axis=1)
    else:
        merged["game_possessions_est"] = merged["team_possessions_est"]
    return merged


def canonical_player_games(player: pd.DataFrame, team: pd.DataFrame, results: pd.DataFrame) -> pd.DataFrame:
    match = first_col(player, "match_id")
    season = first_col(player, "season")
    team_col = first_col(player, "team_name", "team")
    opp = first_col(player, "opp_name", "opponent", "opponent_name")
    assists = first_col(player, "assists", "assist", "assists_total")
    rebounds = first_col(player, "rebounds_total", "rebounds", "total_rebounds")
    minutes = first_col(player, "minutes")
    seconds = first_col(player, "seconds")
    starter = first_col(player, "starter", "is_starter")
    position = first_col(player, "playing_position", "position")
    home_away = first_col(player, "home_away")
    points = first_col(player, "points")
    source_pid = first_col(player, "player_id", "person_id", "external_id")
    required = {"match_id": match, "season": season, "team": team_col,
                "assists": assists, "rebounds": rebounds}
    missing = [k for k, v in required.items() if not v]
    if missing:
        raise RuntimeError(f"Historical player schema missing required fields {missing}; columns={list(player.columns)}")

    out = pd.DataFrame({
        "match_id": player[match].astype(str),
        "season": player[season].astype(str),
        "player_key": normalized_name_key(player),
        "source_player_id": player[source_pid].astype("string") if source_pid else pd.NA,
        "team": player[team_col].astype(str),
        "opponent": player[opp].astype(str) if opp else None,
        "assists": numeric(player[assists]),
        "rebounds": numeric(player[rebounds]),
        "rebounds_offensive": ncol(player, "rebounds_offensive"),
        "rebounds_defensive": ncol(player, "rebounds_defensive"),
        "turnovers": ncol(player, "turnovers"),
        "field_goals_attempted": ncol(player, "field_goals_attempted"),
        "field_goals_made": ncol(player, "field_goals_made"),
        "three_pointers_attempted": ncol(player, "three_pointers_attempted"),
        "points": numeric(player[points]) if points else math.nan,
        "starter": player[starter].astype(str) if starter else None,
        "position": player[position].astype(str) if position else None,
        "home_away": player[home_away] if home_away else None,
    })
    if seconds:
        out["minutes"] = numeric(player[seconds]) / 60.0
    elif minutes:
        out["minutes"] = player[minutes].map(parse_minutes)
    else:
        out["minutes"] = math.nan

    env = canonical_team_environment(team)
    out = out.merge(env, on=["match_id", "team", "opponent"], how="left")

    r_match = first_col(results, "match_id")
    r_time = first_col(results, "match_time_utc", "match_time", "date", "match_date")
    if r_match and r_time:
        lookup = results[[r_match, r_time]].copy()
        lookup.columns = ["match_id", "match_time"]
        lookup["match_id"] = lookup["match_id"].astype(str)
        lookup = lookup.drop_duplicates("match_id")
        out = out.merge(lookup, on="match_id", how="left")
        out["match_time"] = pd.to_datetime(out["match_time"], errors="coerce", utc=True)
    else:
        out["match_time"] = pd.NaT

    out = out[out["player_key"].notna() & out["assists"].notna() & out["rebounds"].notna()].copy()
    out = out[(out["assists"] >= 0) & (out["rebounds"] >= 0)]
    out = out.sort_values(["match_time", "match_id", "team", "player_key"], na_position="last").reset_index(drop=True)
    if out.duplicated(["match_id", "team", "player_key"]).any():
        dupes = out[out.duplicated(["match_id", "team", "player_key"], keep=False)].head(10)
        raise RuntimeError("Duplicate player-game identity rows: " + dupes.to_json(orient="records"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="nbl_player_props_v1/data/historical/player_games.csv.gz")
    ap.add_argument("--receipt", default="nbl_player_props_v1/data/historical/source_receipt.json")
    args = ap.parse_args()

    loaded: dict[str, pd.DataFrame] = {}
    receipts: dict[str, Any] = {}
    for key, (tag, name) in ASSETS.items():
        asset = release_asset(tag, name)
        loaded[key], receipts[key] = download_csv(asset)
        print(f"SOURCE {key} rows={len(loaded[key])} cols={len(loaded[key].columns)} sha256={receipts[key]['sha256']}")
        print(f"COLUMNS {key}: {','.join(map(str, loaded[key].columns))}")

    games = canonical_player_games(loaded["player"], loaded["team"], loaded["results"])
    out = Path(args.output); out.parent.mkdir(parents=True, exist_ok=True)
    games.to_csv(out, index=False, compression="gzip")

    id_counts = (games.dropna(subset=["source_player_id"])
                 .groupby("player_key")["source_player_id"].nunique())
    multi_id_keys = int((id_counts > 1).sum())
    receipt = {
        "schema_version": "0.1.3",
        "market_data": False,
        "sources": receipts,
        "rows": len(games),
        "seasons": sorted(games["season"].dropna().astype(str).unique().tolist()),
        "players": int(games["player_key"].nunique()),
        "matches": int(games["match_id"].nunique()),
        "assists_non_null": int(games["assists"].notna().sum()),
        "rebounds_non_null": int(games["rebounds"].notna().sum()),
        "team_environment_match_rate": float(games["game_possessions_est"].notna().mean()),
        "player_identity_method": "normalized_name_with_source_player_id_retained",
        "normalized_name_keys_with_multiple_source_ids": multi_id_keys,
        "output_sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
    }
    rp = Path(args.receipt); rp.parent.mkdir(parents=True, exist_ok=True)
    rp.write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"ok": True, **{k: receipt[k] for k in (
        "rows", "players", "matches", "team_environment_match_rate", "normalized_name_keys_with_multiple_source_ids")}}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
