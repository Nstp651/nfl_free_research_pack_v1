"""Content-addressed SportsDataverse build. Discovery never implies acceptance.

Capture pins once, then rebuild with --manifest. Raw transport drift is accepted only
when an exact allowlisted byte-count/SHA variant is present; the normalized-history
SHA remains the semantic authority. Raw source tables never become model features;
only the normalizer allowlist does.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import subprocess
from urllib.request import urlopen

import pandas as pd
import pyreadr

from nba_player_props_v1.historical.core_normalize import normalize_player_box
from nba_player_props_v1.historical.source_catalog import core_assets
from nba_player_props_v1.source_receipt import canonical_json, sha256_bytes, sha256_file

NBA_ESPN_TEAMS = {str(i) for i in range(1, 31)}


def competition_filter(frame):
    # All-Star exhibitions use season_type=2 upstream; season_type alone is unsafe.
    return frame[frame.season_type.isin([2, 3]) &
                 frame.team_id_espn.isin(NBA_ESPN_TEAMS) &
                 frame.opponent_team_id_espn.isin(NBA_ESPN_TEAMS)].copy()


def write_json(path, value):
    Path(path).write_bytes(canonical_json(value) + b"\n")


def _transport_variants(asset):
    variants = []
    primary_sha = str(asset.get("sha256") or "")
    primary_bytes = asset.get("bytes")
    if primary_sha:
        if len(primary_sha) != 64 or not isinstance(primary_bytes, int) or primary_bytes <= 0:
            raise ValueError("invalid primary transport pin")
        variants.append({"sha256": primary_sha, "bytes": primary_bytes, "status": "PRIMARY_PIN"})
    for raw in asset.get("allowed_transport_variants") or []:
        digest = str(raw.get("sha256") or "")
        size = raw.get("bytes")
        if len(digest) != 64 or not isinstance(size, int) or size <= 0:
            raise ValueError("invalid allowed transport variant")
        variants.append({"sha256": digest, "bytes": size, "status": "ALLOWLISTED_TRANSPORT_VARIANT"})
    pairs = [(x["sha256"], x["bytes"]) for x in variants]
    if len(set(pairs)) != len(pairs):
        raise ValueError("duplicate transport variant pin")
    return variants


def fetch_asset(asset, cache):
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    variants = _transport_variants(asset)
    primary = variants[0] if variants else None
    expected = primary["sha256"] if primary else None
    path = cache / (expected or f"{asset['dataset']}_{asset['season_end_year']}.rds")
    if not path.exists():
        with urlopen(asset["url"], timeout=120) as response:
            raw = response.read()
        path.write_bytes(raw)
    digest, size = sha256_file(path), path.stat().st_size
    matched = next((x for x in variants if x["sha256"] == digest and x["bytes"] == size), None)
    if variants and not matched:
        expected_text = ",".join(f"{x['bytes']}:{x['sha256']}" for x in variants)
        raise ValueError(
            "pinned upstream bytes/hash mismatch: "
            f"dataset={asset.get('dataset')} season={asset.get('season_end_year')} "
            f"url={asset.get('url')} allowed_variants={expected_text} "
            f"actual_bytes={size} actual_sha256={digest}"
        )
    addressed = cache / digest
    if not addressed.exists():
        addressed.write_bytes(path.read_bytes())
    receipt = {
        **asset,
        "sha256": digest,
        "bytes": size,
        "transport_pin_status": matched["status"] if matched else "UNPINNED_DISCOVERY",
        "primary_pin_sha256": primary["sha256"] if primary else None,
        "primary_pin_bytes": primary["bytes"] if primary else None,
    }
    return addressed, receipt


def normalized_bytes(frame):
    return frame.to_csv(index=False, lineterminator="\n", float_format="%.12g").encode()


def audit_history(frame, *, as_of):
    cutoff = pd.Timestamp(as_of)
    if cutoff.tzinfo is None:
        raise ValueError("as_of requires timezone")
    if (frame.game_start_utc > cutoff).any():
        raise ValueError("future historical game timestamp")
    if frame.duplicated(["game_id_espn", "player_id_espn"]).any():
        raise ValueError("duplicate canonical player-game")
    for _, game in frame.groupby("game_id_espn"):
        if game.game_start_utc.nunique() != 1 or game.team_id_espn.nunique() != 2:
            raise ValueError("incomplete or inconsistent game identity")
        if set(game.team_id_espn) != set(game.opponent_team_id_espn):
            raise ValueError("opponent identity mismatch")
    return {
        "canonical_espn_identity": "PASS", "nba_crosswalk": "NOT_RUN",
        "duplicate_canonical_player_games": 0,
        "timestamp_non_null_rate": float(frame.game_start_utc.notna().mean()),
        "future_timestamp_audit": "PASS",
        "rows_by_season": {str(int(s)): {"rows": len(g), "games": g.game_id_espn.nunique(),
            "players": g.player_id_espn.nunique(), "teams": g.team_id_espn.nunique()}
            for s, g in frame.groupby("season")},
    }


def build(manifest, cache, output, *, as_of, builder_commit):
    assets, frames = [], []
    for asset in manifest["assets"]:
        path, receipt = fetch_asset(asset, cache)
        if receipt["dataset"] != "player_box":
            raise ValueError("only player_box accepted by this build stage")
        source = pyreadr.read_r(str(path))[None]
        normalized = normalize_player_box(source)
        if set(normalized.season.astype(int)) != {asset["season_end_year"]}:
            raise ValueError("source season mismatch")
        # NBA regular season and playoffs only; preseason and exhibitions excluded.
        normalized = competition_filter(normalized)
        frames.append(normalized)
        assets.append({**receipt, "source_rows": len(source), "accepted_rows": len(normalized),
                       "excluded_rows": len(source) - len(normalized)})
    frame = pd.concat(frames, ignore_index=True).sort_values(
        ["game_start_utc", "game_id_espn", "team_id_espn", "player_id_espn"]).reset_index(drop=True)
    audit = audit_history(frame, as_of=as_of)
    raw = normalized_bytes(frame)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "player_games.csv").write_bytes(raw)
    pins = {"schema_version": manifest.get("schema_version", "nba_source_pins_v1"), "assets": assets}
    write_json(output / "source_pins.json", pins)
    receipt = {"schema_version": "nba_historical_build_v1", "market_data": False,
        "builder_commit": builder_commit, "as_of_utc": as_of,
        "upstream_assets": assets, "normalized_sha256": sha256_bytes(raw),
        "latest_completed_game_utc": frame.game_start_utc.max().isoformat(),
        "audit": audit, "source_acceptance": "NOT_ACCEPTED",
        "pending_gates": ["independent_box_reconciliation", "nba_identity_crosswalk",
                          "current_schedule_freshness", "specialist_availability_audit"]}
    receipt["receipt_sha256"] = sha256_bytes(canonical_json(receipt))
    write_json(output / "historical_build_receipt.json", receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest")
    parser.add_argument("--seasons", type=int, nargs="+")
    parser.add_argument("--cache", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--as-of", required=True)
    args = parser.parse_args()
    if bool(args.manifest) == bool(args.seasons):
        parser.error("choose pinned --manifest or discovery --seasons")
    manifest = json.loads(Path(args.manifest).read_text()) if args.manifest else {
        "assets": [asdict(core_assets(s)[0]) for s in sorted(set(args.seasons))]}
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    receipt = build(manifest, args.cache, args.output, as_of=args.as_of, builder_commit=commit)
    print(json.dumps({"normalized_sha256": receipt["normalized_sha256"], "audit": receipt["audit"],
                      "source_acceptance": receipt["source_acceptance"]}))


if __name__ == "__main__":
    main()
