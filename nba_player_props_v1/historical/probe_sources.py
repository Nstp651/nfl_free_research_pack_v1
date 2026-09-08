"""Read-only connectivity evidence; successful HTTP is never source acceptance."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.request import Request, urlopen

from nba_player_props_v1.source_receipt import canonical_json, sha256_bytes

URLS = {
    "current_schedule": "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json",
    # Published nba_api endpoint example: connectivity only, NOT current freshness.
    "player_track_sample": "https://stats.nba.com/stats/boxscoreplayertrackv3?GameID=0021700807",
}
TRACK_METRICS = ("touches", "passes", "secondary_assists", "rebound_chances",
                 "offensive_rebound_chances", "defensive_rebound_chances")
OTHER_METRICS = ("potential_assists", "time_of_possession", "drives", "lineup_creation",
                 "teammate_finishing", "contested_rebounds", "lineup_rebound_share",
                 "opponent_miss_environment", "shot_location_environment", "box_outs")


def probe(item):
    name, url = item
    result = {"name": name, "url": url, "checked_at_utc": datetime.now(timezone.utc).isoformat()}
    try:
        request = Request(url, headers={"User-Agent": "NBA-V1-source-audit/1.0", "Accept": "application/json"})
        with urlopen(request, timeout=25) as response:
            raw = response.read()
            json.loads(raw)
            result.update(status="RECEIVED_JSON_NOT_ACCEPTED", http_status=response.status,
                          bytes=len(raw), sha256=sha256_bytes(raw))
    except Exception as exc:
        result.update(status="BLOCKED", error_type=type(exc).__name__, reason=str(exc))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    with ThreadPoolExecutor(max_workers=2) as pool:
        probes = dict(zip(URLS, pool.map(probe, URLS.items())))
    registry = {}
    for name in TRACK_METRICS + OTHER_METRICS:
        tracking = name in TRACK_METRICS
        status = ("BLOCKED" if probes["player_track_sample"]["status"] == "BLOCKED" else "PARTIAL") if tracking else "UNAVAILABLE"
        registry[name] = {"status": status,
            "source": URLS["player_track_sample"] if tracking else "audited SportsDataverse core box only",
            "scope": "connectivity probe only" if tracking else "absent from core; alternative sources not yet audited",
            "seasons_available": None, "row_coverage": None, "player_coverage": None,
            "game_coverage": None, "null_rate": None, "schema_stability": "NOT_VERIFIED",
            "identity_reconciliation": "NOT_VERIFIED", "current_season_freshness": "NOT_VERIFIED",
            "historical_consistency": "NOT_VERIFIED", "production_feature": False,
            "reason": "No accepted game-level historical/runtime enrichment dataset; never zero-impute as evidence"}
    report = {"schema_version": "nba_specialist_probe_v1", "market_data": False,
        "source_acceptance": "NOT_ACCEPTED", "probes": probes, "specialist_metrics": registry}
    report["receipt_sha256"] = sha256_bytes(canonical_json(report))
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_bytes(canonical_json(report) + b"\n")
    print(json.dumps(probes))


if __name__ == "__main__":
    main()
