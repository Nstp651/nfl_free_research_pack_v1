#!/usr/bin/env python3
"""Read-only NBL/Genius source client for the player-props research pack.

The NBL Rosetta schedule response contains betting metadata at both fixture level
and inside nested season/competition objects. Layers 0-2 must remain market-blind,
so schedule records are rebuilt from strict top-level and nested allow-lists at the
source boundary. No bookmaker/price/odds field is ever returned to the model pack.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any

import requests

BASE_URL = "https://prod.rosetta.nbl.com.au"
DEFAULT_HEADERS = {
    "Accept": "application/json",
    "Accept-Language": "en-AU,en;q=0.9",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Origin": "https://nbl.com.au",
    "Referer": "https://nbl.com.au/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
}
RETRY_STATUS = {429, 500, 502, 503, 504}
MARKET_KEY = re.compile(
    r"(?:odds|sportsbook|bookmaker|moneyline|spread|betting|price|market_line|over_under|total_line)",
    re.I,
)
SAFE_MATCH_KEYS = {
    "id", "external_id", "start_time", "start_time_datetime", "round", "override_round",
    "match_status", "status", "match_type", "match_slug", "match_title",
    "home_score", "away_score", "attendance", "date_updated",
}
SAFE_TEAM_KEYS = {
    "id", "external_id", "name", "team_code", "short_name", "nickname", "team_logo",
}
SAFE_VENUE_KEYS = {"id", "external_id", "name", "city", "state", "country"}
SAFE_SEASON_KEYS = {"id", "external_id", "name", "year", "season_type", "start_date", "end_date"}


class SourceError(RuntimeError):
    pass


@dataclass(frozen=True)
class SourceResponse:
    route: str
    data: Any
    receipt: dict[str, Any]


def _allow_nested(value: Any, keys: set[str]) -> Any:
    if isinstance(value, dict):
        return {k: value.get(k) for k in keys if k in value}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return None


def safe_fixture(row: dict[str, Any]) -> dict[str, Any]:
    """Return the minimal canonical market-blind fixture representation."""
    if not isinstance(row, dict):
        raise SourceError("Malformed NBL fixture row")
    out = {k: row.get(k) for k in SAFE_MATCH_KEYS if k in row}
    out["home_team"] = _allow_nested(row.get("home_team"), SAFE_TEAM_KEYS)
    out["away_team"] = _allow_nested(row.get("away_team"), SAFE_TEAM_KEYS)
    out["venue"] = _allow_nested(row.get("venue"), SAFE_VENUE_KEYS)
    out["season"] = _allow_nested(row.get("season"), SAFE_SEASON_KEYS)
    hits = market_key_hits(out)
    if hits:
        raise SourceError("Safe fixture allow-list retained market fields: " + ", ".join(hits[:10]))
    return out


class RosettaClient:
    def __init__(self, session: requests.Session | None = None, timeout: float = 30.0,
                 max_retries: int = 3, rate_limit_rps: float = 4.0) -> None:
        self.session = session or requests.Session()
        self.timeout = timeout
        self.max_retries = max_retries
        self.min_interval = 1.0 / max(rate_limit_rps, 0.1)
        self._last_request = 0.0

    def _pace(self) -> None:
        wait = self.min_interval - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

    def get(self, route: str, params: dict[str, Any] | None = None,
            raw_array: bool = False) -> SourceResponse:
        if not route.startswith("/"):
            route = "/" + route
        url = BASE_URL + route
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            self._pace()
            try:
                response = self.session.get(url, params=params, headers=DEFAULT_HEADERS, timeout=self.timeout)
                if response.status_code in RETRY_STATUS and attempt < self.max_retries:
                    time.sleep(0.6 * (2 ** attempt))
                    continue
                response.raise_for_status()
                payload = response.json()
                if raw_array:
                    if not isinstance(payload, list):
                        raise SourceError(f"Expected raw array for {route}")
                    data = payload
                    meta = {"count": len(payload)}
                else:
                    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
                        raise SourceError(f"Malformed Rosetta envelope for {route}")
                    data = payload["data"]
                    meta = {
                        "type": payload.get("type"), "count": payload.get("count", len(data)),
                        "fetched": payload.get("fetched"), "ttlRemaining": payload.get("ttlRemaining"),
                        "source": payload.get("source"),
                    }
                return SourceResponse(
                    route=route,
                    data=data,
                    receipt={
                        "provider": "nbl.com.au/Genius Sports Rosetta", "url": response.url,
                        "status_code": response.status_code, **meta,
                    },
                )
            except (requests.RequestException, ValueError, SourceError) as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(0.6 * (2 ** attempt))
                    continue
                break
        raise SourceError(f"NBL source failed {route}: {last_error}")

    def seasons(self) -> SourceResponse:
        return self.get("/get/nbl/seasons")

    def teams(self) -> SourceResponse:
        return self.get("/get/nbl/teams")

    def schedule(self, year: int, season_type: str = "all") -> SourceResponse:
        raw = self.get(f"/get/nbl/matches/in/season/{year}/{season_type}")
        clean = [safe_fixture(row) for row in raw.data]
        return SourceResponse(
            route=raw.route,
            data=clean,
            receipt={
                **raw.receipt,
                "research_allowlist": "SAFE_MATCH_KEYS_V3_DEEP_SEASON",
                "market_fields_exposed_to_model": False,
            },
        )

    def team_stats(self, year: int, season_type: str = "regular") -> SourceResponse:
        return self.get(f"/get/nbl/team/stats/for/season/{year}/{season_type}")

    def roster(self, team_id: str, year: int) -> SourceResponse:
        return self.get(f"/get/nbl/players/for/team/{team_id}/in/season/{year}")

    def players(self, year: int) -> SourceResponse:
        return self.get(f"/get/nbl/players/in/season/{year}")

    def player_stats(self, player_id: str) -> SourceResponse:
        return self.get(f"/get/nbl/statistics/for/player/{player_id}")

    def player_boxscores(self, player_id: str, year: int,
                         season_type: str = "regular") -> SourceResponse:
        return self.get(f"/get/nbl/player_boxscores/for/{player_id}/in/season/{year}/{season_type}")

    def news(self, limit: int = 200) -> SourceResponse:
        return self.get("/get/nbl/news", params={"limit": limit}, raw_array=True)


def market_key_hits(value: Any, path: str = "root") -> list[str]:
    """Fail-safe audit against accidental sportsbook/market ingestion."""
    hits: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if MARKET_KEY.search(str(key)):
                hits.append(f"{path}.{key}")
            hits.extend(market_key_hits(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            hits.extend(market_key_hits(child, f"{path}[{idx}]"))
    return hits
