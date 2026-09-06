#!/usr/bin/env python3
"""Temporary/operational diagnostic for historical NBL timestamp coverage."""
from __future__ import annotations

import json
from typing import Any

import pandas as pd

try:
    from .build_player_games import ASSETS, download_csv, first_col, release_asset
except ImportError:
    from build_player_games import ASSETS, download_csv, first_col, release_asset


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


def main() -> int:
    reports = []
    for key, (tag, name) in ASSETS.items():
        frame, _ = download_csv(release_asset(tag, name))
        reports.append(audit_frame(key, frame))
    print("NBL_SOURCE_TIME_DIAGNOSTIC=" + json.dumps(reports, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
