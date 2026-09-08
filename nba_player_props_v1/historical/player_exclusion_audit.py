from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd
import pyreadr

from nba_player_props_v1.historical.source_catalog import core_assets
from nba_player_props_v1.source_receipt import canonical_json, sha256_bytes, sha256_file

NBA_ESPN_TEAMS = {str(i) for i in range(1, 31)}
STAT_FIELDS = (
    "assists", "rebounds", "offensive_rebounds", "defensive_rebounds", "turnovers",
    "field_goals_made", "field_goals_attempted", "three_point_field_goals_made",
    "three_point_field_goals_attempted", "free_throws_made", "free_throws_attempted",
)


def _download(url: str, cache: Path) -> tuple[Path, str, int]:
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / sha256_bytes(url.encode())
    if not path.exists():
        req = Request(url, headers={"User-Agent": "NBA-V1-player-exclusion-audit/1.0", "Accept": "application/octet-stream"})
        with urlopen(req, timeout=120) as response:
            path.write_bytes(response.read())
    return path, sha256_file(path), path.stat().st_size


def _minutes(value) -> float:
    if pd.isna(value):
        return 0.0
    if isinstance(value, str) and ":" in value:
        minutes, seconds = value.split(":", 1)
        return float(minutes) + float(seconds) / 60.0
    return float(value)


def _bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if value in (0, 1):
        return bool(value)
    if isinstance(value, str) and value.lower() in ("true", "false"):
        return value.lower() == "true"
    if pd.isna(value):
        return False
    raise ValueError(f"invalid did_not_play value {value!r}")


def audit_frame(frame: pd.DataFrame, season: int) -> dict:
    required = {"game_id", "season", "season_type", "athlete_id", "athlete_display_name", "team_id", "opponent_team_id", "minutes", "did_not_play", *STAT_FIELDS}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"player source schema missing {missing}")
    data = frame.loc[:, sorted(required)].copy()
    for col in ("game_id", "athlete_id", "team_id", "opponent_team_id"):
        data[col] = data[col].astype("string")
    data = data[data.season_type.isin([2, 3]) & data.team_id.isin(NBA_ESPN_TEAMS) & data.opponent_team_id.isin(NBA_ESPN_TEAMS)].copy()
    data["minutes_parsed"] = data.minutes.map(_minutes)
    data["dnp_parsed"] = data.did_not_play.map(_bool)
    for field in STAT_FIELDS:
        data[field] = pd.to_numeric(data[field], errors="coerce").fillna(0)
    data["box_stat_sum"] = data[list(STAT_FIELDS)].sum(axis=1)
    suspicious = data[(data.box_stat_sum > 0) & (data.dnp_parsed | (data.minutes_parsed <= 0))].copy()
    sample_cols = ["game_id", "athlete_id", "athlete_display_name", "team_id", "opponent_team_id", "minutes", "minutes_parsed", "did_not_play", "dnp_parsed", *STAT_FIELDS]
    return {
        "season": season,
        "franchise_source_rows": int(len(data)),
        "positive_box_rows_excluded_by_minutes_or_dnp": int(len(suspicious)),
        "sample": suspicious.loc[:, sample_cols].head(100).to_dict("records"),
    }


def run(seasons: list[int], cache: str, output: str) -> dict:
    cache_path = Path(cache)
    season_reports, assets = [], []
    for season in sorted(set(seasons)):
        asset = next(a for a in core_assets(season) if a.dataset == "player_box")
        path, digest, size = _download(asset.url, cache_path)
        frame = pyreadr.read_r(str(path))[None]
        season_reports.append(audit_frame(frame, season))
        assets.append({"season": season, "url": asset.url, "sha256": digest, "bytes": size})
    total = sum(r["positive_box_rows_excluded_by_minutes_or_dnp"] for r in season_reports)
    report = {
        "schema_version": "nba_player_exclusion_audit_v1",
        "market_data": False,
        "status": "PASS" if total == 0 else "INVESTIGATE",
        "positive_box_rows_excluded_by_minutes_or_dnp": total,
        "seasons": season_reports,
        "assets": assets,
    }
    report["receipt_sha256"] = sha256_bytes(canonical_json(report))
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_bytes(canonical_json(report) + b"\n")
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seasons", type=int, nargs="+", required=True)
    parser.add_argument("--cache", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = run(args.seasons, args.cache, args.output)
    print(json.dumps(report))


if __name__ == "__main__":
    main()
