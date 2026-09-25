from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import sys

from tennis_v1.data_pipeline import normalize_results, write_pack
from tennis_v1.data_sources import UCI2013ServeStatsSource, ValuebetennisSource


def build(years: list[int], output: Path):
    vb = ValuebetennisSource()
    result_frames = [vb.fetch_year(year) for year in years]
    matches = normalize_results(result_frames)
    serve_stats = UCI2013ServeStatsSource().fetch()
    decision = write_pack(output, matches, serve_stats, current_year=max(years))
    return decision


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("rebuild", "refresh", "probe", "zero-upload"):
        p = sub.add_parser(name)
        p.add_argument("--output", required=True)
        p.add_argument("--through-year", type=int, default=datetime.now(timezone.utc).year)
    args = parser.parse_args()
    output = Path(args.output)
    years = list(range(2021, args.through_year + 1)) if args.cmd == "rebuild" else [args.through_year]
    decision = build(years, output)
    report = asdict(decision)
    report["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    report_path = output / "ZERO_UPLOAD_TEST.json"
    report_path.write_text(
        json.dumps(report, indent=2, default=str, sort_keys=True), encoding="utf-8"
    )
    print(f"ZERO_UPLOAD_TEST={decision.zero_upload_status}")
    for blocker in decision.blockers:
        print(f"BLOCKER={blocker}")
    if args.cmd == "zero-upload" and decision.zero_upload_status != "PASS":
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
