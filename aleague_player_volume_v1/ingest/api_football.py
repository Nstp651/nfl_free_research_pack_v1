"""API-Football adapter for A-League Player Volume V1.

Provider docs: https://www.api-football.com/documentation-v3
A-League Men league id: 188.

The adapter is intentionally split into:
1. network client;
2. pure parsing/validation functions;
3. canonical publication handled elsewhere.

Tests exercise only pure parsing so CI never spends quota or needs secrets.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ..model_core import ModelIntegrityError
from ..qbase import GoalkeeperMatch, PlayerMatchShooting, TeamMatchShooting


API_BASE = "https://v3.football.api-sports.io"
ALEAGUE_MEN_LEAGUE_ID = 188
MAX_BATCH_FIXTURE_IDS = 20


class ApiFootballError(RuntimeError):
    pass


class ApiFootballClient:
    def __init__(self, api_key: str, *, min_interval_seconds: float = 6.1, timeout_seconds: int = 30):
        if not api_key or not api_key.strip():
            raise ValueError("API-Football key is required")
        self.api_key = api_key.strip()
        self.min_interval_seconds = max(0.0, float(min_interval_seconds))
        self.timeout_seconds = int(timeout_seconds)
        self._last_request_at = 0.0

    def get(self, endpoint: str, params: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.min_interval_seconds:
            time.sleep(self.min_interval_seconds - elapsed)
        query = urlencode({k: v for k, v in (params or {}).items() if v is not None})
        url = f"{API_BASE}/{endpoint.lstrip('/')}"
        if query:
            url += f"?{query}"
        request = Request(url, headers={"x-apisports-key": self.api_key, "Accept": "application/json"})
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # network/HTTP errors are wrapped with no secret echo
            raise ApiFootballError(f"API-Football request failed for {endpoint}") from exc
        finally:
            self._last_request_at = time.monotonic()
        if not isinstance(payload, dict):
            raise ApiFootballError("API-Football returned non-object JSON")
        errors = payload.get("errors")
        if errors:
            raise ApiFootballError(f"API-Football error payload: {errors}")
        return payload

    def league(self, season: int) -> Dict[str, Any]:
        return self.get("leagues", {"id": ALEAGUE_MEN_LEAGUE_ID, "season": season})

    def fixtures(self, season: int) -> Dict[str, Any]:
        return self.get("fixtures", {"league": ALEAGUE_MEN_LEAGUE_ID, "season": season})

    def fixture_batch(self, fixture_ids: Sequence[int]) -> Dict[str, Any]:
        ids = [int(value) for value in fixture_ids]
        if not ids or len(ids) > MAX_BATCH_FIXTURE_IDS:
            raise ValueError(f"fixture batch must contain 1..{MAX_BATCH_FIXTURE_IDS} ids")
        return self.get("fixtures", {"ids": "-".join(str(value) for value in ids)})

    def fixture_players(self, fixture_id: int) -> Dict[str, Any]:
        return self.get("fixtures/players", {"fixture": int(fixture_id)})

    def fixture_statistics(self, fixture_id: int) -> Dict[str, Any]:
        return self.get("fixtures/statistics", {"fixture": int(fixture_id)})


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ModelIntegrityError(f"{label} must be an object")
    return value


def _number(value: Any, label: str, *, allow_none: bool = False) -> Optional[float]:
    if value is None and allow_none:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ModelIntegrityError(f"{label} must be numeric")
    if value < 0:
        raise ModelIntegrityError(f"{label} must be nonnegative")
    return float(value)


def _int_count(value: Any, label: str, *, allow_none: bool = False) -> Optional[int]:
    number = _number(value, label, allow_none=allow_none)
    if number is None:
        return None
    rounded = int(number)
    if abs(number - rounded) > 1e-9:
        raise ModelIntegrityError(f"{label} must be an integer count")
    return rounded


def normalize_kickoff_utc(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ModelIntegrityError("fixture.date is required")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ModelIntegrityError("fixture.date must be ISO-8601") from exc
    if dt.tzinfo is None:
        raise ModelIntegrityError("fixture.date must be timezone-aware")
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def fixture_metadata(fixture_entry: Mapping[str, Any], season: int) -> Dict[str, Any]:
    fixture = _require_mapping(fixture_entry.get("fixture"), "fixture")
    league = _require_mapping(fixture_entry.get("league"), "league")
    teams = _require_mapping(fixture_entry.get("teams"), "teams")
    home = _require_mapping(teams.get("home"), "teams.home")
    away = _require_mapping(teams.get("away"), "teams.away")
    fixture_id = _int_count(fixture.get("id"), "fixture.id")
    league_id = _int_count(league.get("id"), "league.id")
    if league_id != ALEAGUE_MEN_LEAGUE_ID:
        raise ModelIntegrityError(f"unexpected league id {league_id}; expected {ALEAGUE_MEN_LEAGUE_ID}")
    home_id = _int_count(home.get("id"), "teams.home.id")
    away_id = _int_count(away.get("id"), "teams.away.id")
    if home_id == away_id:
        raise ModelIntegrityError("home and away team ids cannot match")
    return {
        "fixture_id": f"apif:{fixture_id}",
        "provider_fixture_id": fixture_id,
        "kickoff_utc": normalize_kickoff_utc(fixture.get("date")),
        "season": f"{season}-{str(season + 1)[-2:]}",
        "home_team_id": f"apif_team:{home_id}",
        "away_team_id": f"apif_team:{away_id}",
        "home_team_name": str(home.get("name") or "").strip(),
        "away_team_name": str(away.get("name") or "").strip(),
    }


def parse_fixture_players(
    metadata: Mapping[str, Any],
    payload: Mapping[str, Any],
) -> Tuple[List[PlayerMatchShooting], List[GoalkeeperMatch], Dict[str, str]]:
    """Convert `/fixtures/players` response into canonical player and keeper rows.

    Returns (player_rows, keeper_rows, player_name_map).
    Null shot values are accepted only for true goalkeeper/non-shooting records and
    converted to zero when the provider gives the rest of the player stat block.
    A missing minutes value means the appearance is not usable and is skipped.
    """
    responses = payload.get("response")
    if not isinstance(responses, list) or not responses:
        raise ModelIntegrityError("fixtures/players response is empty")
    team_ids = {metadata["home_team_id"], metadata["away_team_id"]}
    player_rows: List[PlayerMatchShooting] = []
    keeper_rows: List[GoalkeeperMatch] = []
    names: Dict[str, str] = {}

    for team_block in responses:
        team_block = _require_mapping(team_block, "fixtures/players team block")
        team = _require_mapping(team_block.get("team"), "fixtures/players team")
        provider_team_id = _int_count(team.get("id"), "fixtures/players team.id")
        team_id = f"apif_team:{provider_team_id}"
        if team_id not in team_ids:
            raise ModelIntegrityError(f"player block team {team_id} not in fixture")
        opponent_id = metadata["away_team_id"] if team_id == metadata["home_team_id"] else metadata["home_team_id"]
        players = team_block.get("players")
        if not isinstance(players, list):
            raise ModelIntegrityError("fixtures/players players must be a list")
        for item in players:
            item = _require_mapping(item, "player item")
            player = _require_mapping(item.get("player"), "player")
            provider_player_id = _int_count(player.get("id"), "player.id")
            player_id = f"apif_player:{provider_player_id}"
            names[player_id] = str(player.get("name") or "").strip()
            statistics = item.get("statistics")
            if not isinstance(statistics, list) or not statistics:
                continue
            stat = _require_mapping(statistics[0], "player.statistics[0]")
            games = _require_mapping(stat.get("games"), "games")
            minutes = _number(games.get("minutes"), "games.minutes", allow_none=True)
            if minutes is None:
                continue
            position = str(games.get("position") or "").upper()
            shots = _require_mapping(stat.get("shots") or {}, "shots")
            total_shots = _int_count(shots.get("total"), "shots.total", allow_none=True)
            shots_on = _int_count(shots.get("on"), "shots.on", allow_none=True)
            if total_shots is None and shots_on is None:
                total_shots = 0
                shots_on = 0
            elif total_shots is None or shots_on is None:
                raise ModelIntegrityError(f"partial shot counts for {player_id}")
            row = PlayerMatchShooting(
                fixture_id=str(metadata["fixture_id"]),
                kickoff_utc=str(metadata["kickoff_utc"]),
                season=str(metadata["season"]),
                player_id=player_id,
                team_id=team_id,
                opponent_id=str(opponent_id),
                minutes=float(minutes),
                started=not bool(games.get("substitute", False)),
                shots=int(total_shots),
                shots_on_target=int(shots_on),
            )
            row.validate()
            player_rows.append(row)

            goals = _require_mapping(stat.get("goals") or {}, "goals")
            saves = _int_count(goals.get("saves"), "goals.saves", allow_none=True)
            conceded = _int_count(goals.get("conceded"), "goals.conceded", allow_none=True)
            if position in {"G", "GK"} or saves is not None:
                if saves is None or conceded is None:
                    raise ModelIntegrityError(f"goalkeeper saves/conceded missing for {player_id}")
                # Provider player payload does not expose SoTA directly. Reconstructing
                # saves + conceded is valid for the ordinary shot-on-target accounting
                # path, while reconciliation tests compare this with team SoT faced.
                sota = int(saves) + int(conceded)
                keeper = GoalkeeperMatch(
                    fixture_id=str(metadata["fixture_id"]),
                    kickoff_utc=str(metadata["kickoff_utc"]),
                    season=str(metadata["season"]),
                    player_id=player_id,
                    team_id=team_id,
                    opponent_id=str(opponent_id),
                    minutes=float(minutes),
                    shots_on_target_faced=sota,
                    saves=int(saves),
                    goals_allowed=int(conceded),
                )
                keeper.validate()
                keeper_rows.append(keeper)
    if not player_rows:
        raise ModelIntegrityError("no usable player rows parsed")
    return player_rows, keeper_rows, names


def _stat_value(stats: Iterable[Mapping[str, Any]], stat_type: str) -> Optional[int]:
    for item in stats:
        if str(item.get("type")) == stat_type:
            return _int_count(item.get("value"), f"team stat {stat_type}", allow_none=True)
    return None


def parse_fixture_team_statistics(
    metadata: Mapping[str, Any],
    payload: Mapping[str, Any],
) -> List[TeamMatchShooting]:
    responses = payload.get("response")
    if not isinstance(responses, list) or len(responses) != 2:
        raise ModelIntegrityError("fixtures/statistics must contain exactly two team blocks")
    parsed: Dict[str, Tuple[int, int]] = {}
    for block in responses:
        block = _require_mapping(block, "fixtures/statistics team block")
        team = _require_mapping(block.get("team"), "fixtures/statistics team")
        provider_team_id = _int_count(team.get("id"), "fixtures/statistics team.id")
        team_id = f"apif_team:{provider_team_id}"
        stats = block.get("statistics")
        if not isinstance(stats, list):
            raise ModelIntegrityError("fixtures/statistics statistics must be a list")
        shots = _stat_value(stats, "Total Shots")
        sot = _stat_value(stats, "Shots on Goal")
        if sot is None:  # provider has historically used both labels
            sot = _stat_value(stats, "Shots on Target")
        if shots is None or sot is None:
            raise ModelIntegrityError(f"missing Total Shots / Shots on Goal for {team_id}")
        if sot > shots:
            raise ModelIntegrityError("team SoT cannot exceed shots")
        parsed[team_id] = (shots, sot)
    home_id = str(metadata["home_team_id"])
    away_id = str(metadata["away_team_id"])
    if set(parsed) != {home_id, away_id}:
        raise ModelIntegrityError("team statistics ids do not match fixture")
    home_sh, home_sot = parsed[home_id]
    away_sh, away_sot = parsed[away_id]
    rows = [
        TeamMatchShooting(str(metadata["fixture_id"]), str(metadata["kickoff_utc"]), str(metadata["season"]), home_id, away_id, True, home_sh, home_sot, away_sh, away_sot),
        TeamMatchShooting(str(metadata["fixture_id"]), str(metadata["kickoff_utc"]), str(metadata["season"]), away_id, home_id, False, away_sh, away_sot, home_sh, home_sot),
    ]
    for row in rows:
        row.validate()
    return rows


def reconcile_fixture(
    team_rows: Sequence[TeamMatchShooting],
    player_rows: Sequence[PlayerMatchShooting],
    keeper_rows: Sequence[GoalkeeperMatch],
) -> Dict[str, Any]:
    """Hard/soft reconciliation between provider team and player statistics."""
    if len(team_rows) != 2:
        raise ModelIntegrityError("fixture reconciliation requires two team rows")
    by_team = {row.team_id: row for row in team_rows}
    player_shots: Dict[str, int] = {team_id: 0 for team_id in by_team}
    player_sot: Dict[str, int] = {team_id: 0 for team_id in by_team}
    for row in player_rows:
        if row.team_id not in by_team:
            raise ModelIntegrityError("player team missing from team rows")
        player_shots[row.team_id] += row.shots
        player_sot[row.team_id] += row.shots_on_target
    keeper_saves: Dict[str, int] = {team_id: 0 for team_id in by_team}
    keeper_sota: Dict[str, int] = {team_id: 0 for team_id in by_team}
    for row in keeper_rows:
        if row.team_id not in by_team:
            raise ModelIntegrityError("keeper team missing from team rows")
        keeper_saves[row.team_id] += row.saves
        keeper_sota[row.team_id] += row.shots_on_target_faced

    team_player_deltas = {}
    keeper_sota_deltas = {}
    for team_id, team in by_team.items():
        team_player_deltas[team_id] = {
            "shots": player_shots[team_id] - team.shots_for,
            "sot": player_sot[team_id] - team.sot_for,
        }
        keeper_sota_deltas[team_id] = keeper_sota[team_id] - team.sot_against
    return {
        "team_player_deltas": team_player_deltas,
        "keeper_sota_deltas": keeper_sota_deltas,
        "exact_team_player_match": all(v["shots"] == 0 and v["sot"] == 0 for v in team_player_deltas.values()),
        "exact_keeper_sota_match": all(v == 0 for v in keeper_sota_deltas.values()),
    }


def canonical_dicts(rows: Iterable[Any]) -> List[Dict[str, Any]]:
    return [asdict(row) for row in rows]
