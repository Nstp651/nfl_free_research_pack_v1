#!/usr/bin/env python3
"""Build compact post-history priors for NBL player-prop runtime inference.

The canonical historical table is excellent for training but unnecessarily large for
matchday inference. This script collapses it to the latest rolling player and team
state *after* the most recent completed game. Unlike taking the final training row,
these rolling values include that final game's box score and therefore represent the
correct prior for the next fixture.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCHEMA_VERSION = "nbl_historical_prior_snapshot_v1"
PLAYER_WINDOWS = (3, 5, 10)
TEAM_WINDOWS = (5, 10)


def season_start(value: Any) -> int | None:
    m = re.search(r"(?:19|20)\d{2}", str(value or ""))
    return int(m.group(0)) if m else None


def finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def mean_last(series: pd.Series, n: int) -> float | None:
    values = pd.to_numeric(series, errors="coerce").dropna().tail(n)
    return finite(values.mean()) if len(values) else None


def sd_last(series: pd.Series, n: int) -> float | None:
    values = pd.to_numeric(series, errors="coerce").dropna().tail(n)
    return finite(values.std(ddof=1)) if len(values) >= 2 else None


def starter_number(value: Any) -> float | None:
    text = str(value or "").strip().lower()
    if text in {"1", "true", "t", "yes", "y", "starter", "start"}:
        return 1.0
    if text in {"0", "false", "f", "no", "n", "bench"}:
        return 0.0
    return None


def _iso(value: Any) -> str | None:
    ts = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(ts):
        return None
    return ts.isoformat()


def player_snapshot(group: pd.DataFrame) -> dict[str, Any]:
    g = group.sort_values(["match_time", "season", "match_id"]).copy()
    latest = g.iloc[-1]
    minutes = pd.to_numeric(g["minutes"], errors="coerce")
    assists = pd.to_numeric(g["assists"], errors="coerce")
    rebounds = pd.to_numeric(g["rebounds"], errors="coerce")
    safe_minutes = minutes.where(minutes > 0)
    starter = g.get("starter", pd.Series(index=g.index, dtype=object)).map(starter_number)
    latest_season = str(latest["season"])
    season_games = int((g["season"].astype(str) == latest_season).sum())

    features: dict[str, Any] = {
        "player_games_prior": float(len(g)),
        "player_last_season_games": float(season_games),
    }
    for n in PLAYER_WINDOWS:
        features[f"player_minutes_mean_{n}"] = mean_last(minutes, n)
        features[f"player_assists_mean_{n}"] = mean_last(assists, n)
        features[f"player_rebounds_mean_{n}"] = mean_last(rebounds, n)
    for n in (5, 10):
        features[f"player_minutes_sd_{n}"] = sd_last(minutes, n)
        features[f"player_start_rate_{n}"] = mean_last(starter, n)
        features[f"player_turnovers_mean_{n}"] = mean_last(g["turnovers"], n)
        features[f"player_fga_mean_{n}"] = mean_last(g["field_goals_attempted"], n)
        features[f"player_orb_mean_{n}"] = mean_last(g["rebounds_offensive"], n)
        features[f"player_drb_mean_{n}"] = mean_last(g["rebounds_defensive"], n)
        features[f"player_assists_per_min_mean_{n}"] = mean_last(assists / safe_minutes, n)
        features[f"player_rebounds_per_min_mean_{n}"] = mean_last(rebounds / safe_minutes, n)

    source_ids = sorted({str(x) for x in g.get("source_player_id", pd.Series(dtype=object)).dropna().astype(str)})
    return {
        "player_key": str(latest["player_key"]),
        "source_player_ids": source_ids,
        "last_team": str(latest["team"]),
        "last_season": latest_season,
        "last_season_start": season_start(latest_season),
        "last_match_time": _iso(latest["match_time"]),
        "features": features,
    }


def team_snapshot(group: pd.DataFrame) -> dict[str, Any]:
    g = group.sort_values(["match_time", "season", "match_id"]).copy()
    latest = g.iloc[-1]
    latest_season = str(latest["season"])
    season_games = int((g["season"].astype(str) == latest_season).sum())
    features: dict[str, Any] = {
        "team_games_prior": float(len(g)),
        "team_last_season_games": float(season_games),
    }
    mapping = {
        "team_points_box": "team_points_mean",
        "team_assists_box": "team_assists_mean",
        "team_rebounds_box": "team_rebounds_mean",
        "team_fgm": "team_fgm_mean",
        "team_missed_fg": "team_missed_fg_mean",
        "team_possessions_est": "team_possessions_mean",
        "opp_points_box": "points_allowed_mean",
        "opp_assists_box": "assists_allowed_mean",
        "opp_rebounds_box": "rebounds_allowed_mean",
        "opp_fgm": "fgm_allowed_mean",
        "opp_missed_fg": "missed_fg_allowed_mean",
        "opp_possessions_est": "opponent_possessions_mean",
    }
    for n in TEAM_WINDOWS:
        for raw, stem in mapping.items():
            if raw in g:
                features[f"{stem}_{n}"] = mean_last(g[raw], n)
    return {
        "team": str(latest["team"]),
        "last_season": latest_season,
        "last_season_start": season_start(latest_season),
        "last_match_time": _iso(latest["match_time"]),
        "features": features,
    }


def build_snapshot(raw: pd.DataFrame, source_receipt: dict[str, Any] | None = None) -> dict[str, Any]:
    required = {
        "season", "match_id", "match_time", "player_key", "team", "assists", "rebounds", "minutes",
        "turnovers", "field_goals_attempted", "rebounds_offensive", "rebounds_defensive",
        "team_points_box", "team_assists_box", "team_rebounds_box", "team_fgm", "team_missed_fg",
        "team_possessions_est", "opp_points_box", "opp_assists_box", "opp_rebounds_box", "opp_fgm",
        "opp_missed_fg", "opp_possessions_est",
    }
    missing = sorted(required - set(raw.columns))
    if missing:
        raise ValueError(f"historical table missing snapshot fields {missing}")
    df = raw.copy()
    df["match_time"] = pd.to_datetime(df["match_time"], errors="coerce", utc=True)
    df = df[df["match_time"].notna() & df["player_key"].notna()].copy()
    if df.empty:
        raise ValueError("historical table has no timestamped player rows")

    players = {
        str(key): player_snapshot(group)
        for key, group in df.groupby("player_key", sort=True)
    }
    team_games = df.drop_duplicates(["season", "match_id", "team"]).copy()
    teams = {
        str(team): team_snapshot(group)
        for team, group in team_games.groupby("team", sort=True)
    }
    source_sha = None
    if source_receipt is not None:
        source_sha = hashlib.sha256(
            json.dumps(source_receipt, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
    core = {
        "schema_version": SCHEMA_VERSION,
        "market_data": False,
        "source_receipt_sha256": source_sha,
        "historical_rows": int(len(df)),
        "historical_matches": int(df[["season", "match_id"]].drop_duplicates().shape[0]),
        "players": players,
        "teams": teams,
        "notes": [
            "Rolling priors include the most recent completed historical game.",
            "player_season_games_prior and team_season_games_prior are set at runtime for the target season.",
            "Projected minutes and current role are never inferred from this snapshot alone.",
        ],
    }
    core["snapshot_revision"] = hashlib.sha256(
        json.dumps(core, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:20]
    return core


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--source-receipt")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    raw = pd.read_csv(args.data, low_memory=False)
    receipt = json.loads(Path(args.source_receipt).read_text()) if args.source_receipt else None
    snapshot = build_snapshot(raw, receipt)
    out = Path(args.output); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({
        "ok": True,
        "snapshot_revision": snapshot["snapshot_revision"],
        "players": len(snapshot["players"]),
        "teams": len(snapshot["teams"]),
        "historical_rows": snapshot["historical_rows"],
        "historical_matches": snapshot["historical_matches"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
