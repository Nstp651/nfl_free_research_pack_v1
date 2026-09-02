#!/usr/bin/env python3
"""
NFL Free Research Pack V1

Builds pre-market NFL receptions research packs from free nflverse data.

Data used:
- nflverse play-by-play / player stats / team stats
- nflverse-FTN charting (free subset; CC-BY-SA 4.0; attribution required)
- NFL Next Gen Stats via nflverse
- PFR snap counts / advanced receiving via nflverse
- current nflverse rosters and depth charts
- nflverse schedule

Important model-safety rules:
- This service contains NO sportsbook prices, lines, market consensus or betting projections.
- True in-season route participation is NOT claimed.
- Snap share is exposed only as a route-opportunity proxy and is explicitly labelled PROXY.
- nflverse injury data is not relied on.
- Current role/injury/practice/preseason interpretation still belongs in live Layer-1 research.
"""

from __future__ import annotations

import argparse
import json
import math
import hashlib
import os
import sys
import traceback
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

import numpy as np
import pandas as pd

SKILL_POSITIONS = {"WR", "TE", "RB", "FB"}
DEFAULT_HISTORY_SEASONS = 2
BUILD_VERSION = "1.1.1"
FTN_READ_CODES = {"0": "primary_read", "1": "second_read", "2": "third_or_later",
                  "CHK": "checkdown", "DES": "designed_read", "SD": "scramble_drill"}
FTN_DICTIONARY = "https://nflreadr.nflverse.com/articles/dictionary_ftn_charting.html"


def log(msg: str) -> None:
    print(f"[nfl-pack] {msg}", flush=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def as_pd(obj: Any) -> pd.DataFrame:
    if obj is None:
        return pd.DataFrame()
    if isinstance(obj, pd.DataFrame):
        return obj.copy()
    if hasattr(obj, "to_pandas"):
        return obj.to_pandas()
    return pd.DataFrame(obj)


def safe_load(label: str, fn: Callable, *args, retries: int = 3, **kwargs) -> pd.DataFrame:
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            log(f"loading {label} (attempt {attempt}/{retries})")
            df = as_pd(fn(*args, **kwargs))
            log(f"{label}: {len(df):,} rows")
            return df
        except Exception as exc:
            last_exc = exc
            log(f"WARNING {label} attempt {attempt} failed: {exc}")
            if attempt < retries:
                time.sleep(2 * attempt)
    log(f"WARNING {label} unavailable after {retries} attempts: {last_exc}")
    return pd.DataFrame()


def safe_num(v: Any, digits: int = 4) -> float | int | None:
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except Exception:
        pass
    try:
        f = float(v)
    except Exception:
        return None
    if not math.isfinite(f):
        return None
    if abs(f - round(f)) < 1e-12:
        return int(round(f))
    return round(f, digits)


def safe_str(v: Any) -> str | None:
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except Exception:
        pass
    s = str(v).strip()
    return s or None


def first_existing(df: pd.DataFrame, names: Iterable[str]) -> str | None:
    cols = set(df.columns)
    for n in names:
        if n in cols:
            return n
    return None


def bool_series(s: pd.Series) -> pd.Series:
    # Unknown observations must not count as false in charting rates.
    mapping = {"1": True, "1.0": True, "true": True, "t": True, "yes": True,
               "y": True, "0": False, "0.0": False, "false": False,
               "f": False, "no": False, "n": False}
    return s.astype("string").str.strip().str.lower().map(mapping).astype("boolean")


def numeric(df: pd.DataFrame, name: str) -> pd.Series:
    return pd.to_numeric(df.get(name, pd.Series(np.nan, index=df.index)), errors="coerce")


def total(df: pd.DataFrame, name: str) -> float:
    return numeric(df, name).sum(min_count=1)


def ratio(numerator: Any, denominator: Any) -> float | int | None:
    n, d = safe_num(numerator), safe_num(denominator)
    return safe_num(n / d) if n is not None and d is not None and d > 0 else None


def records_clean(df: pd.DataFrame) -> list[dict[str, Any]]:
    if df.empty:
        return []
    out = []
    for row in df.to_dict(orient="records"):
        clean = {}
        for k, v in row.items():
            if isinstance(v, (np.integer,)):
                clean[k] = int(v)
            elif isinstance(v, (np.floating,)):
                clean[k] = safe_num(v)
            elif isinstance(v, pd.Timestamp):
                clean[k] = v.isoformat()
            else:
                try:
                    if pd.isna(v):
                        clean[k] = None
                    else:
                        clean[k] = v
                except Exception:
                    clean[k] = v
        out.append(clean)
    return out


def filter_regular(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    for col in ("season_type", "game_type"):
        if col in df.columns:
            df = df[df[col].astype(str) == "REG"]
    return df.copy()


def prior_seasons(season: int, n: int = DEFAULT_HISTORY_SEASONS) -> list[int]:
    return list(range(season - n, season))


def load_inputs(season: int, history_n: int) -> dict[str, Any]:
    import nflreadpy as nfl
    years = prior_seasons(season, history_n) + [season]
    d: dict[str, Any] = {"years": years, "season": season}

    d["schedule"] = safe_load("schedule", nfl.load_schedules, season)
    d["current_roster"] = safe_load("current roster", nfl.load_rosters, season)
    d["current_depth"] = safe_load("current depth charts", nfl.load_depth_charts, season)
    d["players"] = safe_load("players", nfl.load_players)

    d["player_stats"] = {}
    d["team_stats"] = {}
    d["pbp"] = {}
    d["ftn"] = {}
    d["snap"] = {}
    d["pfr_rec"] = {}

    for y in years:
        d["player_stats"][y] = filter_regular(
            safe_load(f"player stats {y}", nfl.load_player_stats, y, summary_level="week")
        )
        d["team_stats"][y] = filter_regular(
            safe_load(f"team stats {y}", nfl.load_team_stats, y, summary_level="week")
        )
        d["pbp"][y] = filter_regular(safe_load(f"pbp {y}", nfl.load_pbp, y))
        d["ftn"][y] = safe_load(f"FTN charting {y}", nfl.load_ftn_charting, y)
        d["snap"][y] = filter_regular(safe_load(f"snap counts {y}", nfl.load_snap_counts, y))
        d["pfr_rec"][y] = filter_regular(
            safe_load(
                f"PFR advanced receiving {y}",
                nfl.load_pfr_advstats,
                y,
                stat_type="rec",
                summary_level="week",
            )
        )

    # Load NGS one season at a time. This is important before Week 1: nflreadpy
    # 0.1.5's current-season validator still flips on the traditional Thursday,
    # so a combined [prior years + current year] request can fail wholesale.
    # Per-season loading preserves 2024/2025 history even if 2026 NGS is not yet valid.
    d["ngs_receiving"] = {}
    for y in years:
        d["ngs_receiving"][y] = filter_regular(
            safe_load(f"NGS receiving {y}", nfl.load_nextgen_stats, y, stat_type="receiving")
        )

    # Previous-season roster is useful for PFR<->GSIS ID mapping and team-change flags.
    d["prior_rosters"] = {
        y: safe_load(f"roster {y}", nfl.load_rosters, y)
        for y in prior_seasons(season, history_n)
    }
    return d


def latest_depth(depth: pd.DataFrame) -> pd.DataFrame:
    if depth.empty:
        return depth
    d = depth.copy()
    if "team" in d.columns and "dt" in d.columns:
        d["_dt"] = pd.to_datetime(d["dt"], errors="coerce", utc=True)
        max_dt = d.groupby("team")["_dt"].transform("max")
        return d[d["_dt"] == max_dt].drop(columns=["_dt"], errors="ignore")
    # Legacy fallback
    if "week" in d.columns:
        max_week = d["week"].max()
        return d[d["week"] == max_week].copy()
    return d


def roster_skill_players(roster: pd.DataFrame, depth: pd.DataFrame) -> pd.DataFrame:
    if roster.empty:
        return pd.DataFrame()

    r = roster.copy()
    # Exclude clearly released/retired roster-history rows so the GPT is not flooded
    # with dead candidates. Keep reserve/PUP/practice-squad/suspended players because
    # they may still matter to availability/redistribution research.
    if "status" in r.columns:
        dead_status = {"CUT", "UFA", "RET", "TRC", "TRD", "TRT", "NWT", "RSR"}
        r = r[~r["status"].astype(str).isin(dead_status)].copy()
    pos_col = first_existing(r, ["position", "depth_chart_position"])
    if pos_col:
        r = r[r[pos_col].astype(str).isin(SKILL_POSITIONS)].copy()

    # Current roster may occasionally contain duplicates; prefer one row per GSIS ID/name.
    key = first_existing(r, ["gsis_id", "full_name"])
    if key:
        known = r[r[key].notna()].drop_duplicates(subset=[key], keep="last")
        r = pd.concat([known, r[r[key].isna()]], ignore_index=True)

    d = latest_depth(depth)
    if not d.empty:
        join_key = None
        if "gsis_id" in r.columns and "gsis_id" in d.columns:
            join_key = "gsis_id"
        elif "full_name" in r.columns and "player_name" in d.columns:
            d = d.rename(columns={"player_name": "full_name"})
            join_key = "full_name"

        if join_key and "team" in r.columns and "team" in d.columns:
            join_keys = [join_key, "team"]
            keep = [
                c for c in [
                    join_key, "team", "pos_grp", "pos_name", "pos_abb", "pos_slot",
                    "pos_rank", "dt"
                ] if c in d.columns
            ]
            d2 = d[keep].dropna(subset=join_keys).drop_duplicates(subset=join_keys, keep="last")
            r = r.merge(d2, on=join_keys, how="left")

    return r


def weekly_receiver_rows(stats: pd.DataFrame) -> pd.DataFrame:
    if stats.empty:
        return stats
    s = stats.copy()
    if "targets" not in s.columns:
        return pd.DataFrame()
    pos = first_existing(s, ["position_group", "position"])
    if pos:
        s = s[(s[pos].astype(str).isin(SKILL_POSITIONS)) | (s["targets"].fillna(0) > 0)]
    else:
        s = s[s["targets"].fillna(0) > 0]
    return s


def weighted_mean(values: pd.Series, weights: pd.Series | None = None) -> float | None:
    v = pd.to_numeric(values, errors="coerce")
    mask = v.notna()
    if weights is None:
        return safe_num(v[mask].mean())
    w = pd.to_numeric(weights, errors="coerce").fillna(0)
    mask = mask & w.notna() & (w > 0)
    if not mask.any():
        return None
    if float(w[mask].sum()) <= 0:
        return None
    return safe_num(np.average(v[mask], weights=w[mask]))


def aggregate_receiver_window(stats: pd.DataFrame, last_n_games: int | None = None) -> dict[str, dict]:
    s = weekly_receiver_rows(stats)
    if s.empty:
        return {}

    id_col = first_existing(s, ["player_id", "gsis_id"])
    name_col = first_existing(s, ["player_display_name", "player_name"])
    if not id_col:
        return {}

    s = s.sort_values([id_col, "week"] if "week" in s.columns else [id_col]).copy()

    result: dict[str, dict] = {}
    for pid, g in s.groupby(id_col, dropna=True):
        if last_n_games:
            # One weekly row per player is normal. Use rows, not simply week numbers,
            # so bye weeks do not distort "last 3/5 games".
            g = g.tail(last_n_games)

        targets = total(g, "targets")
        rec = total(g, "receptions")
        games = g["game_id"].nunique() if "game_id" in g.columns else g["week"].nunique()
        games = int(games) if games else int(len(g))

        air = total(g, "receiving_air_yards")
        rec_yards = total(g, "receiving_yards")
        yac = total(g, "receiving_yards_after_catch")

        if "target_share" in g.columns:
            tshare = weighted_mean(g["target_share"])
        else:
            tshare = None

        teams = sorted({str(x) for x in g.get("team", pd.Series(dtype=str)).dropna().unique()})
        positions = sorted({
            str(x) for x in g.get(
                first_existing(g, ["position", "position_group"]) or "_missing",
                pd.Series(dtype=str)
            ).dropna().unique()
        })

        out = {
            "player_id": str(pid),
            "player_name": safe_str(g[name_col].dropna().iloc[-1]) if name_col and g[name_col].notna().any() else None,
            "source_teams": teams,
            "positions": positions,
            "games": games,
            "targets": safe_num(targets),
            "receptions": safe_num(rec),
            "targets_per_game": safe_num(targets / games) if games else None,
            "receptions_per_game": safe_num(rec / games) if games else None,
            "catch_rate": safe_num(rec / targets) if targets else None,
            "target_share": tshare,
            "target_share_method": "mean of observed weekly shares; not aggregate season share",
            "receiving_yards": safe_num(rec_yards),
            "receiving_air_yards": safe_num(air),
            "adot": safe_num(air / targets) if targets else None,
            "yac_per_reception": safe_num(yac / rec) if rec else None,
        }

        if "receiving_epa" in g.columns:
            epa = pd.to_numeric(g["receiving_epa"], errors="coerce").fillna(0).sum()
            out["receiving_epa_per_target"] = safe_num(epa / targets) if targets else None

        if "air_yards_share" in g.columns:
            out["air_yards_share"] = weighted_mean(g["air_yards_share"])
        if "wopr" in g.columns:
            out["wopr"] = weighted_mean(g["wopr"])

        result[str(pid)] = out
    return result


def aggregate_team_stats(team_stats: pd.DataFrame) -> dict[str, dict]:
    if team_stats.empty or "team" not in team_stats.columns:
        return {}
    out = {}
    for team, g in team_stats.groupby("team"):
        games = g["game_id"].nunique() if "game_id" in g.columns else g["week"].nunique()
        games = int(games) if games else len(g)
        attempts = total(g, "attempts")
        comps = total(g, "completions")
        sacks = total(g, "sacks_suffered")
        out[str(team)] = {
            "games": games,
            "pass_attempts_per_game": safe_num(attempts / games) if games else None,
            "completions_per_game": safe_num(comps / games) if games else None,
            "dropbacks_per_game_proxy": safe_num((attempts + sacks) / games) if games else None,
            "completion_rate": safe_num(comps / attempts) if attempts else None,
            "sacks_suffered_per_game": safe_num(sacks / games) if games else None,
        }
    return out


def aggregate_team_pbp(pbp: pd.DataFrame) -> dict[str, dict]:
    if pbp.empty or "posteam" not in pbp.columns:
        return {}
    p = pbp.copy()
    if "no_play" in p.columns:
        p = p[numeric(p, "no_play") == 0]
    if "two_point_attempt" in p.columns:
        p = p[numeric(p, "two_point_attempt") == 0]
    if "play_type" in p.columns:
        plays = p[p["play_type"].isin(["pass", "run"])].copy()
    else:
        plays = p.copy()

    out = {}
    for team, g in plays.groupby("posteam"):
        game_col = "game_id" if "game_id" in g.columns else None
        games = g[game_col].nunique() if game_col else None
        if not games:
            games = max(int(g["week"].nunique()) if "week" in g.columns else 1, 1)

        pass_plays = (g["play_type"] == "pass").sum() if "play_type" in g.columns else None
        total_plays = len(g)

        neutral = g
        if "qtr" in neutral.columns:
            neutral = neutral[pd.to_numeric(neutral["qtr"], errors="coerce") <= 3]
        if "score_differential" in neutral.columns:
            sd = pd.to_numeric(neutral["score_differential"], errors="coerce")
            neutral = neutral[sd.abs() <= 7]
        if "down" in neutral.columns:
            neutral = neutral[neutral["down"].notna()]

        n_pass = (neutral["play_type"] == "pass").sum() if "play_type" in neutral.columns else None
        n_total = len(neutral)

        if "receiver_player_id" in p.columns:
            target_rows = p[(p["posteam"] == team) & p["receiver_player_id"].notna()]
            targetable = len(target_rows)
            avg_air = safe_num(numeric(target_rows, "air_yards").mean()) if len(target_rows) else None
        else:
            targetable = None
            avg_air = None

        no_huddle_rate = None
        if "no_huddle" in g.columns:
            no_huddle_rate = safe_num(pd.to_numeric(g["no_huddle"], errors="coerce").fillna(0).mean())

        out[str(team)] = {
            "games": games,
            "offensive_plays_per_game": safe_num(total_plays / games),
            "raw_pass_play_rate": safe_num(pass_plays / total_plays) if pass_plays is not None and total_plays else None,
            "neutral_pass_rate_proxy": safe_num(n_pass / n_total) if n_pass is not None and n_total else None,
            "targetable_passes_per_game": safe_num(targetable / games) if targetable is not None else None,
            "average_target_air_yards": avg_air,
            "no_huddle_rate": no_huddle_rate,
            "neutral_pass_rate_definition": "Q1-Q3, score differential within +/-7, pass vs run play; descriptive proxy, NOT PROE",
        }
    return out


def merge_team_metrics(team_stats: pd.DataFrame, pbp: pd.DataFrame) -> dict[str, dict]:
    a = aggregate_team_stats(team_stats)
    b = aggregate_team_pbp(pbp)
    teams = sorted(set(a) | set(b))
    return {t: {**a.get(t, {}), **b.get(t, {})} for t in teams}


def build_id_map(rosters: list[pd.DataFrame], players: pd.DataFrame) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for df in rosters:
        if df.empty:
            continue
        if "pfr_id" in df.columns and "gsis_id" in df.columns:
            for _, r in df[["pfr_id", "gsis_id"]].dropna().drop_duplicates().iterrows():
                mapping[str(r["pfr_id"])] = str(r["gsis_id"])
    if not players.empty and "pfr_id" in players.columns and "gsis_id" in players.columns:
        for _, r in players[["pfr_id", "gsis_id"]].dropna().drop_duplicates().iterrows():
            mapping[str(r["pfr_id"])] = str(r["gsis_id"])
    return mapping


def aggregate_snap(snap: pd.DataFrame, pfr_to_gsis: dict[str, str], last_n_games: int | None = None) -> dict[str, dict]:
    if snap.empty:
        return {}
    pfr_col = first_existing(snap, ["pfr_player_id", "pfr_id"])
    if not pfr_col:
        return {}
    s = snap.copy()
    if "week" in s.columns:
        s = s.sort_values([pfr_col, "week"])
    out = {}
    for pfr, g in s.groupby(pfr_col, dropna=True):
        if last_n_games:
            g = g.tail(last_n_games)
        gsis = pfr_to_gsis.get(str(pfr))
        if not gsis:
            continue
        games = g["game_id"].nunique() if "game_id" in g.columns else len(g)
        snaps = total(g, "offense_snaps")
        pct = weighted_mean(g["offense_pct"]) if "offense_pct" in g.columns else None
        out[gsis] = {
            "games": int(games),
            "offense_snaps": safe_num(snaps),
            "offense_snap_pct": pct,
            "aggregation": "mean of observed weekly offense_pct; not a routes measure",
            "route_opportunity_status": "PROXY ONLY — snap share is not route participation",
        }
    return out


def ftn_receiver_metrics(ftn: pd.DataFrame, pbp: pd.DataFrame) -> tuple[dict[str, dict], list[str]]:
    if ftn.empty or pbp.empty:
        return {}, []

    need_pbp = [c for c in [
        "game_id", "play_id", "receiver_player_id", "receiver_player_name",
        "posteam", "complete_pass", "air_yards"
    ] if c in pbp.columns]
    if not {"game_id", "play_id", "receiver_player_id"}.issubset(set(need_pbp)):
        return {}, []

    f = ftn.copy()
    join_right_game = "nflverse_game_id"
    join_right_play = "nflverse_play_id"
    if join_right_game not in f.columns or join_right_play not in f.columns:
        return {}, []

    eligible = filter_regular(pbp)
    for flag in ("no_play", "two_point_attempt"):
        if flag in eligible.columns:
            eligible = eligible[numeric(eligible, flag) == 0]
    if "pass_attempt" in eligible.columns:
        eligible = eligible[numeric(eligible, "pass_attempt") == 1]
    if f.duplicated([join_right_game, join_right_play]).any():
        raise ValueError("Duplicate FTN game/play IDs; refusing a many-to-many charting join")
    merged = eligible[need_pbp].merge(
        f,
        left_on=["game_id", "play_id"],
        right_on=[join_right_game, join_right_play],
        how="inner",
        suffixes=("", "_ftn"),
        validate="one_to_one",
    )
    merged = merged[merged["receiver_player_id"].notna()].copy()
    if merged.empty:
        return {}, []

    read_values = []
    if "read_thrown" in merged.columns:
        read_values = sorted({str(x) for x in merged["read_thrown"].dropna().unique()})

    out = {}
    bool_cols = [
        "is_catchable_ball", "is_contested_ball", "is_created_reception", "is_drop",
        "is_screen_pass", "is_play_action", "is_rpo", "is_motion",
        "is_qb_out_of_pocket"
    ]

    for pid, g in merged.groupby("receiver_player_id"):
        n = len(g)
        row = {
            "charted_targets": n,
            "attribution": "FTN Data via nflverse (CC-BY-SA 4.0)",
        }
        for c in bool_cols:
            if c in g.columns:
                observed = bool_series(g[c])
                row[c.replace("is_", "") + "_rate"] = safe_num(observed.mean())
                row[c.replace("is_", "") + "_observed_targets"] = int(observed.notna().sum())

        if "is_catchable_ball" in g.columns and "is_drop" in g.columns:
            catchable = bool_series(g["is_catchable_ball"])
            drops = bool_series(g["is_drop"])
            denom = int((catchable.fillna(False) & drops.notna()).sum())
            row["drop_rate_per_catchable_target"] = safe_num(int((drops & catchable).sum()) / denom) if denom else None
        if "is_catchable_ball" in g.columns and "complete_pass" in g.columns:
            catches = numeric(g, "complete_pass")
            observed = bool_series(g["is_catchable_ball"]).fillna(False) & catches.notna()
            row["catchable_target_conversion"] = ratio(catches[observed].sum(), observed.sum())

        if "read_thrown" in g.columns:
            counts = Counter(str(x) for x in g["read_thrown"].dropna())
            row["read_thrown_distribution_raw"] = {
                k: {
                    "count": int(v),
                    "share_of_charted_targets": safe_num(v / n) if n else None,
                }
                for k, v in sorted(counts.items())
            }
            codes = g["read_thrown"].astype("string").str.replace(r"\.0$", "", regex=True)
            row["read_thrown_verified_counts"] = {label: int((codes == code).sum()) for code, label in FTN_READ_CODES.items()}
            row["read_thrown_unknown_or_missing"] = int((~codes.isin(FTN_READ_CODES)).sum())
            row["read_thrown_interpretation_status"] = "Official nflreadr FTN dictionary verified 2026-09-02; missing reads are unknown."
            row["read_thrown_definition_url"] = FTN_DICTIONARY
            if "posteam" in merged.columns:
                shares = {}
                for team, pg in g.groupby("posteam"):
                    tg = merged[merged["posteam"] == team]
                    team_codes = tg["read_thrown"].astype("string").str.replace(r"\.0$", "", regex=True)
                    player_codes = pg["read_thrown"].astype("string").str.replace(r"\.0$", "", regex=True)
                    shares[str(team)] = {"primary_read_target_share": ratio((player_codes == "0").sum(), (team_codes == "0").sum()),
                                         "team_charted_primary_read_targets": int((team_codes == "0").sum())}
                row["primary_read_share_by_source_team"] = shares

        out[str(pid)] = row
    return out, read_values


def aggregate_ngs(ngs: pd.DataFrame, season: int, use_season_aggregate: bool = True) -> dict[str, dict]:
    if ngs.empty or "season" not in ngs.columns:
        return {}
    n = ngs[pd.to_numeric(ngs["season"], errors="coerce") == season].copy()
    if n.empty:
        return {}

    id_col = first_existing(n, ["player_gsis_id", "player_id", "gsis_id"])
    name_col = first_existing(n, ["player_display_name", "player_name"])
    if not id_col:
        return {}

    if "week" in n.columns:
        w = pd.to_numeric(n["week"], errors="coerce")
        if use_season_aggregate and (w == 0).any():
            n = n[w == 0].copy()
        elif not use_season_aggregate:
            # Current-season target-week builds use weekly rows only. Season aggregate
            # week=0 rows can contain data from later weeks and would leak look-ahead.
            n = n[w > 0].copy()

    out = {}
    for pid, g in n.groupby(id_col, dropna=True):
        weights = numeric(g, "targets")
        row = {
            "player_name": safe_str(g[name_col].dropna().iloc[-1]) if name_col and g[name_col].notna().any() else None,
            "targets": safe_num(total(g, "targets")),
            "receptions": safe_num(total(g, "receptions")),
        }
        for c in [
            "avg_cushion", "avg_separation", "avg_air_distance",
            "percent_share_of_intended_air_yards"
        ]:
            if c in g.columns:
                row[c] = weighted_mean(g[c], weights)
        if row["targets"]:
            row["catch_percentage_recomputed"] = safe_num(row["receptions"] / row["targets"])
        row["coverage_note"] = (
            "NGS receiving includes only players meeting NFL Next Gen Stats qualification thresholds; missing != zero."
        )
        out[str(pid)] = row
    return out


def aggregate_pfr_rec(pfr: pd.DataFrame, pfr_to_gsis: dict[str, str]) -> dict[str, dict]:
    if pfr.empty:
        return {}
    id_col = first_existing(pfr, ["pfr_player_id", "pfr_id"])
    if not id_col:
        return {}
    out = {}
    for pfr_id, g in pfr.groupby(id_col, dropna=True):
        gsis = pfr_to_gsis.get(str(pfr_id))
        if not gsis:
            continue
        row = {}
        for c in [
            "receiving_drop", "receiving_drops", "receiving_drop_pct",
            "targets", "receptions"
        ]:
            if c in g.columns:
                vals = pd.to_numeric(g[c], errors="coerce")
                if c.endswith("_pct"):
                    row[c] = safe_num(vals.mean())
                else:
                    row[c] = safe_num(vals.sum(min_count=1))
        if row:
            out[gsis] = row
    return out


def current_season_cut(df: pd.DataFrame, target_week: int) -> pd.DataFrame:
    if df.empty:
        return df
    if "week" not in df.columns:
        return df.iloc[0:0].copy()
    w = pd.to_numeric(df["week"], errors="coerce")
    return filter_regular(df[w.between(1, target_week - 1)].copy())


def determine_data_state(inputs: dict[str, Any], target_week: int) -> dict[str, Any]:
    season = inputs["season"]
    stats = current_season_cut(inputs["player_stats"].get(season, pd.DataFrame()), target_week)
    pbp = current_season_cut(inputs["pbp"].get(season, pd.DataFrame()), target_week)

    max_week = None
    for df in (stats, pbp):
        if not df.empty and "week" in df.columns:
            vals = pd.to_numeric(df["week"], errors="coerce").dropna()
            if len(vals):
                m = int(vals.max())
                max_week = m if max_week is None else max(max_week, m)

    if max_week is None:
        mode = "PRE_WEEK_1_OR_NO_CURRENT_REGULAR_SEASON_DATA"
        current_games = 0
    elif max_week <= 3:
        mode = "EARLY_SEASON"
        current_games = max_week
    else:
        mode = "IN_SEASON"
        current_games = max_week

    return {
        "mode": mode,
        "current_season_data_through_week": max_week,
        "current_regular_season_weeks_available": len(set().union(*[set(pd.to_numeric(d["week"], errors="coerce").dropna().astype(int)) for d in (stats, pbp) if not d.empty and "week" in d])),
        "roster_context": "LATEST_AVAILABLE; NOT A POINT-IN-TIME HISTORICAL ROSTER",
        "historical_backtest_eligible": False,
        "target_week": target_week,
        "true_route_participation": "NOT PROVIDED BY THIS FREE PACK IN-SEASON",
        "route_proxy_rule": "offense snap share may be shown only as PROXY; never treat it as routes or route participation",
        "injury_feed": "NOT RELIED ON — verify through official/live research",
        "preseason_usage": "NOT CLAIMED FROM NFLVERSE REGULAR-SEASON PBP; verify via official gamebooks/current reporting",
    }


def fixture_rows(schedule: pd.DataFrame, season: int, week: int | None) -> pd.DataFrame:
    if schedule.empty:
        return schedule
    s = schedule.copy()
    if "season" in s.columns:
        s = s[pd.to_numeric(s["season"], errors="coerce") == season]
    if "game_type" in s.columns:
        s = s[s["game_type"].astype(str) == "REG"]
    if week is not None and "week" in s.columns:
        s = s[pd.to_numeric(s["week"], errors="coerce") == week]
    return s


def player_context(
    roster_row: pd.Series,
    histories: dict[int, dict[str, dict]],
    snap_histories: dict[int, dict[str, dict]],
    ftn_histories: dict[int, dict[str, dict]],
    ngs_histories: dict[int, dict[str, dict]],
    pfr_histories: dict[int, dict[str, dict]],
    season: int,
    current_receiver: dict[str, dict],
    current_snap: dict[str, dict],
    current_ftn: dict[str, dict],
    current_ngs: dict[str, dict],
    current_pfr: dict[str, dict],
) -> dict[str, Any]:
    pid = safe_str(roster_row.get("gsis_id"))
    if not pid:
        pid = f"name:{safe_str(roster_row.get('full_name')) or 'unknown'}"

    current_team = safe_str(roster_row.get("team"))
    prior1 = histories.get(season - 1, {}).get(pid if not pid.startswith("name:") else "", {})
    prior_teams = prior1.get("source_teams", []) if prior1 else []

    years_exp = safe_num(roster_row.get("years_exp"))
    is_rookie = years_exp == 0 if years_exp is not None else None
    changed = (current_team not in prior_teams) if prior_teams and current_team else None

    out = {
        "player_id": None if pid.startswith("name:") else pid,
        "player_name": safe_str(roster_row.get("full_name")) or safe_str(roster_row.get("football_name")),
        "current_team": current_team,
        "position": safe_str(roster_row.get("position")) or safe_str(roster_row.get("depth_chart_position")),
        "roster_status": safe_str(roster_row.get("status")) or safe_str(roster_row.get("status_description_abbr")),
        "years_experience": years_exp,
        "rookie_flag": is_rookie,
        "current_depth": {
            "position_group": safe_str(roster_row.get("pos_grp")),
            "position": safe_str(roster_row.get("pos_abb")) or safe_str(roster_row.get("pos_name")),
            "slot": safe_num(roster_row.get("pos_slot")),
            "rank": safe_num(roster_row.get("pos_rank")),
            "depth_timestamp": safe_str(roster_row.get("dt")),
            "warning": "Depth-chart status supports roster context but does not prove routes.",
        },
        "team_change_since_prior_season": changed,
        "prior_season_teams": prior_teams,
        "current_season_to_date": {
            "receiving": current_receiver.get(pid),
            "snap_proxy": current_snap.get(pid),
            "ftn_charting": current_ftn.get(pid),
            "next_gen_receiving": current_ngs.get(pid),
            "pfr_advanced_receiving": current_pfr.get(pid),
        },
        "historical": {},
        "model_use_notes": [],
    }

    for y in sorted(histories.keys(), reverse=True):
        out["historical"][str(y)] = {
            "season_receiving": histories[y].get(pid),
            "snap_proxy": snap_histories.get(y, {}).get(pid),
            "ftn_charting": ftn_histories.get(y, {}).get(pid),
            "next_gen_receiving": ngs_histories.get(y, {}).get(pid),
            "pfr_advanced_receiving": pfr_histories.get(y, {}).get(pid),
        }

    if changed:
        out["model_use_notes"].append(
            "TRANSFER RISK: prior production/target share came from a different team; do not copy it into the current role without live role translation."
        )
    if is_rookie:
        out["model_use_notes"].append(
            "ROOKIE: NFL historical receiving baseline may be absent; current role must be established by draft/camp/preseason/live research."
        )
    out["model_use_notes"].append(
        "Snap share is a route-opportunity proxy only, especially weak for TE/RB because blocking can inflate snaps."
    )
    return out


def build_game_pack(
    game: pd.Series,
    inputs: dict[str, Any],
    season: int,
    history_n: int,
    caches: dict[str, Any],
) -> dict[str, Any]:
    week = int(game["week"])
    home = safe_str(game.get("home_team"))
    away = safe_str(game.get("away_team"))
    game_id = safe_str(game.get("game_id")) or f"{season}_{week:02d}_{away}_{home}"

    roster = caches["skill_roster"]
    roster_game = roster[roster["team"].astype(str).isin([away, home])].copy() if not roster.empty and "team" in roster.columns else pd.DataFrame()

    players = []
    if not roster_game.empty:
        for _, rr in roster_game.sort_values(["team", "position", "full_name"], na_position="last").iterrows():
            players.append(
                player_context(
                    rr,
                    caches["receiver_histories"],
                    caches["snap_histories"],
                    caches["ftn_histories"],
                    caches["ngs_histories"],
                    caches["pfr_histories"],
                    season,
                    caches["current_receiver_by_week"].get(week, {}),
                    caches["current_snap_by_week"].get(week, {}),
                    caches["current_ftn_by_week"].get(week, {}),
                    caches["current_ngs_by_week"].get(week, {}),
                    caches["current_pfr_by_week"].get(week, {}),
                )
            )

    team_context = {}
    for t in [away, home]:
        if not t:
            continue
        hist = {}
        for y in prior_seasons(season, history_n):
            hist[str(y)] = caches["team_histories"].get(y, {}).get(t)
        current_team = caches["current_team_by_week"].get(week, {}).get(t)
        team_context[t] = {
            "current_season_to_date": current_team,
            "historical": hist,
            "warning": "Historical team rates are baselines; current coaches/QB/personnel/role changes must be researched live.",
        }

    fixture_meta = {}
    for c in [
        "game_id", "season", "week", "game_type", "gameday", "weekday",
        "gametime", "away_team", "home_team", "stadium", "roof",
        "surface", "location"
    ]:
        if c in game.index:
            fixture_meta[c] = safe_str(game.get(c)) if c not in {"season", "week"} else safe_num(game.get(c))

    state = determine_data_state(inputs, week)
    limitations = [
        "NO sportsbook prices/lines/market consensus are contained in this pack.",
        "True current in-season route participation is not available in this free stack; do not infer routes from snap share.",
        "nflverse injury data is not relied on; official injury/practice/inactive research remains mandatory.",
        "Preseason role/deployment must be verified through official gamebooks/current reporting; this pack does not claim preseason route truth.",
        "NGS has qualification thresholds; missing NGS rows are not zero values.",
        "FTN read labels follow the official nflreadr dictionary verified 2026-09-02; missing/unknown reads remain unknown. Primary-read shares use charted team targets only.",
        "Current roster/depth are latest available snapshots. Regenerating an old week is not a point-in-time historical backtest.",
    ]

    return {
        "schema_version": "1.1.0",
        "build_version": BUILD_VERSION,
        "pack_type": "NFL_RECEPTIONS_FREE_RESEARCH_PACK",
        "generated_at_utc": now_iso(),
        "fixture": fixture_meta,
        "data_state": state,
        "team_context": team_context,
        "players": players,
        "source_receipt": {
            "availability": source_availability(inputs, week),
            "nflverse": [
                "play-by-play",
                "player stats",
                "team stats",
                "rosters",
                "depth charts",
                "Next Gen Stats",
                "PFR snap counts",
                "PFR advanced receiving",
                "FTN charting subset via nflverse",
            ],
            "ftn_attribution": "FTN Data via nflverse; free subset licensed CC-BY-SA 4.0.",
            "generated_data_policy": "Pre-market football research only.",
        },
        "limitations": limitations,
        "layer_1_usage_rule": (
            "Use as structured evidence inside Layer 1. Current official/live role, injury, QB, practice and personnel evidence overrides stale historical baselines. "
            "Never use this pack as a substitute for the deep nugget/contradiction search."
        ),
        "game_id": game_id,
    }


def build_caches(inputs: dict[str, Any], season: int, history_n: int, target_weeks: list[int] | None = None) -> dict[str, Any]:
    years = prior_seasons(season, history_n)
    current_roster = inputs["current_roster"]
    skill_roster = roster_skill_players(current_roster, inputs["current_depth"])

    all_rosters = [current_roster] + [inputs["prior_rosters"].get(y, pd.DataFrame()) for y in years]
    pfr_to_gsis = build_id_map(all_rosters, inputs["players"])

    receiver_histories = {}
    snap_histories = {}
    ftn_histories = {}
    ngs_histories = {}
    pfr_histories = {}
    team_histories = {}
    ftn_read_values = {}

    for y in years:
        receiver_histories[y] = aggregate_receiver_window(inputs["player_stats"].get(y, pd.DataFrame()))
        snap_histories[y] = aggregate_snap(inputs["snap"].get(y, pd.DataFrame()), pfr_to_gsis)
        ftn_histories[y], ftn_read_values[y] = ftn_receiver_metrics(
            inputs["ftn"].get(y, pd.DataFrame()),
            inputs["pbp"].get(y, pd.DataFrame()),
        )
        ngs_histories[y] = aggregate_ngs(inputs["ngs_receiving"].get(y, pd.DataFrame()), y, use_season_aggregate=True)
        pfr_histories[y] = aggregate_pfr_rec(inputs["pfr_rec"].get(y, pd.DataFrame()), pfr_to_gsis)
        team_histories[y] = merge_team_metrics(
            inputs["team_stats"].get(y, pd.DataFrame()),
            inputs["pbp"].get(y, pd.DataFrame()),
        )

    # Build week-specific "data available before target week" caches to prevent look-ahead.
    schedule = fixture_rows(inputs["schedule"], season, None)
    weeks = sorted({int(x) for x in pd.to_numeric(schedule.get("week", pd.Series(dtype=int)), errors="coerce").dropna().unique()})
    if target_weeks is not None:
        weeks = sorted(set(target_weeks))
    current_receiver_by_week = {}
    current_snap_by_week = {}
    current_ftn_by_week = {}
    current_ngs_by_week = {}
    current_pfr_by_week = {}
    current_team_by_week = {}

    for target_week in weeks:
        ps = current_season_cut(inputs["player_stats"].get(season, pd.DataFrame()), target_week)
        sn = current_season_cut(inputs["snap"].get(season, pd.DataFrame()), target_week)
        pb = current_season_cut(inputs["pbp"].get(season, pd.DataFrame()), target_week)
        ft = current_season_cut(inputs["ftn"].get(season, pd.DataFrame()), target_week)
        ng = current_season_cut(inputs["ngs_receiving"].get(season, pd.DataFrame()), target_week)
        pr = current_season_cut(inputs["pfr_rec"].get(season, pd.DataFrame()), target_week)
        ts = current_season_cut(inputs["team_stats"].get(season, pd.DataFrame()), target_week)

        current_receiver_by_week[target_week] = aggregate_receiver_window(ps)
        current_snap_by_week[target_week] = aggregate_snap(sn, pfr_to_gsis)
        current_ftn_by_week[target_week], _ = ftn_receiver_metrics(ft, pb)
        current_ngs_by_week[target_week] = aggregate_ngs(ng, season, use_season_aggregate=False)
        current_pfr_by_week[target_week] = aggregate_pfr_rec(pr, pfr_to_gsis)
        current_team_by_week[target_week] = merge_team_metrics(ts, pb)

    return {
        "skill_roster": skill_roster,
        "pfr_to_gsis": pfr_to_gsis,
        "receiver_histories": receiver_histories,
        "snap_histories": snap_histories,
        "ftn_histories": ftn_histories,
        "ngs_histories": ngs_histories,
        "pfr_histories": pfr_histories,
        "team_histories": team_histories,
        "current_receiver_by_week": current_receiver_by_week,
        "current_snap_by_week": current_snap_by_week,
        "current_ftn_by_week": current_ftn_by_week,
        "current_ngs_by_week": current_ngs_by_week,
        "current_pfr_by_week": current_pfr_by_week,
        "current_team_by_week": current_team_by_week,
        "ftn_read_values_observed": ftn_read_values,
    }


def _stable_payload(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _stable_payload(v) for k, v in obj.items() if k != "generated_at_utc"}
    if isinstance(obj, list):
        return [_stable_payload(v) for v in obj]
    return obj


def payload_hash(payload: Any) -> str:
    raw = json.dumps(_stable_payload(payload), sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def write_json(path: Path, payload: Any) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            old = json.loads(path.read_text(encoding="utf-8"))
            if _stable_payload(old) == _stable_payload(payload):
                log(f"unchanged {path}")
                return False
        except Exception:
            pass
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    tmp.replace(path)
    return True


def resolve_active_week(schedule: pd.DataFrame, season: int) -> int:
    s = fixture_rows(schedule, season, None)
    if s.empty or "week" not in s.columns:
        raise RuntimeError("Cannot resolve active week: regular-season schedule unavailable")
    # Best signal is an unplayed game. The nflverse schedule updates every ~5 minutes.
    if "result" in s.columns:
        unplayed = s[s["result"].isna()].copy()
        if not unplayed.empty:
            return int(pd.to_numeric(unplayed["week"], errors="coerce").dropna().min())
    # Date fallback for unusual schedule/result states.
    if "gameday" in s.columns:
        today = pd.Timestamp.now(tz="UTC").date()
        gd = pd.to_datetime(s["gameday"], errors="coerce").dt.date
        future = s[gd >= today].copy()
        if not future.empty:
            return int(pd.to_numeric(future["week"], errors="coerce").dropna().min())
    return int(pd.to_numeric(s["week"], errors="coerce").dropna().max())


def validate_core_sources(inputs: dict[str, Any], season: int, history_n: int) -> dict[str, Any]:
    prior = season - 1
    checks = {
        "schedule_current": not inputs.get("schedule", pd.DataFrame()).empty,
        "roster_current": not inputs.get("current_roster", pd.DataFrame()).empty,
        "depth_current": not inputs.get("current_depth", pd.DataFrame()).empty,
        f"player_stats_{prior}": not inputs.get("player_stats", {}).get(prior, pd.DataFrame()).empty,
        f"pbp_{prior}": not inputs.get("pbp", {}).get(prior, pd.DataFrame()).empty,
    }
    required = ["schedule_current", "roster_current", f"player_stats_{prior}", f"pbp_{prior}"]
    failed = [k for k in required if not checks.get(k)]
    optional = {
        f"ftn_{prior}": not inputs.get("ftn", {}).get(prior, pd.DataFrame()).empty,
        f"ngs_{prior}": not inputs.get("ngs_receiving", {}).get(prior, pd.DataFrame()).empty,
        f"snap_{prior}": not inputs.get("snap", {}).get(prior, pd.DataFrame()).empty,
        f"pfr_rec_{prior}": not inputs.get("pfr_rec", {}).get(prior, pd.DataFrame()).empty,
    }
    return {
        "status": "FAIL" if failed else ("PARTIAL" if not all(optional.values()) or not checks["depth_current"] else "PASS"),
        "required_checks": checks,
        "optional_checks": optional,
        "failed_required": failed,
    }


def source_availability(inputs: dict[str, Any], target_week: int) -> dict[str, Any]:
    out = {}
    for name in ("player_stats", "team_stats", "pbp", "ftn", "snap", "pfr_rec", "ngs_receiving"):
        out[name] = {}
        for season, frame in inputs.get(name, {}).items():
            df = current_season_cut(frame, target_week) if season == inputs["season"] else filter_regular(frame)
            weeks = numeric(df, "week")
            out[name][str(season)] = {"status": "AVAILABLE" if not df.empty else "UNAVAILABLE_OR_NO_ELIGIBLE_ROWS",
                                     "rows": len(df), "through_week": safe_num(weeks.max()),
                                     "upstream_publication_time": None}
    for name in ("current_roster", "current_depth"):
        df = inputs.get(name, pd.DataFrame())
        out[name] = {"rows": len(df), "status": "AVAILABLE" if len(df) else "UNAVAILABLE",
                     "context": "latest available; not a historical point-in-time snapshot"}
    return out

def build_all(season: int, out_dir: Path, history_n: int, only_week: int | None, verify_sources: bool = False) -> None:
    inputs = load_inputs(season, history_n)
    health = validate_core_sources(inputs, season, history_n)
    if health["status"] == "FAIL":
        raise SystemExit(f"Core source gate failed; refusing to publish a degraded pack: {health['failed_required']}")

    target_week = only_week if only_week is not None else resolve_active_week(inputs["schedule"], season)
    log(f"target active week: {target_week}")
    sched = fixture_rows(inputs["schedule"], season, target_week)
    if sched.empty:
        raise SystemExit(f"No regular-season fixtures found for {season} week {target_week}")

    # Current-season data becomes essential once regular-season games exist.
    if target_week > 1:
        for name in ("player_stats", "pbp"):
            eligible = current_season_cut(inputs[name].get(season, pd.DataFrame()), target_week)
            if eligible.empty:
                raise SystemExit(f"Missing current-season {name} before week {target_week}; keeping last good published pack")

    caches = build_caches(inputs, season, history_n, [target_week])

    manifest_games = []
    built_packs = []
    for _, game in sched.sort_values(["week", "gameday", "gametime"], na_position="last").iterrows():
        pack = build_game_pack(game, inputs, season, history_n, caches)
        pack["source_health"] = health
        game_id = pack["game_id"]
        for team in (str(game["away_team"]), str(game["home_team"])):
            if not any(p["current_team"] == team for p in pack["players"]):
                raise ValueError(f"No eligible roster players for {team}; refusing publication")
        pack["pack_revision"] = payload_hash(pack)
        built_packs.append(pack)
        path = out_dir / "games" / str(season) / f"{game_id}.json"
        write_json(path, pack)
        manifest_games.append({
            "game_id": game_id,
            "season": safe_num(game.get("season")),
            "week": safe_num(game.get("week")),
            "away_team": safe_str(game.get("away_team")),
            "home_team": safe_str(game.get("home_team")),
            "gameday": safe_str(game.get("gameday")),
            "gametime": safe_str(game.get("gametime")),
            "data_state": pack["data_state"]["mode"],
            "path": f"games/{season}/{game_id}.json",
            "pack_revision": pack["pack_revision"],
        })
        log(f"wrote {path}")

    manifest_path = out_dir / "manifest.json"
    manifest = {
        "schema_version": "1.1.0",
        "build_version": BUILD_VERSION,
        "season": season,
        "active_week": target_week,
        "generated_at_utc": now_iso(),
        "last_checked_at_utc": now_iso(),
        "games": sorted(manifest_games, key=lambda x: (x.get("gameday") or "", x.get("game_id") or "")),
        "source_health": health,
        "source_status": {
            "FTN_read_values_observed_by_prior_season": {
                str(k): v for k, v in caches["ftn_read_values_observed"].items()
            },
            "route_participation": "NOT PROVIDED IN-SEASON",
            "injuries": "NOT RELIED ON",
        },
        "attribution": "Includes FTN Data via nflverse; FTN subset is CC-BY-SA 4.0.",
    }
    if verify_sources:
        from reconcile_sources import verify
        write_json(out_dir / "source_acceptance.json", verify(inputs, built_packs))
    write_json(manifest_path, manifest)
    log(f"wrote {manifest_path}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--season", type=int, required=True)
    p.add_argument("--output", default="data")
    p.add_argument("--history-seasons", type=int, default=2)
    p.add_argument("--week", type=int, default=None, help="Optional override. Default automatically resolves the earliest unplayed regular-season week.")
    p.add_argument("--verify-sources", action="store_true", help="Reconcile two real packs to the loaded source rows before publication.")
    args = p.parse_args()
    if not 1 <= args.history_seasons <= 3:
        p.error("--history-seasons must be between 1 and 3")
    if args.week is not None and not 1 <= args.week <= 18:
        p.error("--week must be between 1 and 18")
    build_all(args.season, Path(args.output), args.history_seasons, args.week, args.verify_sources)


if __name__ == "__main__":
    main()
