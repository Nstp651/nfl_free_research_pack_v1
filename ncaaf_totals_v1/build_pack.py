#!/usr/bin/env python3
"""Build a compact, market-blind NCAA Football totals research slate.

Free upstream: sportsdataverse/sportsdataverse-data GitHub release assets.
Hard boundary: a week-W slate can only expose current-season weekly metrics
with through_week <= W-1. No betting/odds datasets are downloaded.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import requests

REPO = "sportsdataverse/sportsdataverse-data"
API = f"https://api.github.com/repos/{REPO}/releases/tags"
UA = "nick-ncaaf-totals-research-pack/0.1.0"
SCHEMA_VERSION = "0.1.0"
SYDNEY = ZoneInfo("Australia/Sydney")

REQUIRED = {
    "schedule": "cfb_schedules",
    "weekly": "cfb_team_summaries_weekly",
    "ratings": "cfb_ratings_weekly",
}
OPTIONAL = {
    "talent": "cfb_team_talent",
    "returning": "cfb_returning_production",
}

# Explicit allow-lists keep the pack compact and make accidental betting-field
# ingestion impossible even if upstream adds market columns later.
SUMMARY_METRICS = [
    "valid_games", "games", "playsgame_off", "playsgame_def",
    "EPAplay_off", "EPAplay_def", "success_off", "success_def",
    "pass_epa_off", "pass_epa_def", "rush_epa_off", "rush_epa_def",
    "pass_success_off", "pass_success_def", "rush_success_off", "rush_success_def",
    "explosive_off", "explosive_def", "havoc_off", "havoc_def",
    "sack_rate_off", "sack_rate_def", "pressure_rate_off", "pressure_rate_def",
    "pass_rate_off", "pass_rate_def", "rush_rate_off", "rush_rate_def",
    "points_drive_off", "points_drive_def", "points_per_drive_off", "points_per_drive_def",
    "drives_game_off", "drives_game_def", "points_off", "points_def",
    "yards_play_off", "yards_play_def", "turnover_rate_off", "turnover_rate_def",
    "finishing_drives_off", "finishing_drives_def", "redzone_td_rate_off", "redzone_td_rate_def",
    "adj_off_epa", "adj_def_epa", "net_adj_epa", "adj_st_epa",
]
RATING_METRICS = [
    "adj_net", "adj_off_epa", "adj_def_epa", "adj_st_epa",
    "fei_net", "fei_off", "fei_def", "fei_st",
    "off_rating", "def_rating", "net_rating",
]
PRESEASON_METRICS = [
    "talent_composite", "blue_chip_ratio", "off_returning",
    "def_returning", "overall_returning",
]
DENY_KEY = re.compile(r"(?:odds|spread|moneyline|betting|sportsbook|bookmaker|over_under|total_line|line_price)", re.I)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, (pd.Timestamp, datetime)):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    if pd.isna(value):
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def norm_id(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    s = str(value).strip()
    if re.fullmatch(r"\d+\.0", s):
        s = s[:-2]
    return s or None


def first_col(df: pd.DataFrame, *names: str) -> str | None:
    for name in names:
        if name in df.columns:
            return name
    return None


def get_release(tag: str) -> dict[str, Any]:
    r = requests.get(f"{API}/{tag}", headers={"user-agent": UA}, timeout=30)
    r.raise_for_status()
    return r.json()


def pick_asset(release: dict[str, Any], season: int) -> dict[str, Any]:
    season_s = str(season)
    assets = [a for a in release.get("assets", []) if season_s in a.get("name", "")]
    # Prefer compressed CSV, then CSV. We intentionally avoid binary parquet in
    # the build environment so no pyarrow dependency is required.
    def score(a: dict[str, Any]) -> tuple[int, int]:
        n = a.get("name", "").lower()
        if n.endswith(".csv.gz"):
            ext = 0
        elif n.endswith(".csv"):
            ext = 1
        else:
            ext = 9
        return (ext, len(n))
    assets = sorted(assets, key=score)
    for asset in assets:
        n = asset.get("name", "").lower()
        if n.endswith(".csv.gz") or n.endswith(".csv"):
            return asset
    raise FileNotFoundError(f"No CSV release asset for {release.get('tag_name')} season {season}")


def download_asset(tag: str, season: int) -> tuple[pd.DataFrame, dict[str, Any]]:
    release = get_release(tag)
    asset = pick_asset(release, season)
    url = asset["browser_download_url"]
    r = requests.get(url, headers={"user-agent": UA}, timeout=90)
    r.raise_for_status()
    raw = r.content
    sha = hashlib.sha256(raw).hexdigest()
    compression = "gzip" if asset["name"].lower().endswith(".gz") else None
    df = pd.read_csv(io.BytesIO(raw), compression=compression, low_memory=False)
    receipt = {
        "tag": tag,
        "asset": asset["name"],
        "url": url,
        "sha256": sha,
        "bytes": len(raw),
        "asset_updated_at": asset.get("updated_at"),
        "release_updated_at": release.get("updated_at"),
    }
    return df, receipt


def to_bool(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    return series.astype(str).str.lower().isin({"true", "1", "yes", "y"})


def parse_utc(value: Any) -> datetime | None:
    if value is None or pd.isna(value):
        return None
    try:
        ts = pd.to_datetime(value, utc=True)
        return ts.to_pydatetime()
    except Exception:
        return None


def choose_week(schedule: pd.DataFrame, season: int, explicit: str) -> int:
    if explicit != "auto":
        return int(explicit)
    week_col = first_col(schedule, "week")
    start_col = first_col(schedule, "start_date", "date_time", "game_date")
    if not week_col or not start_col:
        raise ValueError("Schedule cannot auto-resolve week: missing week/start_date")
    now = utc_now()
    candidates: list[int] = []
    for _, row in schedule.iterrows():
        start = parse_utc(row.get(start_col))
        if start is None or start < now:
            continue
        try:
            candidates.append(int(row.get(week_col)))
        except Exception:
            continue
    if not candidates:
        raise ValueError("No future target week found in schedule")
    return min(candidates)


def fbs_week(schedule: pd.DataFrame, season: int, week: int) -> pd.DataFrame:
    out = schedule.copy()
    if "season" in out.columns:
        out = out[pd.to_numeric(out["season"], errors="coerce") == season]
    out = out[pd.to_numeric(out["week"], errors="coerce") == week]
    if "fbs_game" not in out.columns:
        raise ValueError("Schedule missing required fbs_game flag")
    out = out[to_bool(out["fbs_game"])]
    if "season_type" in out.columns:
        allowed = {"regular", "postseason", "spring_regular", "spring_postseason"}
        out = out[out["season_type"].astype(str).str.lower().isin(allowed)]
    game_id = first_col(out, "game_id", "id")
    if not game_id:
        raise ValueError("Schedule missing game_id")
    if out[game_id].astype(str).duplicated().any():
        raise ValueError("Duplicate game_id in target slate")
    return out.sort_values(first_col(out, "start_date", "date_time", "game_date") or game_id)


def metric_dict(row: pd.Series | None, allow: list[str]) -> dict[str, Any]:
    if row is None:
        return {}
    return {k: jsonable(row[k]) for k in allow if k in row.index and jsonable(row[k]) is not None}


def latest_rows(df: pd.DataFrame, season: int, cutoff_week: int | None) -> tuple[dict[str, pd.Series], int | None]:
    if df.empty:
        return {}, None
    season_col = first_col(df, "season")
    week_col = first_col(df, "through_week", "week")
    team_col = first_col(df, "team_id", "pos_team_id", "id")
    if not team_col:
        raise ValueError("Team-week source missing team_id")
    work = df.copy()
    if season_col:
        work = work[pd.to_numeric(work[season_col], errors="coerce") == season]
    max_week: int | None = None
    if cutoff_week is not None:
        if not week_col:
            raise ValueError("Current weekly source missing through_week")
        w = pd.to_numeric(work[week_col], errors="coerce")
        work = work[w <= cutoff_week]
        if not work.empty:
            max_week = int(pd.to_numeric(work[week_col], errors="coerce").max())
    elif week_col and not work.empty:
        max_week = int(pd.to_numeric(work[week_col], errors="coerce").max())
        work = work[pd.to_numeric(work[week_col], errors="coerce") == max_week]
    if week_col and not work.empty:
        work = work.sort_values(week_col).groupby(work[team_col].map(norm_id), dropna=True).tail(1)
    result: dict[str, pd.Series] = {}
    for _, row in work.iterrows():
        tid = norm_id(row.get(team_col))
        if tid:
            result[tid] = row
    return result, max_week


def season_rows(df: pd.DataFrame, season: int) -> dict[str, pd.Series]:
    if df.empty:
        return {}
    team_col = first_col(df, "team_id", "id")
    if not team_col:
        return {}
    work = df.copy()
    if "season" in work.columns:
        work = work[pd.to_numeric(work["season"], errors="coerce") == season]
    out: dict[str, pd.Series] = {}
    for _, row in work.iterrows():
        tid = norm_id(row.get(team_col))
        if tid:
            out[tid] = row
    return out


def team_name(row: pd.Series | None, fallback: Any) -> str | None:
    if row is not None:
        for c in ("pos_team", "team", "school", "team_name"):
            if c in row.index and not pd.isna(row[c]):
                return str(row[c])
    return None if fallback is None or pd.isna(fallback) else str(fallback)


def profile(team_id: str | None, name: str | None, current_summary: dict[str, pd.Series],
            current_ratings: dict[str, pd.Series], prior_summary: dict[str, pd.Series],
            prior_ratings: dict[str, pd.Series], talent: dict[str, pd.Series],
            returning: dict[str, pd.Series]) -> dict[str, Any]:
    cs = current_summary.get(team_id or "")
    cr = current_ratings.get(team_id or "")
    ps = prior_summary.get(team_id or "")
    pr = prior_ratings.get(team_id or "")
    tr = talent.get(team_id or "")
    rr = returning.get(team_id or "")
    return {
        "team_id": team_id,
        "team_name": team_name(cs or ps, name),
        "current": {
            "available": cs is not None or cr is not None,
            "summary": metric_dict(cs, SUMMARY_METRICS),
            "ratings": metric_dict(cr, RATING_METRICS),
        },
        "prior_season": {
            "available": ps is not None or pr is not None,
            "summary": metric_dict(ps, SUMMARY_METRICS),
            "ratings": metric_dict(pr, RATING_METRICS),
        },
        "preseason": {
            "talent": metric_dict(tr, PRESEASON_METRICS),
            "returning_production": metric_dict(rr, PRESEASON_METRICS),
        },
    }


def market_key_audit(value: Any, path: str = "root") -> list[str]:
    hits: list[str] = []
    if isinstance(value, dict):
        for k, v in value.items():
            if DENY_KEY.search(str(k)):
                hits.append(f"{path}.{k}")
            hits.extend(market_key_audit(v, f"{path}.{k}"))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            hits.extend(market_key_audit(v, f"{path}[{i}]"))
    return hits


def corr_guard(current: dict[str, pd.Series]) -> dict[str, Any]:
    pairs = (("adj_off_epa", "EPAplay_off"), ("adj_def_epa", "EPAplay_def"))
    out: dict[str, Any] = {"status": "NOT_TESTED", "tests": []}
    suspicious = False
    tested = False
    for adjusted, raw in pairs:
        rows = []
        for r in current.values():
            if adjusted in r.index and raw in r.index:
                a, b = jsonable(r[adjusted]), jsonable(r[raw])
                if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                    rows.append((float(a), float(b)))
        if len(rows) >= 25:
            tested = True
            c = pd.Series([x[0] for x in rows]).corr(pd.Series([x[1] for x in rows]))
            c = float(c) if c is not None and not math.isnan(c) else None
            flag = c is not None and abs(c) >= 0.98
            suspicious = suspicious or flag
            out["tests"].append({"adjusted": adjusted, "raw": raw, "n": len(rows), "correlation": c, "suspicious": flag})
    out["status"] = "SUSPICIOUS" if suspicious else ("PASS" if tested else "NOT_TESTED")
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--season", type=int, default=utc_now().year)
    p.add_argument("--week", default="auto", help="integer NCAA week or auto")
    p.add_argument("--output", default="ncaaf_totals_v1/data")
    args = p.parse_args()

    receipts: dict[str, Any] = {}
    tables: dict[str, pd.DataFrame] = {}
    failures: list[str] = []
    limitations: list[str] = []

    # Schedule must be loaded first so auto-week can resolve.
    schedule, receipts["schedule"] = download_asset(REQUIRED["schedule"], args.season)
    week = choose_week(schedule, args.season, args.week)
    games_df = fbs_week(schedule, args.season, week)
    if games_df.empty:
        raise SystemExit(f"No FBS-v-FBS fixtures found for {args.season} week {week}")

    for key in ("weekly", "ratings"):
        tag = REQUIRED[key]
        try:
            tables[key], receipts[key] = download_asset(tag, args.season)
        except Exception as e:
            failures.append(f"{tag}: {e}")
            tables[key] = pd.DataFrame()

    prior_season = args.season - 1
    for key in ("weekly", "ratings"):
        tag = REQUIRED[key]
        try:
            tables[f"prior_{key}"], receipts[f"prior_{key}"] = download_asset(tag, prior_season)
        except Exception as e:
            failures.append(f"prior {tag}: {e}")
            tables[f"prior_{key}"] = pd.DataFrame()

    for key, tag in OPTIONAL.items():
        try:
            tables[key], receipts[key] = download_asset(tag, args.season)
        except Exception as e:
            limitations.append(f"Optional {tag} unavailable for {args.season}: {e}")
            tables[key] = pd.DataFrame()

    if failures:
        raise SystemExit("Required NCAA source failure(s): " + " | ".join(failures))

    cutoff = week - 1
    if cutoff >= 0:
        cur_summary, summary_through = latest_rows(tables["weekly"], args.season, cutoff)
        cur_ratings, ratings_through = latest_rows(tables["ratings"], args.season, cutoff)
    else:
        cur_summary, summary_through, cur_ratings, ratings_through = {}, None, {}, None
    prior_summary, prior_summary_week = latest_rows(tables["prior_weekly"], prior_season, None)
    prior_ratings, prior_ratings_week = latest_rows(tables["prior_ratings"], prior_season, None)
    talent = season_rows(tables["talent"], args.season)
    returning = season_rows(tables["returning"], args.season)

    if summary_through is not None and summary_through > cutoff:
        raise SystemExit(f"Leakage gate failed: summaries through {summary_through}, cutoff {cutoff}")
    if ratings_through is not None and ratings_through > cutoff:
        raise SystemExit(f"Leakage gate failed: ratings through {ratings_through}, cutoff {cutoff}")
    if week > 1 and not cur_summary:
        limitations.append("No current-season weekly summaries were available at the W-1 cutoff.")
    if week > 1 and not cur_ratings:
        limitations.append("No current-season weekly ratings were available at the W-1 cutoff.")

    h_id = first_col(games_df, "home_id")
    a_id = first_col(games_df, "away_id")
    h_team = first_col(games_df, "home_team")
    a_team = first_col(games_df, "away_team")
    gid_col = first_col(games_df, "game_id", "id")
    start_col = first_col(games_df, "start_date", "date_time", "game_date")
    if not all((h_id, a_id, h_team, a_team, gid_col, start_col)):
        raise SystemExit("Schedule schema missing required fixture fields")

    games: list[dict[str, Any]] = []
    for _, row in games_df.iterrows():
        start = parse_utc(row[start_col])
        hid, aid = norm_id(row[h_id]), norm_id(row[a_id])
        game = {
            "game_id": norm_id(row[gid_col]),
            "fixture": {
                "season": args.season,
                "week": week,
                "season_type": jsonable(row.get("season_type")),
                "away_team": jsonable(row[a_team]),
                "away_id": aid,
                "home_team": jsonable(row[h_team]),
                "home_id": hid,
                "neutral_site": jsonable(row.get("neutral_site")),
                "venue": jsonable(row.get("venue")),
                "start_utc": start.isoformat() if start else jsonable(row[start_col]),
                "start_australia_sydney": start.astimezone(SYDNEY).isoformat() if start else None,
                "sydney_date": start.astimezone(SYDNEY).date().isoformat() if start else None,
                "completed": jsonable(row.get("completed")),
                "fbs_game": True,
            },
            "home_profile": profile(hid, jsonable(row[h_team]), cur_summary, cur_ratings,
                                    prior_summary, prior_ratings, talent, returning),
            "away_profile": profile(aid, jsonable(row[a_team]), cur_summary, cur_ratings,
                                    prior_summary, prior_ratings, talent, returning),
        }
        games.append(game)

    quality = corr_guard(cur_summary)
    if quality["status"] == "SUSPICIOUS":
        limitations.append("Opponent-adjusted EPA sanity guard is suspicious; affected adjusted fields require live/alternative verification.")

    slate_id = f"{args.season}_{week:02d}"
    revision_basis = {
        "schema_version": SCHEMA_VERSION,
        "season": args.season,
        "week": week,
        "cutoff": cutoff,
        "source_hashes": {k: v["sha256"] for k, v in receipts.items()},
        "game_ids": [g["game_id"] for g in games],
    }
    pack_revision = hashlib.sha256(json.dumps(revision_basis, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]
    generated = utc_now().isoformat()
    through_values = [v for v in (summary_through, ratings_through) if v is not None]
    current_through = max(through_values) if through_values else None
    source_status = "PARTIAL" if limitations else "PASS"

    pack: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "slate_id": slate_id,
        "pack_revision": pack_revision,
        "season": args.season,
        "week": week,
        "market_data": False,
        "generated_at_utc": generated,
        "last_checked_at_utc": generated,
        "data_state": {
            "current_season_data_through_week": current_through,
            "required_max_through_week": cutoff,
            "prior_season": prior_season,
            "prior_summary_final_through_week": prior_summary_week,
            "prior_ratings_final_through_week": prior_ratings_week,
        },
        "source_health": {"status": source_status, "failed_required": [], "quality": quality},
        "source_receipt": receipts,
        "limitations": limitations,
        "games": games,
    }
    market_hits = market_key_audit(pack)
    if market_hits:
        raise SystemExit("Market boundary violation in generated pack: " + ", ".join(market_hits[:20]))

    out = Path(args.output)
    slate_dir = out / "slates" / str(args.season)
    slate_dir.mkdir(parents=True, exist_ok=True)
    (slate_dir / f"{slate_id}.json").write_text(json.dumps(pack, indent=2, sort_keys=True), encoding="utf-8")

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "market_data": False,
        "generated_at_utc": generated,
        "last_checked_at_utc": generated,
        "fixture_count": len(games),
        "source_health": pack["source_health"],
        "attribution": {
            "provider": "sportsdataverse / cfbfastR public release data",
            "repository": f"https://github.com/{REPO}",
            "purpose": "pre-market NCAA football research only",
        },
        "limitations": limitations,
        "slates": [{
            "slate_id": slate_id,
            "season": args.season,
            "week": week,
            "pack_revision": pack_revision,
            "game_count": len(games),
            "current_season_data_through_week": current_through,
        }],
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({
        "ok": True, "slate_id": slate_id, "pack_revision": pack_revision,
        "games": len(games), "current_through_week": current_through,
        "source_health": source_status, "limitations": limitations,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
