#!/usr/bin/env python3
"""Deterministic Layer 3/4 integration for a frozen NCAA totals P_model.

This module NEVER retrieves odds and NEVER mutates P_model. It consumes:
1. a complete frozen P_model artifact created before market access; and
2. a complete market-board snapshot retrieved after freeze.

It performs exact fixture/line mapping, duplicate-price selection, push-aware
pricing math, freshness classification and ranking. Ambiguous/unmatched
fixtures fail closed instead of fuzzy-matching sportsbook names.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
import math
import re
from pathlib import Path
from typing import Any

from market_math import evaluate_price, side_probabilities
from freeze_receipt import validate_receipt

FROZEN_SCHEMA_VERSION = "1.1.0"


def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def normalize_team(value: str) -> str:
    """Conservative normalization only; intentionally not fuzzy matching."""
    s = str(value).casefold().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def fixture_key(home: str, away: str, commence_time: str) -> tuple[str, str, str]:
    dt = parse_time(commence_time)
    if dt is None:
        raise ValueError("invalid fixture commence_time")
    # Upstream sources are expected to agree on exact kickoff minute. Seconds are
    # removed only to avoid harmless :00 formatting differences.
    minute = dt.replace(second=0, microsecond=0).isoformat()
    return normalize_team(home), normalize_team(away), minute


def validate_frozen(frozen: dict) -> None:
    if frozen.get("schema_version") not in {FROZEN_SCHEMA_VERSION, "1.1.2", "1.1.3"}:
        raise ValueError("unsupported frozen P_model schema")
    if frozen.get("schema_version") == "1.1.3":
        validate_receipt(frozen)
    if frozen.get("p_model_status") != "FROZEN":
        raise ValueError("P_model is not frozen")
    if parse_time(frozen.get("frozen_at")) is None:
        raise ValueError("invalid frozen_at")
    games = frozen.get("games")
    if not isinstance(games, list) or not games:
        raise ValueError("frozen P_model contains no games")
    seen = set()
    for g in games:
        key = fixture_key(g.get("home_team", ""), g.get("away_team", ""), g.get("commence_time", ""))
        if key in seen:
            raise ValueError("duplicate frozen fixture")
        seen.add(key)
        grid = g.get("probability_grid")
        if not isinstance(grid, list) or not grid:
            raise ValueError("frozen fixture missing probability grid")
        lines = set()
        for row in grid:
            line = float(row["line"])
            if line in lines:
                raise ValueError("duplicate frozen total line")
            lines.add(line)
            over = float(row["over"]); push = float(row["push"]); under = float(row["under"])
            if any(not math.isfinite(x) or x < 0 or x > 1 for x in (over, push, under)):
                raise ValueError("invalid frozen probability")
            if abs(over + push + under - 1.0) > 3e-8:
                raise ValueError("frozen probability partition failed")
            if abs(line - round(line)) >= 1e-9 and abs(push) > 1e-12:
                raise ValueError("half-point frozen line has push probability")


def validate_board(board: dict) -> None:
    if board.get("service") != "NCAAF_TOTALS_MARKET_GATEWAY":
        raise ValueError("wrong market service")
    if board.get("sport_key") != "americanfootball_ncaaf":
        raise ValueError("wrong sport key")
    if board.get("region") != "au" or board.get("market_group") != "ncaaf-totals" or board.get("market_key") != "totals":
        raise ValueError("wrong market family")
    if not re.fullmatch(r"[a-f0-9]{16}", str(board.get("board_revision", ""))):
        raise ValueError("invalid board revision")
    if parse_time(board.get("retrieved_at")) is None:
        raise ValueError("invalid market retrieved_at")
    games = board.get("games")
    if not isinstance(games, list):
        raise ValueError("invalid market games")


def freshness(last_update: Any, retrieved_at: str) -> tuple[str, float | None]:
    retrieved = parse_time(retrieved_at)
    updated = parse_time(last_update)
    if retrieved is None or updated is None:
        return "UNKNOWN", None
    age = max(0.0, (retrieved - updated).total_seconds() / 60.0)
    if age <= 30.0:
        return "CURRENT", age
    if age <= 90.0:
        return "AGING", age
    return "STALE", age


def grid_index(game: dict) -> dict[float, dict]:
    return {float(r["line"]): r for r in game["probability_grid"]}


def candidate_sort_key(c: dict) -> tuple:
    # Highest price, then newest update, then bookmaker key alphabetically.
    updated = parse_time(c.get("last_update"))
    timestamp = updated.timestamp() if updated else float("-inf")
    return (-float(c["odds"]), -timestamp, str(c["bookmaker_key"]))


def integrate(frozen: dict, board: dict) -> dict:
    validate_frozen(frozen)
    validate_board(board)
    if parse_time(board["retrieved_at"]) < parse_time(frozen["frozen_at"]):
        raise ValueError("Market board predates freeze")

    market_by_fixture: dict[tuple[str, str, str], dict] = {}
    for g in board["games"]:
        key = fixture_key(g.get("home_team", ""), g.get("away_team", ""), g.get("commence_time", ""))
        if key in market_by_fixture:
            raise ValueError("duplicate market fixture after canonicalization")
        market_by_fixture[key] = g

    selections = []
    unmatched = []
    for fg in frozen["games"]:
        key = fixture_key(fg["home_team"], fg["away_team"], fg["commence_time"])
        mg = market_by_fixture.get(key)
        if mg is None:
            unmatched.append({
                "game_id": fg.get("game_id"),
                "home_team": fg["home_team"],
                "away_team": fg["away_team"],
                "commence_time": fg["commence_time"],
                "reason": "NO_EXACT_MARKET_FIXTURE_MATCH",
            })
            continue
        index = grid_index(fg)
        candidates: dict[tuple[str, float], list[dict]] = {}
        for book in mg.get("bookmakers", []):
            bkey = str(book.get("key") or "")
            btitle = str(book.get("title") or bkey)
            last = book.get("last_update")
            for outcome in book.get("totals", []):
                side = str(outcome.get("name", ""))
                if side not in {"Over", "Under"}:
                    continue
                try:
                    line = float(outcome["point"]); odds = float(outcome["price"])
                except (KeyError, TypeError, ValueError):
                    continue
                if line not in index or not math.isfinite(odds) or odds <= 1.0:
                    continue
                candidates.setdefault((side, line), []).append({
                    "side": side, "line": line, "odds": odds,
                    "bookmaker_key": bkey, "bookmaker": btitle,
                    "last_update": last,
                })

        for (side, line), rows in candidates.items():
            best = sorted(rows, key=candidate_sort_key)[0]
            probrow = index[line]
            p_win, p_push = side_probabilities(probrow, side)
            ev = evaluate_price(p_win, p_push, best["odds"])
            fresh, age = freshness(best.get("last_update"), board["retrieved_at"])
            selections.append({
                "game_id": fg.get("game_id"),
                "event_id": mg.get("event_id"),
                "home_team": fg["home_team"],
                "away_team": fg["away_team"],
                "commence_time": fg["commence_time"],
                "side": side,
                "line": line,
                "bookmaker_key": best["bookmaker_key"],
                "bookmaker": best["bookmaker"],
                "odds": best["odds"],
                "last_update": best.get("last_update"),
                "freshness": fresh,
                "age_minutes": None if age is None else round(age, 3),
                **{k: (round(v, 10) if isinstance(v, float) and math.isfinite(v) else v) for k, v in asdict(ev).items()},
                "confidence": fg.get("confidence"),
                "fragility": fg.get("fragility"),
                "frozen_thesis": fg.get("frozen_thesis"),
            })

    # BET eligibility excludes unusable freshness and non-positive push-aware ROI.
    eligible = [s for s in selections if s["expected_roi"] > 0 and s["price_edge"] > 0 and s["freshness"] in {"CURRENT", "AGING"}]
    fragility_order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
    eligible.sort(key=lambda s: (
        -float(s["expected_roi"]),
        -float(s["price_edge"]),
        fragility_order.get(str(s.get("fragility", "")).upper(), 9),
        0 if s["freshness"] == "CURRENT" else 1,
        str(s["home_team"]), str(s["away_team"]), str(s["side"]), float(s["line"]),
    ))
    for rank, s in enumerate(eligible, 1):
        s["rank"] = rank

    return {
        "schema_version": "1.1.0",
        "p_model_status": frozen["p_model_status"],
        "frozen_at": frozen["frozen_at"],
        "board_revision": board["board_revision"],
        "market_retrieved_at": board["retrieved_at"],
        "market_group": "ncaaf-totals",
        "matched_selection_count": len(selections),
        "eligible_positive_count": len(eligible),
        "unmatched_fixtures": unmatched,
        "ranked_positive_selections": eligible,
        "all_mapped_selections": selections,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frozen", required=True, help="Complete pre-market frozen P_model JSON")
    ap.add_argument("--board", required=True, help="Complete post-freeze market board JSON")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    result = integrate(json.loads(Path(args.frozen).read_text()), json.loads(Path(args.board).read_text()))
    Path(args.output).write_text(json.dumps(result, indent=2, sort_keys=True))
    print(f"MARKET_INTEGRATION selections={result['matched_selection_count']} positives={result['eligible_positive_count']} board={result['board_revision']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
