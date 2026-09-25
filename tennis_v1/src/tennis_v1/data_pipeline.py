from __future__ import annotations

from dataclasses import dataclass, asdict
from hashlib import sha256
import json
from pathlib import Path
from typing import Iterable

import pandas as pd

from .data_sources import SCHEMA_VERSION, assert_market_blind
from .ratings import build_player_states


@dataclass(frozen=True)
class CoverageDecision:
    results_rows: int
    atp_results_rows: int
    wta_results_rows: int
    serve_stats_rows: int
    serve_stats_latest_year: int | None
    serve_stats_atp_years: tuple[int, ...]
    serve_stats_wta_years: tuple[int, ...]
    results_ready: bool
    serve_return_ready: bool
    tpi_ready: bool
    match_input_ready: bool
    zero_upload_status: str
    blockers: tuple[str, ...]


def _sha_file(path: Path) -> str:
    h = sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize_results(frames: Iterable[pd.DataFrame]) -> pd.DataFrame:
    frames = list(frames)
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    assert_market_blind(df)
    df = df.drop_duplicates(subset=["source", "source_record_id"], keep="last")
    row_valid = (
        (df["winner_id"].astype(str) == df["player_a_id"].astype(str))
        | (df["winner_id"].astype(str) == df["player_b_id"].astype(str))
    )
    df.loc[~row_valid, "quality_flags"] = (
        df.loc[~row_valid, "quality_flags"].astype(str).replace("ok", "") + "|winner_id_mismatch"
    )
    return df.sort_values(["event_date", "source_record_id"], kind="stable").reset_index(drop=True)


def build_players(matches: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for side in ("a", "b"):
        part = matches[["tour", f"player_{side}_id", f"player_{side}_name", "source", "retrieved_at_utc"]].copy()
        part.columns = ["tour", "player_id", "player_name", "source", "retrieved_at_utc"]
        rows.append(part)
    out = pd.concat(rows, ignore_index=True).dropna(subset=["player_id"]).sort_values("retrieved_at_utc")
    out = out.drop_duplicates(subset=["tour", "player_id"], keep="last")
    out["schema_version"] = SCHEMA_VERSION
    out["quality_flags"] = "ok"
    return out.reset_index(drop=True)


def build_tournaments(matches: pd.DataFrame) -> pd.DataFrame:
    cols = ["tour", "tournament_id", "tournament_name", "category", "surface", "source", "retrieved_at_utc"]
    out = matches[cols].drop_duplicates().copy()
    out["schema_version"] = SCHEMA_VERSION
    out["quality_flags"] = "ok"
    return out.reset_index(drop=True)


def build_tournament_conditions(serve_stats: pd.DataFrame) -> pd.DataFrame:
    """Build TPI inputs only when exact dated match-level serve stats exist."""
    if serve_stats.empty or "event_date" not in serve_stats or serve_stats["event_date"].isna().all():
        return pd.DataFrame(columns=[
            "tour", "tournament_name", "event_date", "prior_matches", "service_points_won_rate",
            "ace_rate", "double_fault_rate", "hold_rate", "break_rate", "quality_flags",
        ])
    return pd.DataFrame()


def evaluate_coverage(matches: pd.DataFrame, serve_stats: pd.DataFrame, current_year: int) -> CoverageDecision:
    atp = int((matches["tour"].astype(str).str.upper() == "ATP").sum()) if not matches.empty else 0
    wta = int((matches["tour"].astype(str).str.upper() == "WTA").sum()) if not matches.empty else 0
    years_atp: tuple[int, ...] = ()
    years_wta: tuple[int, ...] = ()
    latest = None
    if not serve_stats.empty and "event_year" in serve_stats:
        years_atp = tuple(sorted(set(pd.to_numeric(
            serve_stats.loc[serve_stats["tour"] == "ATP", "event_year"], errors="coerce"
        ).dropna().astype(int))))
        years_wta = tuple(sorted(set(pd.to_numeric(
            serve_stats.loc[serve_stats["tour"] == "WTA", "event_year"], errors="coerce"
        ).dropna().astype(int))))
        all_years = years_atp + years_wta
        latest = max(all_years) if all_years else None

    results_ready = atp > 0 and wta > 0
    serve_ready = (
        len(years_atp) >= 3
        and len(years_wta) >= 3
        and latest is not None
        and latest >= current_year - 1
    )
    tpi_ready = (
        serve_ready
        and ("event_date" in serve_stats.columns)
        and serve_stats["event_date"].notna().any()
    )
    match_input_ready = results_ready and serve_ready
    blockers: list[str] = []
    if not results_ready:
        blockers.append("ATP/WTA result history is incomplete")
    if not serve_ready:
        blockers.append(
            "No zero-cost automated source supplies sufficiently deep and current ATP+WTA "
            "match-level serve/return statistics"
        )
    if not tpi_ready:
        blockers.append(
            "Tournament Pace Index lacks current chronologically dated serve/return observations"
        )
    status = "PASS" if match_input_ready and tpi_ready else "FAIL_SERVE_STATS_GAP"
    return CoverageDecision(
        results_rows=len(matches),
        atp_results_rows=atp,
        wta_results_rows=wta,
        serve_stats_rows=len(serve_stats),
        serve_stats_latest_year=latest,
        serve_stats_atp_years=years_atp,
        serve_stats_wta_years=years_wta,
        results_ready=results_ready,
        serve_return_ready=serve_ready,
        tpi_ready=tpi_ready,
        match_input_ready=match_input_ready,
        zero_upload_status=status,
        blockers=tuple(blockers),
    )


def write_pack(output_dir: Path, matches: pd.DataFrame, serve_stats: pd.DataFrame, current_year: int) -> CoverageDecision:
    output_dir.mkdir(parents=True, exist_ok=True)
    assert_market_blind(matches)
    assert_market_blind(serve_stats)
    players = build_players(matches)
    tournaments = build_tournaments(matches)
    states = build_player_states(matches)
    tpi = build_tournament_conditions(serve_stats)

    assets = {
        "matches.parquet": matches,
        "match_stats.parquet": serve_stats,
        "players.parquet": players,
        "tournaments.parquet": tournaments,
        "player_state_daily.parquet": states,
        "tournament_conditions.parquet": tpi,
    }
    manifest_assets = {}
    for name, df in assets.items():
        path = output_dir / name
        df.to_parquet(path, index=False)
        manifest_assets[name] = {"rows": len(df), "sha256": _sha_file(path)}

    decision = evaluate_coverage(matches, serve_stats, current_year)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "market_data": False,
        "assets": manifest_assets,
        "coverage": asdict(decision),
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, default=str, sort_keys=True), encoding="utf-8"
    )
    return decision


def build_match_input_pack(*_args, **_kwargs):
    raise RuntimeError(
        "MATCH_INPUT_BLOCKED: results-only Elo/workload states cannot credibly identify "
        "separate serve and return strengths; a current multi-season ATP+WTA match-level "
        "serve/return source is required."
    )
