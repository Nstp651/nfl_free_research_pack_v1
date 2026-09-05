#!/usr/bin/env python3
"""Production entrypoint for the NCAA pack builder.

This entrypoint fixes pandas-Series truth evaluation in the base builder and
extends the compact allow-list with cfbfastR fields verified in its matchup
model. The upstream base builder stays small/reviewable; production workflows
invoke this file.
"""
from __future__ import annotations

import build_pack as bp

# Verified in cfbfastR's higher-model matchup implementation. These are the
# highest-value totals inputs missing from the first compact allow-list:
# pass/rush efficiency splits, offensive pass tendency, defensive faced pass
# tendency, and pace. Duplicates are removed while preserving order.
VERIFIED_MATCHUP_METRICS = [
    "EPAplay_off_pass", "EPAplay_def_pass",
    "EPAplay_off_rush", "EPAplay_def_rush",
    "passrate_off", "passrate_def",
    "playsgame_off", "playsgame_def",
]
bp.SUMMARY_METRICS = list(dict.fromkeys(bp.SUMMARY_METRICS + VERIFIED_MATCHUP_METRICS))


def fixed_profile(team_id, name, current_summary, current_ratings, prior_summary,
                  prior_ratings, talent, returning):
    cs = current_summary.get(team_id or "")
    cr = current_ratings.get(team_id or "")
    ps = prior_summary.get(team_id or "")
    pr = prior_ratings.get(team_id or "")
    tr = talent.get(team_id or "")
    rr = returning.get(team_id or "")
    name_row = cs if cs is not None else ps
    return {
        "team_id": team_id,
        "team_name": bp.team_name(name_row, name),
        "current": {
            "available": cs is not None or cr is not None,
            "summary": bp.metric_dict(cs, bp.SUMMARY_METRICS),
            "ratings": bp.metric_dict(cr, bp.RATING_METRICS),
        },
        "prior_season": {
            "available": ps is not None or pr is not None,
            "summary": bp.metric_dict(ps, bp.SUMMARY_METRICS),
            "ratings": bp.metric_dict(pr, bp.RATING_METRICS),
        },
        "preseason": {
            "talent": bp.metric_dict(tr, bp.PRESEASON_METRICS),
            "returning_production": bp.metric_dict(rr, bp.PRESEASON_METRICS),
        },
    }


bp.profile = fixed_profile

if __name__ == "__main__":
    raise SystemExit(bp.main())
