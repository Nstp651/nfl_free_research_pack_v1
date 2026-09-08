from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd
import pyreadr

from nba_player_props_v1.historical.source_catalog import core_assets
from nba_player_props_v1.source_receipt import canonical_json, sha256_bytes, sha256_file

NBA_ESPN_TEAMS = {str(i) for i in range(1, 31)}
RECON_FIELDS = (
    "assists",
    "field_goals_made",
    "field_goals_attempted",
    "three_point_field_goals_made",
    "three_point_field_goals_attempted",
    "free_throws_made",
    "free_throws_attempted",
)
RAW_RECON_FIELDS = (
    "assists",
    "rebounds",
    "offensive_rebounds",
    "defensive_rebounds",
    "field_goals_made",
    "field_goals_attempted",
    "three_point_field_goals_made",
    "three_point_field_goals_attempted",
    "free_throws_made",
    "free_throws_attempted",
)
MAX_QUARANTINED_ROW_FRACTION = 0.0005


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json(value) + b"\n")


def _download(url: str, cache: Path) -> tuple[Path, str, int]:
    cache.mkdir(parents=True, exist_ok=True)
    key = sha256_bytes(url.encode())
    path = cache / key
    if not path.exists():
        req = Request(url, headers={"User-Agent": "NBA-V1-source-acceptance/1.0", "Accept": "application/octet-stream"})
        with urlopen(req, timeout=120) as response:
            path.write_bytes(response.read())
    return path, sha256_file(path), path.stat().st_size


def _asset_for(season: int, dataset: str):
    matches = [a for a in core_assets(season) if a.dataset == dataset]
    if len(matches) != 1:
        raise ValueError(f"expected one {dataset} asset for {season}")
    return matches[0]


def _first_column(frame: pd.DataFrame, candidates: tuple[str, ...], label: str) -> str:
    hits = [name for name in candidates if name in frame.columns]
    if not hits:
        raise ValueError(f"{label} schema missing one of {list(candidates)}; columns={sorted(map(str, frame.columns))}")
    return hits[0]


def _minutes(value) -> float:
    if pd.isna(value):
        return 0.0
    if isinstance(value, str) and ":" in value:
        minutes, seconds = value.split(":", 1)
        minutes, seconds = float(minutes), float(seconds)
        if minutes < 0 or seconds < 0 or seconds >= 60:
            raise ValueError("invalid minutes clock")
        return minutes + seconds / 60.0
    return float(value)


def _boolean(value) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if value in (0, 1):
        return bool(value)
    if isinstance(value, str) and value.lower() in ("true", "false"):
        return value.lower() == "true"
    if pd.isna(value):
        return False
    raise ValueError(f"invalid boolean value {value!r}")


def _normalize_team_box(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"game_id", "season", "season_type", "team_id", "opponent_team_id", "team_score", "opponent_team_score", *RAW_RECON_FIELDS}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"team-box schema missing {missing}")
    out = frame.loc[:, sorted(required)].copy()
    for col in ("game_id", "team_id", "opponent_team_id"):
        out[col] = out[col].astype("string")
    out = out[out.season_type.isin([2, 3]) & out.team_id.isin(NBA_ESPN_TEAMS) & out.opponent_team_id.isin(NBA_ESPN_TEAMS)].copy()
    for col in ("team_score", "opponent_team_score", *RAW_RECON_FIELDS):
        out[col] = pd.to_numeric(out[col], errors="raise")
    if out.duplicated(["game_id", "team_id"]).any():
        raise ValueError("duplicate team-box game/team rows")
    return out


def _normalize_raw_player_box(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"game_id", "season", "season_type", "athlete_id", "team_id", "opponent_team_id", "minutes", "did_not_play", *RAW_RECON_FIELDS}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"raw player-box schema missing {missing}")
    out = frame.loc[:, sorted(required)].copy()
    for col in ("game_id", "athlete_id", "team_id", "opponent_team_id"):
        out[col] = out[col].astype("string")
    out = out[out.season_type.isin([2, 3]) & out.team_id.isin(NBA_ESPN_TEAMS) & out.opponent_team_id.isin(NBA_ESPN_TEAMS)].copy()
    out["minutes_parsed"] = out.minutes.map(_minutes)
    out["dnp_parsed"] = out.did_not_play.map(_boolean)
    for col in RAW_RECON_FIELDS:
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0)
        if (out[col] < 0).any():
            raise ValueError(f"negative raw player-box {col}")
    out["positive_stat_sum"] = out[list(RAW_RECON_FIELDS)].sum(axis=1)
    if out.duplicated(["game_id", "athlete_id"]).any():
        raise ValueError("duplicate raw player-box player/game rows")
    return out


def _normalize_schedule(frame: pd.DataFrame) -> pd.DataFrame:
    core = {"game_id", "season", "season_type"}
    missing = sorted(core.difference(frame.columns))
    if missing:
        raise ValueError(f"schedule schema missing {missing}")
    home_col = _first_column(frame, ("home_team_id", "home_id"), "schedule home team")
    away_col = _first_column(frame, ("away_team_id", "away_id"), "schedule away team")
    time_col = _first_column(frame, ("game_date_time", "date", "game_date"), "schedule start time")
    out = frame.loc[:, ["game_id", "season", "season_type", home_col, away_col, time_col]].copy().rename(
        columns={home_col: "home_team_id", away_col: "away_team_id", time_col: "game_date_time"}
    )
    for col in ("game_id", "home_team_id", "away_team_id"):
        out[col] = out[col].astype("string")
    out = out[out.season_type.isin([2, 3]) & out.home_team_id.isin(NBA_ESPN_TEAMS) & out.away_team_id.isin(NBA_ESPN_TEAMS)].copy()
    out["game_date_time"] = pd.to_datetime(out.game_date_time, utc=True, errors="raise")
    if out.duplicated(["game_id"]).any():
        raise ValueError("duplicate schedule game ids")
    return out


def _field_reconciliation(merged: pd.DataFrame, field: str, player_prefix: str = "player_") -> dict:
    player_col = f"{player_prefix}{field}"
    player = merged[player_col].astype(float)
    team = merged[field].astype(float)
    ok = np.isclose(player, team, atol=0, rtol=0)
    delta = player - team
    mismatch = merged.loc[~ok, ["game_id_espn", "team_id_espn", "season", player_col, field]].copy()
    mismatch["delta_player_minus_team"] = delta.loc[~ok].astype(float)
    mismatch = mismatch.sort_values(["season", "game_id_espn", "team_id_espn"])
    by_season = {}
    for season, group in mismatch.groupby("season", dropna=False):
        by_season[str(int(season)) if pd.notna(season) else "null"] = int(len(group))
    return {
        "matches": int(ok.sum()),
        "rows": int(len(ok)),
        "rate": float(ok.mean()),
        "mismatch_rows": int((~ok).sum()),
        "max_abs_delta": float(delta.loc[~ok].abs().max()) if (~ok).any() else 0.0,
        "mean_abs_delta_mismatches": float(delta.loc[~ok].abs().mean()) if (~ok).any() else 0.0,
        "mismatches_by_season": by_season,
        "mismatch_sample": mismatch.head(50).to_dict("records"),
    }


def reconcile(history: pd.DataFrame, team_box: pd.DataFrame, schedule: pd.DataFrame) -> dict:
    """Diagnostic reconciliation of the model-training table.

    This intentionally remains strict. A FAIL here is acceptable only when the raw
    source acceptance and quarantine audit prove the difference is entirely caused
    by explicitly quarantined zero-minute/DNP source defects.
    """
    history = history.copy()
    for col in ("game_id_espn", "team_id_espn", "opponent_team_id_espn"):
        history[col] = history[col].astype("string")
    history["game_start_utc"] = pd.to_datetime(history.game_start_utc, utc=True, errors="raise")

    grouped = history.groupby(["season", "game_id_espn", "team_id_espn"], as_index=False).agg(
        **{f"player_{field}": (field, "sum") for field in RECON_FIELDS},
        player_team_score=("team_score", "first"),
        player_opponent_team_score=("opponent_team_score", "first"),
        opponent_team_id_espn=("opponent_team_id_espn", "first"),
        game_start_utc=("game_start_utc", "first"),
    )
    t = team_box.rename(columns={"game_id": "game_id_espn", "team_id": "team_id_espn", "opponent_team_id": "team_box_opponent_team_id"})
    merged = grouped.merge(t, on=["season", "game_id_espn", "team_id_espn"], how="outer", indicator=True, validate="one_to_one")
    if not (merged._merge == "both").all():
        missing = merged.loc[merged._merge != "both", ["season", "game_id_espn", "team_id_espn", "_merge"]].head(20).to_dict("records")
        raise ValueError(f"team-box coverage mismatch: {missing}")
    exact = {field: _field_reconciliation(merged, field) for field in RECON_FIELDS}
    score_ok = np.isclose(merged.player_team_score.astype(float), merged.team_score.astype(float), atol=0, rtol=0)
    opponent_score_ok = np.isclose(merged.player_opponent_team_score.astype(float), merged.opponent_team_score.astype(float), atol=0, rtol=0)
    opponent_id_ok = merged.opponent_team_id_espn.astype(str).eq(merged.team_box_opponent_team_id.astype(str))

    sched = schedule.rename(columns={"game_id": "game_id_espn"}).copy()
    hist_games = history.groupby(["season", "game_id_espn"], as_index=False).agg(
        game_start_utc=("game_start_utc", "first"),
        teams=("team_id_espn", lambda s: tuple(sorted(set(map(str, s))))),
    )
    sched["teams"] = sched.apply(lambda r: tuple(sorted((str(r.home_team_id), str(r.away_team_id)))), axis=1)
    schedule_ids = set(zip(sched.season.astype(int), sched.game_id_espn.astype(str)))
    history_ids = set(zip(hist_games.season.astype(int), hist_games.game_id_espn.astype(str)))
    extra_schedule_ids = sorted(schedule_ids - history_ids)
    sm = hist_games.merge(sched[["season", "game_id_espn", "game_date_time", "teams"]], on=["season", "game_id_espn"], how="left", suffixes=("_history", "_schedule"), indicator=True, validate="one_to_one")
    if not (sm._merge == "both").all():
        missing = sm.loc[sm._merge != "both", ["season", "game_id_espn", "_merge"]].head(20).to_dict("records")
        raise ValueError(f"played-game schedule coverage mismatch: {missing}")
    team_identity_ok = sm.teams_history.eq(sm.teams_schedule)
    seconds = (pd.to_datetime(sm.game_start_utc, utc=True) - pd.to_datetime(sm.game_date_time, utc=True)).dt.total_seconds().abs()
    time_ok = seconds <= 60

    hard_rates = [v["rate"] for v in exact.values()] + [float(score_ok.mean()), float(opponent_score_ok.mean()), float(opponent_id_ok.mean()), float(team_identity_ok.mean()), float(time_ok.mean())]
    passed = min(hard_rates) >= 0.999
    return {
        "status": "PASS" if passed else "FAIL",
        "team_rows": int(len(merged)),
        "played_schedule_games": int(len(sm)),
        "schedule_rows_total": int(len(sched)),
        "schedule_rows_without_played_box": int(len(extra_schedule_ids)),
        "schedule_rows_without_played_box_sample": [{"season": int(season), "game_id_espn": game_id} for season, game_id in extra_schedule_ids[:20]],
        "exact_core_fields": exact,
        "team_score_rate": float(score_ok.mean()),
        "opponent_team_score_rate": float(opponent_score_ok.mean()),
        "opponent_identity_rate": float(opponent_id_ok.mean()),
        "played_schedule_coverage_rate": float((sm._merge == "both").mean()),
        "schedule_team_identity_rate": float(team_identity_ok.mean()),
        "schedule_start_time_within_60s_rate": float(time_ok.mean()),
        "schedule_start_time_max_abs_seconds": float(seconds.max()),
        "threshold": 0.999,
        "directionality_rule": "ALL_PLAYED_GAMES_MUST_RECONCILE; UNPLAYED_SCHEDULE_ROWS_ARE_REPORTED_NOT_TREATED_AS_BOX_FAILURES",
    }


def reconcile_raw_player_to_team(raw_player: pd.DataFrame, team_box: pd.DataFrame) -> dict:
    grouped = raw_player.groupby(["season", "game_id", "team_id"], as_index=False).agg(
        **{f"raw_{field}": (field, "sum") for field in RAW_RECON_FIELDS},
        raw_opponent_team_id=("opponent_team_id", "first"),
    ).rename(columns={"game_id": "game_id_espn", "team_id": "team_id_espn"})
    t = team_box.rename(columns={"game_id": "game_id_espn", "team_id": "team_id_espn", "opponent_team_id": "team_box_opponent_team_id"})
    merged = grouped.merge(t, on=["season", "game_id_espn", "team_id_espn"], how="outer", indicator=True, validate="one_to_one")
    coverage_ok = merged._merge.eq("both")
    if not coverage_ok.all():
        sample = merged.loc[~coverage_ok, ["season", "game_id_espn", "team_id_espn", "_merge"]].head(50).to_dict("records")
        return {"status": "FAIL", "coverage_rate": float(coverage_ok.mean()), "coverage_mismatch_sample": sample}
    exact = {field: _field_reconciliation(merged, field, player_prefix="raw_") for field in RAW_RECON_FIELDS}
    opponent_ok = merged.raw_opponent_team_id.astype(str).eq(merged.team_box_opponent_team_id.astype(str))
    passed = all(v["rate"] == 1.0 for v in exact.values()) and bool(opponent_ok.all())
    return {
        "status": "PASS" if passed else "FAIL",
        "coverage_rate": 1.0,
        "team_rows": int(len(merged)),
        "exact_fields": exact,
        "opponent_identity_rate": float(opponent_ok.mean()),
        "threshold": 1.0,
        "rule": "RAW FRANCHISE PLAYER-BOX SUMS MUST EXACTLY MATCH INDEPENDENT TEAM-BOX TOTALS",
    }


def quarantine_transform_audit(history: pd.DataFrame, raw_player: pd.DataFrame) -> dict:
    history = history.copy()
    for col in ("game_id_espn", "team_id_espn"):
        history[col] = history[col].astype("string")
    quarantine = raw_player[(raw_player.positive_stat_sum > 0) & (raw_player.dnp_parsed | (raw_player.minutes_parsed <= 0))].copy()
    raw_grouped = raw_player.groupby(["season", "game_id", "team_id"], as_index=False).agg(
        **{f"raw_{field}": (field, "sum") for field in RAW_RECON_FIELDS}
    ).rename(columns={"game_id": "game_id_espn", "team_id": "team_id_espn"})
    hist_grouped = history.groupby(["season", "game_id_espn", "team_id_espn"], as_index=False).agg(
        **{f"training_{field}": (field, "sum") for field in RAW_RECON_FIELDS}
    )
    if quarantine.empty:
        q_grouped = raw_grouped[["season", "game_id_espn", "team_id_espn"]].copy()
        for field in RAW_RECON_FIELDS:
            q_grouped[f"quarantine_{field}"] = 0.0
    else:
        q_grouped = quarantine.groupby(["season", "game_id", "team_id"], as_index=False).agg(
            **{f"quarantine_{field}": (field, "sum") for field in RAW_RECON_FIELDS}
        ).rename(columns={"game_id": "game_id_espn", "team_id": "team_id_espn"})
    merged = raw_grouped.merge(hist_grouped, on=["season", "game_id_espn", "team_id_espn"], how="left", validate="one_to_one").merge(
        q_grouped, on=["season", "game_id_espn", "team_id_espn"], how="left", validate="one_to_one"
    )
    exact = {}
    for field in RAW_RECON_FIELDS:
        training = merged[f"training_{field}"].fillna(0).astype(float)
        quarantined = merged[f"quarantine_{field}"].fillna(0).astype(float)
        raw = merged[f"raw_{field}"].astype(float)
        ok = np.isclose(training + quarantined, raw, atol=0, rtol=0)
        exact[field] = {"rate": float(ok.mean()), "mismatch_rows": int((~ok).sum())}
    fraction = float(len(quarantine) / len(raw_player)) if len(raw_player) else 0.0
    target_units = {field: float(quarantine[field].sum()) for field in ("assists", "rebounds")}
    passed = all(v["rate"] == 1.0 for v in exact.values()) and fraction <= MAX_QUARANTINED_ROW_FRACTION
    return {
        "status": "PASS" if passed else "FAIL",
        "raw_franchise_player_rows": int(len(raw_player)),
        "quarantined_positive_stat_rows": int(len(quarantine)),
        "quarantined_row_fraction": fraction,
        "max_quarantined_row_fraction": MAX_QUARANTINED_ROW_FRACTION,
        "quarantined_target_units": target_units,
        "training_plus_quarantine_equals_raw": exact,
        "quarantine_rule": "POSITIVE BOX STATS WITH DNP=true OR minutes<=0 ARE SOURCE-DEFECT ROWS; NEVER IMPUTE MINUTES INTO MODEL TRAINING",
    }


def runtime_espn_schema_probe(as_of: str) -> dict:
    date = pd.Timestamp(as_of)
    if date.tzinfo is None:
        raise ValueError("as_of requires timezone")
    day = date.tz_convert("America/New_York").strftime("%Y%m%d")
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={day}&limit=100"
    result = {"url": url, "checked_at_utc": datetime.now(timezone.utc).isoformat(), "market_data": False}
    try:
        req = Request(url, headers={"User-Agent": "NBA-V1-source-acceptance/1.0", "Accept": "application/json"})
        with urlopen(req, timeout=30) as response:
            raw = response.read()
        body = json.loads(raw)
        events = body.get("events")
        if not isinstance(events, list):
            raise ValueError("ESPN scoreboard events array missing")
        for event in events:
            if not str(event.get("id", "")).isdigit() or not event.get("date"):
                raise ValueError("ESPN scoreboard event identity malformed")
            comps = event.get("competitions") or []
            if len(comps) != 1 or len(comps[0].get("competitors") or []) != 2:
                raise ValueError("ESPN scoreboard competitor identity malformed")
        result.update(status="PASS", http_status=response.status, bytes=len(raw), sha256=sha256_bytes(raw), event_count=len(events))
    except Exception as exc:
        result.update(status="FAIL", error_type=type(exc).__name__, reason=str(exc))
    return result


def _pinned_player_assets(source_pins_path: str | None) -> dict[int, dict]:
    if not source_pins_path:
        return {}
    body = json.loads(Path(source_pins_path).read_text())
    out = {}
    for item in body.get("assets", []):
        if item.get("dataset") == "player_box":
            out[int(item["season_end_year"])] = item
    return out


def run(history_path: str, seasons: list[int], cache: str, output: str, as_of: str, source_pins_path: str | None = None) -> dict:
    history = pd.read_csv(history_path, dtype={"game_id_espn": str, "player_id_espn": str, "team_id_espn": str, "opponent_team_id_espn": str})
    team_frames, schedule_frames, raw_player_frames, assets = [], [], [], []
    cache_path = Path(cache)
    player_pins = _pinned_player_assets(source_pins_path)
    for season in sorted(set(seasons)):
        for dataset in ("player_box", "team_box", "schedule"):
            asset = _asset_for(season, dataset)
            path, digest, size = _download(asset.url, cache_path)
            if dataset == "player_box" and season in player_pins:
                expected = player_pins[season]
                if digest != expected.get("sha256") or size != int(expected.get("bytes")):
                    raise ValueError(f"pinned player-box bytes drift for {season}")
            frame = pyreadr.read_r(str(path))[None]
            if dataset == "player_box":
                normalized = _normalize_raw_player_box(frame)
                raw_player_frames.append(normalized)
            elif dataset == "team_box":
                normalized = _normalize_team_box(frame)
                team_frames.append(normalized)
            else:
                normalized = _normalize_schedule(frame)
                schedule_frames.append(normalized)
            if set(normalized.season.astype(int)) != {season}:
                raise ValueError(f"{dataset} season mismatch for {season}")
            assets.append({**asdict(asset), "sha256": digest, "bytes": size, "source_rows": len(frame), "accepted_rows": len(normalized)})
    team_box = pd.concat(team_frames, ignore_index=True)
    schedule = pd.concat(schedule_frames, ignore_index=True)
    raw_player = pd.concat(raw_player_frames, ignore_index=True)
    training_diagnostic = reconcile(history, team_box, schedule)
    raw_reconciliation = reconcile_raw_player_to_team(raw_player, team_box)
    quarantine = quarantine_transform_audit(history, raw_player)
    identity_pass = all(training_diagnostic[key] == 1.0 for key in (
        "team_score_rate", "opponent_team_score_rate", "opponent_identity_rate",
        "played_schedule_coverage_rate", "schedule_team_identity_rate", "schedule_start_time_within_60s_rate",
    ))
    runtime_probe = runtime_espn_schema_probe(as_of)
    status = "PASS" if raw_reconciliation["status"] == "PASS" and quarantine["status"] == "PASS" and identity_pass and runtime_probe["status"] == "PASS" else "FAIL"
    historical_receipt_input = {
        "schema_version": "nba_historical_source_acceptance_v2",
        "market_data": False,
        "history_sha256": sha256_file(history_path),
        "audit_assets": assets,
        "raw_player_to_team_reconciliation": raw_reconciliation,
        "training_quarantine_audit": quarantine,
        "identity_and_schedule_pass": identity_pass,
    }
    historical_receipt_sha256 = sha256_bytes(canonical_json(historical_receipt_input))
    report = {
        "schema_version": "nba_source_acceptance_v2",
        "market_data": False,
        "status": status,
        "canonical_runtime_identity": "ESPN_ID" if status == "PASS" else "NOT_ACCEPTED",
        "official_nba_id_crosswalk": "OPTIONAL_ENRICHMENT_GATE_NOT_BASE_V1_DEPENDENCY",
        "as_of_utc": as_of,
        "history_sha256": historical_receipt_input["history_sha256"],
        "audit_assets": assets,
        "raw_player_to_team_reconciliation": raw_reconciliation,
        "training_quarantine_audit": quarantine,
        "training_table_reconciliation_diagnostic": training_diagnostic,
        "identity_and_schedule_pass": identity_pass,
        "historical_receipt_sha256": historical_receipt_sha256,
        "runtime_fixture_source": runtime_probe,
        "specialist_metrics_required_for_base_v1": False,
    }
    report["receipt_sha256"] = sha256_bytes(canonical_json(report))
    _write(Path(output), report)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--history", required=True)
    parser.add_argument("--seasons", type=int, nargs="+", required=True)
    parser.add_argument("--cache", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--source-pins")
    args = parser.parse_args()
    report = run(args.history, args.seasons, args.cache, args.output, args.as_of, args.source_pins)
    print(json.dumps({
        "status": report["status"],
        "receipt_sha256": report["receipt_sha256"],
        "historical_receipt_sha256": report["historical_receipt_sha256"],
        "raw_reconciliation": report["raw_player_to_team_reconciliation"],
        "quarantine": report["training_quarantine_audit"],
        "identity_and_schedule_pass": report["identity_and_schedule_pass"],
        "runtime_fixture_source": report["runtime_fixture_source"],
    }))


if __name__ == "__main__":
    main()
