from nba_player_props_v1.historical.source_catalog import core_assets, core_assets_for_range


def test_core_asset_paths_match_hoopr_release_contract():
    assets = {row.dataset: row for row in core_assets(2026)}
    assert assets["player_box"].url.endswith("/espn_nba_player_boxscores/player_box_2026.rds")
    assert assets["team_box"].url.endswith("/espn_nba_team_boxscores/team_box_2026.rds")
    assert assets["schedule"].url.endswith("/espn_nba_schedules/nba_schedule_2026.rds")
    assert assets["play_by_play"].url.endswith("/espn_nba_pbp/play_by_play_2026.rds")


def test_season_range_is_complete_and_ordered():
    assets = core_assets_for_range(2024, 2026)
    assert len(assets) == 12
    assert [row.season_end_year for row in assets[:4]] == [2024] * 4
    assert [row.season_end_year for row in assets[-4:]] == [2026] * 4


def test_invalid_season_range_rejected():
    try:
        core_assets_for_range(2026, 2025)
    except ValueError as exc:
        assert "precedes" in str(exc)
    else:
        raise AssertionError("invalid range must fail")
