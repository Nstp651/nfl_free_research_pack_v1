from __future__ import annotations

from dataclasses import dataclass

BASE = "https://github.com/sportsdataverse/sportsdataverse-data/releases/download"


@dataclass(frozen=True)
class SourceAsset:
    source: str
    dataset: str
    season_end_year: int
    immutable_id: str
    url: str


def _season(year: int) -> int:
    if not isinstance(year, int) or year < 2002 or year > 2100:
        raise ValueError("season_end_year must be an integer from 2002 to 2100")
    return year


def core_assets(season_end_year: int) -> tuple[SourceAsset, ...]:
    """Return authoritative hoopR/SportsDataverse release paths for one NBA season.

    The SportsDataverse loaders key NBA season files by the season END year.
    Example: 2025-26 is season_end_year=2026.
    """
    y = _season(season_end_year)
    specs = (
        ("player_box", "espn_nba_player_boxscores", f"player_box_{y}.rds"),
        ("team_box", "espn_nba_team_boxscores", f"team_box_{y}.rds"),
        ("schedule", "espn_nba_schedules", f"nba_schedule_{y}.rds"),
        ("play_by_play", "espn_nba_pbp", f"play_by_play_{y}.rds"),
    )
    return tuple(
        SourceAsset(
            source="sportsdataverse",
            dataset=dataset,
            season_end_year=y,
            immutable_id=f"{tag}/{filename}",
            url=f"{BASE}/{tag}/{filename}",
        )
        for dataset, tag, filename in specs
    )


def core_assets_for_range(first_season_end_year: int, last_season_end_year: int) -> tuple[SourceAsset, ...]:
    first, last = _season(first_season_end_year), _season(last_season_end_year)
    if last < first:
        raise ValueError("last season precedes first season")
    out: list[SourceAsset] = []
    for year in range(first, last + 1):
        out.extend(core_assets(year))
    return tuple(out)
