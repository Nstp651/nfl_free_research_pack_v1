#!/usr/bin/env python3
"""Production entrypoint for the NCAA pack builder.

Keeps the branch runnable while preserving the original builder source for review.
The only override here fixes pandas-Series truth evaluation in team-name fallback.
"""
from __future__ import annotations

import build_pack as bp


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
