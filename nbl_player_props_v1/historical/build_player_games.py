#!/usr/bin/env python3
"""Build leak-safe historical NBL player-game source table for assists/rebounds.

Free source: JaseZiv/nblr_data release CSVs. The player/team exports contain the
box-score state required by the model; results_wide is authoritative for game time.
All model rolling features are built later with shift(1).
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
    return {"tag": tag, "name": name, "url": f"{RELEASE_BASE}/{tag}/{name}",
            "source_repository": f"https://github.com/{REPO}", "discovery": "stable_release_download_url"}


def download_csv(asset: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    r = requests.get(asset["url"], timeout=120, headers={"user-agent": "nick-nbl-model/0.1"})
    r.raise_for_status(); raw = r.content
    return pd.read_csv(pd.io.common.BytesIO(raw), low_memory=False), {
        **asset, "sha256": "sha256:" + hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
        "etag": r.headers.get("ETag"), "last_modified": r.headers.get("Last-Modified"),
    }


def first_col(df: pd.DataFrame, *names: str) -> str | None:
    lower = {str(c).lower(): c for c in df.columns}
    for name in names:
        if name in df.columns: return name
        if name.lower() in lower: return str(lower[name.lower()])
    return None


def numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def ncol(df: pd.DataFrame, *names: str) -> pd.Series:
    out = pd.Series(math.nan, index=df.index, dtype=float); lower = {str(c).lower(): c for c in df.columns}
    for name in names:
        col = name if name in df.columns else lower.get(name.lower())
        if col is not None: out = out.combine_first(numeric(df[col]))
    return out


def collapse_identical_duplicates(df: pd.DataFrame, identity: list[str], label: str) -> tuple[pd.DataFrame, int]:
    dup = df[df.duplicated(identity, keep=False)]
    if dup.empty: return df, 0
    compare = [c for c in df.columns if c not in identity]; conflicts = []
    for key, group in dup.groupby(identity, dropna=False, sort=False):
        if len(group[compare].drop_duplicates()) > 1:
            conflicts.append((key, group.head(3).to_dict(orient="records")))
            if len(conflicts) >= 3: break
    if conflicts: raise RuntimeError(f"Conflicting duplicate {label} identities: {conflicts}")
    before = len(df); return df.drop_duplicates(identity, keep="first").copy(), before - len(df.drop_duplicates(identity, keep="first"))


def parse_minutes(value: Any) -> float:
    if value is None or (isinstance(value, float) and math.isnan(value)): return math.nan
    text = str(value).strip()
    if not text: return math.nan
    if re.fullmatch(r"\d+(?:\.\d+)?", text): return float(text)
    parts = text.split(":")
    try:
        if len(parts) == 2: return float(parts[0]) + float(parts[1]) / 60
        if len(parts) == 3: return float(parts[0]) * 60 + float(parts[1]) + float(parts[2]) / 60
    except ValueError: pass
    return math.nan


def player_minutes_series(player: pd.DataFrame, seconds: str | None, minutes: str | None) -> pd.Series:
    """Use row-level seconds first, then fall back to the minutes field.

    nblr_data keeps both columns in the combined export, but source population can
    change by season. Choosing one column globally silently dropped 2025-26 when
    `seconds` existed in the schema but was blank for those rows.
    """
    out = pd.Series(math.nan, index=player.index, dtype=float)
    if seconds:
        sec = numeric(player[seconds])
        out = out.combine_first(sec.where(sec >= 0) / 60.0)
    if minutes:
        parsed = player[minutes].map(parse_minutes)
        out = out.combine_first(parsed.where(parsed >= 0))
    return out


def normalized_name_key(df: pd.DataFrame) -> pd.Series:
    first = first_col(df, "first_name", "firstname"); family = first_col(df, "family_name", "last_name", "surname")
    scoreboard = first_col(df, "scoreboard_name", "player_name", "name")
    if first and family:
        raw = df[first].fillna("").astype(str).str.strip() + " " + df[family].fillna("").astype(str).str.strip()
        fallback = df[scoreboard].fillna("").astype(str) if scoreboard else pd.Series("", index=df.index)
        raw = raw.where(raw.str.strip().ne(""), fallback)
    elif scoreboard: raw = df[scoreboard].fillna("").astype(str)
    else: raise RuntimeError("Historical player data has no usable player identity columns")
    return (raw.str.lower().str.normalize("NFKD").str.encode("ascii", errors="ignore").str.decode("ascii")
            .str.replace(r"[^a-z0-9]+", "", regex=True).replace("", pd.NA))


def canonical_team_environment(team: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    match = first_col(team, "match_id"); season = first_col(team, "season"); name = first_col(team, "name", "team_name"); opp = first_col(team, "opp_name", "opponent")
    if not all((match, season, name, opp)): raise RuntimeError("Historical team box source missing identity")
    env = pd.DataFrame({
        "match_id": team[match].astype(str), "season": team[season].astype(str), "team": team[name].astype(str), "opponent": team[opp].astype(str),
        "team_points_box": ncol(team, "points", "score"), "team_fgm": ncol(team, "field_goals_made"), "team_fga": ncol(team, "field_goals_attempted"),
        "team_3pm": ncol(team, "three_pointers_made"), "team_3pa": ncol(team, "three_pointers_attempted"), "team_ftm": ncol(team, "free_throws_made"),
        "team_fta": ncol(team, "free_throws_attempted"), "team_orb": ncol(team, "rebounds_offensive"), "team_drb": ncol(team, "rebounds_defensive"),
        "team_rebounds_box": ncol(team, "rebounds_total"), "team_assists_box": ncol(team, "assists"), "team_turnovers": ncol(team, "turnovers", "turnovers_team"),
    })
    env["team_missed_fg"] = (env["team_fga"] - env["team_fgm"]).clip(lower=0)
    env["team_possessions_est"] = env["team_fga"] - env["team_orb"] + env["team_turnovers"] + .44 * env["team_fta"]
    env, collapsed = collapse_identical_duplicates(env, ["season", "match_id", "team"], "team-game")
    oppenv = env.drop(columns=["opponent"]).rename(columns={"team": "opponent", **{c: f"opp_{c[5:]}" for c in env.columns if c.startswith("team_")}})
    merged = env.merge(oppenv, on=["season", "match_id", "opponent"], how="left")
    merged["game_possessions_est"] = merged[["team_possessions_est", "opp_possessions_est"]].mean(axis=1)
    return merged, collapsed


def result_identity_maps(results: pd.DataFrame) -> tuple[dict[str, Any], dict[str, str]]:
    """Map globally unique match UUID -> authoritative UTC time and season."""
    m = first_col(results, "match_id"); t = first_col(results, "match_time_utc", "match_time", "date", "match_date"); s = first_col(results, "season")
    if not m or not t: raise RuntimeError("results_wide missing match_id/time")
    work = pd.DataFrame({"match_id": results[m].astype(str), "time": results[t], "season": results[s].astype(str) if s else pd.NA})
    time_map: dict[str, Any] = {}; season_map: dict[str, str] = {}
    for match_id, group in work.groupby("match_id", sort=False):
        parsed = pd.to_datetime(group["time"], errors="coerce", utc=True).dropna().drop_duplicates()
        seasons = group["season"].dropna().astype(str).drop_duplicates()
        if len(parsed) > 1 or len(seasons) > 1: raise RuntimeError(f"results match UUID collision: {match_id}")
        if len(parsed) == 1: time_map[str(match_id)] = parsed.iloc[0]
        if len(seasons) == 1: season_map[str(match_id)] = seasons.iloc[0]
    return time_map, season_map


def canonical_player_games(player: pd.DataFrame, team: pd.DataFrame, results: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    match = first_col(player, "match_id"); season = first_col(player, "season"); team_col = first_col(player, "team_name", "team"); opp = first_col(player, "opp_name", "opponent", "opponent_name")
    assists = first_col(player, "assists", "assist", "assists_total"); rebounds = first_col(player, "rebounds_total", "rebounds", "total_rebounds")
    if not all((match, season, team_col, assists, rebounds)): raise RuntimeError("Historical player schema missing required identity/stat fields")
    minutes = first_col(player, "minutes"); seconds = first_col(player, "seconds"); starter = first_col(player, "starter", "is_starter"); position = first_col(player, "playing_position", "position")
    home_away = first_col(player, "home_away"); points = first_col(player, "points"); source_pid = first_col(player, "player_id", "person_id", "external_id"); player_time = first_col(player, "match_time_utc", "match_time", "date", "match_date")
    out = pd.DataFrame({
        "match_id": player[match].astype(str), "season": player[season].astype(str), "player_key": normalized_name_key(player),
        "source_player_id": player[source_pid].astype("string") if source_pid else pd.NA, "team": player[team_col].astype(str), "opponent": player[opp].astype(str) if opp else None,
        "assists": numeric(player[assists]), "rebounds": numeric(player[rebounds]), "rebounds_offensive": ncol(player, "rebounds_offensive"), "rebounds_defensive": ncol(player, "rebounds_defensive"),
        "turnovers": ncol(player, "turnovers"), "field_goals_attempted": ncol(player, "field_goals_attempted"), "field_goals_made": ncol(player, "field_goals_made"),
        "three_pointers_attempted": ncol(player, "three_pointers_attempted"), "points": numeric(player[points]) if points else math.nan,
        "starter": player[starter].astype(str) if starter else None, "position": player[position].astype(str) if position else None,
        "home_away": player[home_away] if home_away else None, "_player_time": player[player_time] if player_time else pd.NA,
    })
    out["minutes"] = player_minutes_series(player, seconds, minutes)
    env, team_dups = canonical_team_environment(team); out = out.merge(env, on=["season", "match_id", "team", "opponent"], how="left")

    time_map, season_map = result_identity_maps(results)
    result_time = pd.to_datetime(out["match_id"].map(time_map), errors="coerce", utc=True)
    player_time_parsed = pd.to_datetime(out.pop("_player_time"), errors="coerce", utc=True)
    result_season = out["match_id"].map(season_map)
    known = result_season.notna(); mismatch = out.loc[known & (result_season.astype(str) != out["season"].astype(str)), ["match_id", "season"]]
    if not mismatch.empty: raise RuntimeError("Historical results/player season mismatch: " + mismatch.head(5).to_json(orient="records"))
    out["match_time"] = result_time.combine_first(player_time_parsed)

    out = out[out["player_key"].notna() & out["assists"].notna() & out["rebounds"].notna()].copy()
    out = out[(out["assists"] >= 0) & (out["rebounds"] >= 0)].sort_values(["match_time", "season", "match_id", "team", "player_key"], na_position="last").reset_index(drop=True)
    out, player_dups = collapse_identical_duplicates(out, ["season", "match_id", "team", "player_key"], "player-game")
    return out, {"team_exact_duplicate_rows_collapsed": team_dups, "player_exact_duplicate_rows_collapsed": player_dups}


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--output", default="nbl_player_props_v1/data/historical/player_games.csv.gz"); ap.add_argument("--receipt", default="nbl_player_props_v1/data/historical/source_receipt.json"); args = ap.parse_args()
    loaded: dict[str, pd.DataFrame] = {}; receipts: dict[str, Any] = {}
    for key, (tag, name) in ASSETS.items():
        loaded[key], receipts[key] = download_csv(release_asset(tag, name))
        print(f"SOURCE {key} rows={len(loaded[key])} cols={len(loaded[key].columns)} sha256={receipts[key]['sha256']}")
        print(f"COLUMNS {key}: {','.join(map(str, loaded[key].columns))}")
    games, duplicate_audit = canonical_player_games(loaded["player"], loaded["team"], loaded["results"])
    out = Path(args.output); out.parent.mkdir(parents=True, exist_ok=True); games.to_csv(out, index=False, compression={"method": "gzip", "mtime": 0})
    id_counts = games.dropna(subset=["source_player_id"]).groupby("player_key")["source_player_id"].nunique(); seasons = sorted(games["season"].dropna().astype(str).unique().tolist()); latest = seasons[-1]; latest_rows = games[games["season"].astype(str) == latest]
    receipt = {
        "schema_version": "0.1.9", "market_data": False, "identity_binding": "season+globally_unique_match_uuid+team+normalized_player_name",
        "timestamp_binding": "results_wide.match_id direct map -> match_time_utc; player match_time fallback", "sources": receipts, "rows": len(games), "seasons": seasons,
        "players": int(games["player_key"].nunique()), "matches": int(games[["season", "match_id"]].drop_duplicates().shape[0]), "assists_non_null": int(games["assists"].notna().sum()),
        "rebounds_non_null": int(games["rebounds"].notna().sum()), "minutes_non_null_rate": float(games["minutes"].notna().mean()), "team_environment_match_rate": float(games["game_possessions_est"].notna().mean()),
        "match_time_non_null_rate": float(games["match_time"].notna().mean()), "latest_season": latest, "latest_season_rows": int(len(latest_rows)),
        "latest_season_match_time_non_null_rate": float(latest_rows["match_time"].notna().mean()), "latest_season_minutes_non_null_rate": float(latest_rows["minutes"].notna().mean()), "player_identity_method": "normalized_name_with_source_player_id_retained",
        "minutes_binding": "row-level seconds/60 with parsed minutes fallback", "normalized_name_keys_with_multiple_source_ids": int((id_counts > 1).sum()), "duplicate_audit": duplicate_audit, "output_sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
    }
    rp = Path(args.receipt); rp.parent.mkdir(parents=True, exist_ok=True); rp.write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"ok": True, **{k: receipt[k] for k in ("rows", "players", "matches", "minutes_non_null_rate", "team_environment_match_rate", "match_time_non_null_rate", "latest_season", "latest_season_rows", "latest_season_match_time_non_null_rate", "latest_season_minutes_non_null_rate", "normalized_name_keys_with_multiple_source_ids")}, "duplicate_audit": duplicate_audit}, sort_keys=True))
    return 0


if __name__ == "__main__": raise SystemExit(main())