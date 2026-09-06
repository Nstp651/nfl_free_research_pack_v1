#!/usr/bin/env python3
"""Build one immutable, market-blind NBL matchup research pack.

One pack is shared by the ASSISTS and REBOUNDS heads. It contains official fixture,
roster, team and player statistical evidence. Current injuries/role/depth-chart
truth is intentionally completed by the live research layer before P_model freeze.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from source_client import RosettaClient, SourceError, market_key_hits

SCHEMA_VERSION = "0.1.0"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def norm_name(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def team_obj(match: dict[str, Any], side: str) -> dict[str, Any]:
    value = match.get(f"{side}_team")
    return value if isinstance(value, dict) else {}


def resolve_fixture(schedule: list[dict[str, Any]], match_id: str | None,
                    home: str | None, away: str | None) -> dict[str, Any]:
    if match_id:
        found = [m for m in schedule if str(m.get("id")) == str(match_id)]
    else:
        nh, na = norm_name(home), norm_name(away)
        found = []
        for m in schedule:
            ht, at = team_obj(m, "home"), team_obj(m, "away")
            if norm_name(ht.get("name")) == nh and norm_name(at.get("name")) == na:
                found.append(m)
            elif norm_name(ht.get("name")) == na and norm_name(at.get("name")) == nh:
                # User order is allowed to be matchup order rather than venue order.
                found.append(m)
    if len(found) != 1:
        raise ValueError(f"Expected exactly one fixture match, found {len(found)}")
    return found[0]


def player_identity(roster_row: dict[str, Any]) -> tuple[str | None, str]:
    p = roster_row.get("player") if isinstance(roster_row.get("player"), dict) else {}
    pid = p.get("id")
    name = " ".join(x for x in (str(p.get("first_name") or "").strip(),
                                  str(p.get("last_name") or "").strip()) if x).strip()
    return (str(pid) if pid else None, name)


def compact_news(news: list[dict[str, Any]], names: list[str], limit: int = 40) -> list[dict[str, Any]]:
    needles = [n.lower() for n in names if len(n.strip()) >= 4]
    out: list[dict[str, Any]] = []
    for article in news:
        hay = " ".join(str(article.get(k) or "") for k in
                       ("title", "excerpt", "sub_headline", "body")).lower()
        if not any(n in hay for n in needles):
            continue
        out.append({k: article.get(k) for k in
                    ("id", "title", "slug", "excerpt", "sub_headline", "byline",
                     "published_date", "featured_image_url") if article.get(k) is not None})
        if len(out) >= limit:
            break
    return out


def build_player_profile(client: RosettaClient, roster_row: dict[str, Any], year: int,
                         prior_year: int, receipts: list[dict[str, Any]]) -> dict[str, Any]:
    pid, name = player_identity(roster_row)
    profile: dict[str, Any] = {
        "player_id": pid,
        "player_name": name,
        "roster": roster_row,
        "season_stats": [],
        "current_game_log": [],
        "prior_nbl_game_log": [],
    }
    if not pid:
        profile["limitations"] = ["Roster row has no player UUID"]
        return profile
    limitations: list[str] = []
    try:
        r = client.player_stats(pid)
        profile["season_stats"] = r.data
        receipts.append(r.receipt)
    except SourceError as exc:
        limitations.append(str(exc))
    try:
        r = client.player_boxscores(pid, year, "regular")
        profile["current_game_log"] = r.data
        receipts.append(r.receipt)
    except SourceError as exc:
        limitations.append(str(exc))
    try:
        r = client.player_boxscores(pid, prior_year, "regular")
        profile["prior_nbl_game_log"] = r.data
        receipts.append(r.receipt)
    except SourceError as exc:
        # New imports / rookies are expected to have no prior NBL log. This becomes
        # an explicit live-research translation trigger rather than fabricated data.
        limitations.append(str(exc))
    if limitations:
        profile["limitations"] = limitations
    return profile


def build_pack(year: int, match_id: str | None, home: str | None, away: str | None,
               client: RosettaClient | None = None) -> dict[str, Any]:
    client = client or RosettaClient()
    receipts: list[dict[str, Any]] = []
    limitations: list[str] = []

    season_r = client.seasons(); receipts.append(season_r.receipt)
    schedule_r = client.schedule(year, "all"); receipts.append(schedule_r.receipt)
    fixture = resolve_fixture(schedule_r.data, match_id, home, away)

    home_team, away_team = team_obj(fixture, "home"), team_obj(fixture, "away")
    for side, team in (("home", home_team), ("away", away_team)):
        if not team.get("id") or not team.get("name"):
            raise ValueError(f"Fixture {side} team missing id/name")

    team_stats_r = client.team_stats(year, "regular"); receipts.append(team_stats_r.receipt)
    try:
        prior_team_stats_r = client.team_stats(year - 1, "regular")
        prior_team_stats = prior_team_stats_r.data
        receipts.append(prior_team_stats_r.receipt)
    except SourceError as exc:
        prior_team_stats = []
        limitations.append(str(exc))

    rosters: dict[str, list[dict[str, Any]]] = {}
    profiles: dict[str, list[dict[str, Any]]] = {}
    news_names = [str(home_team.get("name")), str(away_team.get("name"))]
    for side, team in (("home", home_team), ("away", away_team)):
        rr = client.roster(str(team["id"]), year); receipts.append(rr.receipt)
        rosters[side] = rr.data
        side_profiles = []
        for row in rr.data:
            _, pname = player_identity(row)
            if pname:
                news_names.append(pname)
            side_profiles.append(build_player_profile(client, row, year, year - 1, receipts))
        profiles[side] = side_profiles

    try:
        news_r = client.news(200); receipts.append(news_r.receipt)
        official_news = compact_news(news_r.data, news_names)
    except SourceError as exc:
        official_news = []
        limitations.append(str(exc))

    generated = now_iso()
    core = {
        "schema_version": SCHEMA_VERSION,
        "market_data": False,
        "season_start_year": year,
        "fixture": fixture,
        "season_reference": season_r.data,
        "team_stats_current": team_stats_r.data,
        "team_stats_prior": prior_team_stats,
        "rosters": rosters,
        "player_profiles": profiles,
        "official_news": official_news,
        "limitations": limitations,
        "source_receipts": receipts,
    }
    hits = market_key_hits(core)
    if hits:
        raise ValueError("Market-boundary audit failed: " + ", ".join(hits[:20]))
    revision_material = json.dumps(core, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    pack_revision = hashlib.sha256(revision_material.encode("utf-8")).hexdigest()[:20]
    return {
        **core,
        "generated_at_utc": generated,
        "last_checked_at_utc": generated,
        "pack_revision": pack_revision,
        "research_status": "PARTIAL" if limitations else "STRUCTURED_READY",
        "live_research_required": True,
        "notes": [
            "This pack is pre-market and contains no sportsbook odds/lines/prices.",
            "Structured player history never replaces current role/minutes research.",
            "Players without prior NBL game logs require prior-competition translation.",
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season-year", type=int, required=True,
                    help="Season start year: 2026 means NBL27")
    ap.add_argument("--match-id")
    ap.add_argument("--home")
    ap.add_argument("--away")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    if not args.match_id and not (args.home and args.away):
        ap.error("Provide --match-id or both --home and --away")
    pack = build_pack(args.season_year, args.match_id, args.home, args.away)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(pack, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({
        "ok": True,
        "pack_revision": pack["pack_revision"],
        "fixture_id": pack["fixture"].get("id"),
        "home": team_obj(pack["fixture"], "home").get("name"),
        "away": team_obj(pack["fixture"], "away").get("name"),
        "home_players": len(pack["player_profiles"]["home"]),
        "away_players": len(pack["player_profiles"]["away"]),
        "research_status": pack["research_status"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
