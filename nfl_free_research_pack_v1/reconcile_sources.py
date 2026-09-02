"""Reconcile generated records to real input rows, without calling aggregators.

This validates source interpretation and joins, not current role truth, a GPT run,
Cloudflare deployment, or a historical point-in-time backtest.
"""
from datetime import datetime, timezone
import importlib.metadata
import os
import platform
import pandas as pd


def number(value):
    return None if pd.isna(value) else round(float(value), 4)


def same(actual, expected, context):
    assert actual == expected, f"{context}: output={actual!r}; source={expected!r}"


def regular(frame):
    result = frame
    for key in ("season_type", "game_type"):
        if key in result:
            result = result[result[key] == "REG"]
    return result


def verify(inputs, packs):
    preferred = [{"NE", "SEA"}, {"SF", "LA"}]
    chosen = [p for teams in preferred for p in packs
              if {p["fixture"]["home_team"], p["fixture"]["away_team"]} == teams]
    chosen += [p for p in packs if p not in chosen][:max(0, 2 - len(chosen))]
    assert len(chosen) >= 2, "Two real fixtures required for acceptance"
    report = {"result": "PASS", "mode": "REAL_SOURCE_RECONCILIATION",
              "tested_at_utc": datetime.now(timezone.utc).isoformat(),
              "build_commit": os.getenv("SOURCE_COMMIT", os.getenv("GITHUB_SHA")), "python": platform.python_version(),
              "workflow_run_id": os.getenv("GITHUB_RUN_ID"),
              "deployment_verified": False, "gpt_dry_runs_verified": False,
              "games": [], "ftn_join_counts": {}, "dependencies": {}}
    for package in ("nflreadpy", "pandas", "numpy", "polars", "pyarrow"):
        report["dependencies"][package] = importlib.metadata.version(package)

    # Audit exact eligible charted target joins, including nullable observations.
    joins = {}
    for year in inputs["years"][:-1]:
        pbp, ftn = regular(inputs["pbp"][year]), inputs["ftn"][year]
        if pbp.empty or ftn.empty:
            joins[year] = pd.DataFrame()
            continue
        for flag in ("no_play", "two_point_attempt"):
            if flag in pbp:
                pbp = pbp[pbp[flag] == 0]
        if "pass_attempt" in pbp:
            pbp = pbp[pbp.pass_attempt == 1]
        targets = pbp[pbp.receiver_player_id.notna()]
        merged = targets.merge(ftn, left_on=["game_id", "play_id"],
            right_on=["nflverse_game_id", "nflverse_play_id"], validate="one_to_one",
            suffixes=("", "_ftn"))
        joins[year] = merged
        report["ftn_join_counts"][str(year)] = {"raw_charting_rows": len(ftn),
            "eligible_regular_season_pbp_targets": len(targets),
            "joined_regular_season_targets": len(merged),
            "unmatched_pbp_targets": len(targets) - len(merged),
            "note": "Raw charting may include playoffs; joins use regular-season targets only."}

    roster = inputs["current_roster"]
    depth = inputs["current_depth"]
    for pack in chosen[:2]:
        game = {"game_id": pack["game_id"], "pack_revision": pack["pack_revision"],
                "players": len(pack["players"]), "teams": {}, "rookies": [],
                "transfers": [], "player_checks": 0, "ftn_checks": 0,
                "ngs_identity_matches": [], "missing_prior_ngs": 0}
        week = pack["fixture"]["week"]
        if week == 1:
            same(pack["data_state"]["current_season_data_through_week"], None, "Week 1 cutoff")
        for player in pack["players"]:
            pid, name, team = player["player_id"], player["player_name"], player["current_team"]
            rows = roster[(roster.gsis_id == pid) & (roster.team == team)] if pid else roster[
                (roster.full_name == name) & (roster.team == team)]
            assert len(rows), f"No current roster identity: {name} {team}"
            row = rows.iloc[-1]
            same(player["rookie_flag"], bool(row.years_exp == 0) if pd.notna(row.years_exp) else None, name)
            if player["rookie_flag"]:
                game["rookies"].append({"name": name, "team": team})
            if week == 1:
                assert all(v is None for v in player["current_season_to_date"].values()), name
            if not depth.empty and "dt" in depth:
                td = depth[depth.team == team]
                latest = td[td.dt == td.dt.max()]
                matching = latest[latest.gsis_id == pid] if pid else latest.iloc[:0]
                same(player["current_depth"]["rank"],
                     number(matching.iloc[-1].pos_rank) if len(matching) else None, f"{name} depth")
            for year, historical in player["historical"].items():
                y = int(year)
                source = regular(inputs["player_stats"][y])
                source = source[source.player_id == pid]
                output = historical["season_receiving"]
                if output is not None:
                    assert len(source), f"No receiving source for {name}"
                    for field in ("targets", "receptions", "receiving_yards"):
                        same(output[field], number(source[field].sum(min_count=1)), f"{name} {year} {field}")
                        game["player_checks"] += 1
                    teams = sorted(source.team.dropna().unique().tolist())
                    same(output["source_teams"], teams, f"{name} prior teams")
                    if y == inputs["season"] - 1:
                        same(player["team_change_since_prior_season"], team not in teams, f"{name} transfer")
                        if player["team_change_since_prior_season"]:
                            game["transfers"].append({"name": name, "current_team": team, "source_teams": teams})
                else:
                    assert source.empty, f"Omitted receiving source: {name} {year}"
                joined = joins[y]
                charted = joined[joined.receiver_player_id == pid] if len(joined) else joined
                chart = historical["ftn_charting"]
                same(chart["charted_targets"] if chart else 0, len(charted), f"{name} FTN count")
                if chart:
                    for field in [c for c in charted if c.startswith("is_")]:
                        output_field = field.removeprefix("is_") + "_rate"
                        if output_field not in chart:
                            continue
                        # Explicit true/false mapping keeps missing or unrecognized values unknown.
                        values = charted[field].astype("string").str.lower().map(
                            {"true": 1, "false": 0, "1": 1, "0": 0, "1.0": 1, "0.0": 0})
                        same(chart[output_field], number(values.mean()), f"{name} {year} {field}")
                        same(chart[field.removeprefix("is_") + "_observed_targets"],
                             int(values.notna().sum()), f"{name} FTN denominator")
                        game["ftn_checks"] += 2
                ngs = regular(inputs["ngs_receiving"][y])
                if len(ngs) and (ngs.week == 0).any():
                    ngs = ngs[ngs.week == 0]
                source_ngs = ngs[ngs.player_gsis_id == pid] if len(ngs) else ngs
                output_ngs = historical["next_gen_receiving"]
                same(output_ngs is not None, len(source_ngs) > 0, f"{name} NGS coverage")
                if output_ngs:
                    for field in ("targets", "receptions"):
                        same(output_ngs[field], number(source_ngs[field].sum(min_count=1)), f"{name} NGS {field}")
                    if y == inputs["season"] - 1:
                        game["ngs_identity_matches"].append({"player_id": pid, "roster_name": name,
                            "ngs_name": output_ngs["player_name"]})
                elif y == inputs["season"] - 1:
                    game["missing_prior_ngs"] += 1
        for team, context in pack["team_context"].items():
            team_checks = {}
            for year, output in context["historical"].items():
                stats = regular(inputs["team_stats"][int(year)])
                stats = stats[stats.team == team]
                if len(stats):
                    attempts = int(stats.attempts.sum())
                    games = int(stats.week.nunique())
                    same(output["pass_attempts_per_game"], round(attempts / games, 4), f"{team} {year} attempts")
                    same(output["completions_per_game"], round(float(stats.completions.sum()) / games, 4), f"{team} completions")
                    team_checks[year] = {"games": games, "attempts": attempts,
                                         "completions": int(stats.completions.sum())}
            game["teams"][team] = team_checks
        report["games"].append(game)
    return report
