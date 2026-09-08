"""Run hash-verified conditional A-League distribution backtests.

This command intentionally cannot emit a production-ready verdict. It consumes
canonical historical assets, verifies every manifest asset hash, builds strict
pre-target statistical priors, and reports distribution/calibration diagnostics.
The realised participant set is still used to decide which player rows are
scored, so selection-edge acceptance remains blocked by design.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from aleague_player_volume_v1.backtest import score_forecasts, select_dispersion_holdout
from aleague_player_volume_v1.historical_replay import generate_conditional_distribution_replay
from aleague_player_volume_v1.publication import verify_manifest
from aleague_player_volume_v1.qbase import GoalkeeperMatch, PlayerMatchShooting, TeamMatchShooting


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise RuntimeError(f"{path}:{number} must contain JSON object")
        rows.append(value)
    return rows


def load_season(data_root: Path, season: str):
    root = data_root / season
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        raise RuntimeError(f"manifest missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("model") != "ALEAGUE_PLAYER_VOLUME_V1" or manifest.get("season") != season:
        raise RuntimeError(f"unexpected manifest identity: {manifest_path}")
    verify_manifest(data_root.parent, manifest)
    players = [PlayerMatchShooting(**row) for row in read_jsonl(root / "player_match_shooting.jsonl")]
    teams = [TeamMatchShooting(**row) for row in read_jsonl(root / "team_match_shooting.jsonl")]
    keepers = [GoalkeeperMatch(**row) for row in read_jsonl(root / "goalkeeper_match.jsonl")]
    return manifest, players, teams, keepers


def parse_candidates(value: str) -> list[float]:
    out = sorted({float(item.strip()) for item in value.split(",") if item.strip()})
    if not out or any(item <= 0 for item in out):
        raise argparse.ArgumentTypeError("dispersion candidates must be positive comma-separated numbers")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default="aleague_player_volume_v1/data/api_football")
    parser.add_argument("--seasons", required=True, help="comma-separated canonical season labels, e.g. 2024-25,2025-26")
    parser.add_argument("--validation-start", default=None, help="optional UTC ISO timestamp for train-only dispersion selection")
    parser.add_argument("--shots-dispersion-candidates", type=parse_candidates, default=parse_candidates("0.75,1,1.5,2,3,4,6,10,20"))
    parser.add_argument("--sot-dispersion-candidates", type=parse_candidates, default=parse_candidates("0.75,1,1.5,2,3,4,6,10,20"))
    parser.add_argument("--saves-dispersion-candidates", type=parse_candidates, default=parse_candidates("0.75,1,1.5,2,3,4,6,10,20"))
    parser.add_argument("--output", default="aleague_player_volume_v1/data/backtests/conditional_distribution_backtest.json")
    args = parser.parse_args()

    data_root = Path(args.data_root)
    seasons = [value.strip() for value in args.seasons.split(",") if value.strip()]
    if not seasons:
        raise RuntimeError("at least one season required")

    manifests = []
    player_rows = []
    team_rows = []
    keeper_rows = []
    for season in seasons:
        manifest, players, teams, keepers = load_season(data_root, season)
        manifests.append({
            "season": season,
            "manifest_content_sha256": manifest.get("manifest_content_sha256"),
            "source_receipt": manifest.get("source_receipt"),
        })
        player_rows.extend(players)
        team_rows.extend(teams)
        keeper_rows.extend(keepers)

    replay = generate_conditional_distribution_replay(player_rows, team_rows, keeper_rows)
    score = score_forecasts(replay["observations"])
    dispersion = {}
    if args.validation_start:
        candidate_map = {
            "SHOTS": args.shots_dispersion_candidates,
            "SOT": args.sot_dispersion_candidates,
            "SAVES": args.saves_dispersion_candidates,
        }
        for head, candidates in candidate_map.items():
            dispersion[head] = select_dispersion_holdout(
                replay["observations"],
                head=head,
                validation_start_utc=args.validation_start,
                candidates=candidates,
            )

    report = {
        "schema_version": "aleague_player_volume_conditional_backtest_report_v1",
        "model": "ALEAGUE_PLAYER_VOLUME_V1",
        "seasons": seasons,
        "source_manifests": manifests,
        "market_data_used": False,
        "replay_mode": replay["replay_mode"],
        "selection_integrity": replay["selection_integrity"],
        "participant_set_source": replay["participant_set_source"],
        "parameter_information_cutoff": replay["parameter_information_cutoff"],
        "allowed_uses": replay["allowed_uses"],
        "prohibited_uses": replay["prohibited_uses"],
        "production_edge_acceptance": "BLOCKED_REQUIRES_FULL_PREMATCH_REPLAY",
        "row_counts": {
            "player_match_shooting": len(player_rows),
            "team_match_shooting": len(team_rows),
            "goalkeeper_match": len(keeper_rows),
            "forecast_observations": len(replay["observations"]),
        },
        "score": score,
        "dispersion_holdout": dispersion,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "PASS_DIAGNOSTIC_ONLY",
        "output": str(output),
        "production_edge_acceptance": report["production_edge_acceptance"],
        "rows": report["row_counts"],
    }, indent=2))


if __name__ == "__main__":
    main()
