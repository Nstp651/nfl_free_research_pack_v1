#!/usr/bin/env python3
"""Operational diagnostic for historical NBL timestamp coverage and ID recovery."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from source_client import RosettaClient  # noqa: E402
from build_player_games import ASSETS, download_csv, first_col, release_asset  # noqa: E402


def audit_frame(label: str, df: pd.DataFrame) -> dict[str, Any]:
    season_col = first_col(df, "season")
    time_col = first_col(df, "match_time_utc", "match_time", "date", "match_date")
    match_col = first_col(df, "match_id")
    external_col = first_col(df, "external_id")
    if not season_col:
        return {"label": label, "season_column": None, "time_column": time_col}
    seasons = sorted(df[season_col].dropna().astype(str).unique().tolist())
    latest = seasons[-1] if seasons else None
    rows = df[df[season_col].astype(str) == latest].copy() if latest else df.iloc[0:0]
    parsed = pd.to_datetime(rows[time_col], errors="coerce", utc=True) if time_col else pd.Series(pd.NaT, index=rows.index)
    sample_cols = [c for c in (match_col, external_col, time_col, first_col(df, "team_name", "name"), first_col(df, "home_team_name"), first_col(df, "away_team_name")) if c]
    return {
        "label": label,
        "season_column": season_col,
        "time_column": time_col,
        "latest_season": latest,
        "latest_rows": int(len(rows)),
        "latest_time_non_null": int(parsed.notna().sum()),
        "latest_time_non_null_rate": float(parsed.notna().mean()) if len(rows) else None,
        "sample": rows[sample_cols].head(5).where(pd.notna(rows[sample_cols].head(5)), None).to_dict(orient="records") if sample_cols else [],
    }


def string_set(series: pd.Series) -> set[str]:
    return {str(x).strip() for x in series.dropna().tolist() if str(x).strip()}


def latest_rows(df: pd.DataFrame) -> pd.DataFrame:
    season_col = first_col(df, "season")
    if not season_col:
        return df.iloc[0:0]
    seasons = sorted(df[season_col].dropna().astype(str).unique().tolist())
    if not seasons:
        return df.iloc[0:0]
    return df[df[season_col].astype(str) == seasons[-1]].copy()


def official_bridge(frames: dict[str, pd.DataFrame]) -> dict[str, Any]:
    schedule = RosettaClient().schedule(2025, "all").data
    official_ids = {str(x.get("id") or "").strip() for x in schedule if str(x.get("id") or "").strip()}
    official_external = {str(x.get("external_id") or "").strip() for x in schedule if str(x.get("external_id") or "").strip()}
    p = latest_rows(frames["player"]); r = latest_rows(frames["results"])
    p_match_col = first_col(p, "match_id"); r_match_col = first_col(r, "match_id"); r_external_col = first_col(r, "external_id")
    p_match = string_set(p[p_match_col]) if p_match_col else set()
    r_match = string_set(r[r_match_col]) if r_match_col else set()
    r_external = string_set(r[r_external_col]) if r_external_col else set()
    sample = [{
        "id": x.get("id"),
        "external_id": x.get("external_id"),
        "start_time": x.get("start_time_datetime") or x.get("start_time"),
        "home": (x.get("home_team") or {}).get("name") if isinstance(x.get("home_team"), dict) else None,
        "away": (x.get("away_team") or {}).get("name") if isinstance(x.get("away_team"), dict) else None,
    } for x in schedule[:5]]
    return {
        "official_2025_rows": len(schedule),
        "official_id_count": len(official_ids),
        "official_external_id_count": len(official_external),
        "player_latest_match_ids": len(p_match),
        "results_latest_match_ids": len(r_match),
        "results_latest_external_ids": len(r_external),
        "player_match_to_official_id": len(p_match & official_ids),
        "player_match_to_official_external_id": len(p_match & official_external),
        "results_match_to_official_id": len(r_match & official_ids),
        "results_match_to_official_external_id": len(r_match & official_external),
        "results_external_to_official_id": len(r_external & official_ids),
        "results_external_to_official_external_id": len(r_external & official_external),
        "official_sample": sample,
    }


def main() -> int:
    reports = []
    frames: dict[str, pd.DataFrame] = {}
    for key, (tag, name) in ASSETS.items():
        frame, _ = download_csv(release_asset(tag, name)); frames[key] = frame
        reports.append(audit_frame(key, frame))
    bridge = official_bridge(frames)
    print("NBL_SOURCE_TIME_DIAGNOSTIC=" + json.dumps({"sources": reports, "official_bridge": bridge}, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
