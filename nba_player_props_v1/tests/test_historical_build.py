import json

import pandas as pd
import pytest

from nba_player_props_v1.historical.build_history import audit_history, fetch_asset, normalized_bytes, competition_filter
from nba_player_props_v1.historical.core_normalize import normalize_player_box
from nba_player_props_v1.tests.test_core_normalize import frame


@pytest.mark.parametrize("column,value", [("assists", float("nan")), ("assists", 1.5),
    ("turnovers", float("inf")), ("minutes", -1), ("minutes", "35:90"),
    ("team_id", None), ("field_goals_made", 50)])
def test_malformed_source_rejected(column, value):
    data = frame().astype(object)
    data.loc[0, column] = value
    with pytest.raises(ValueError):
        normalize_player_box(data)


def test_string_false_is_not_true():
    data = frame()
    data["did_not_play"] = ["false", "true"]
    assert len(normalize_player_box(data)) == 1


def test_pinned_asset_tamper_rejected(tmp_path):
    digest = "a" * 64
    (tmp_path / digest).write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="hash mismatch"):
        fetch_asset({"sha256": digest, "bytes": 7}, tmp_path)


def test_future_source_rejected():
    data = normalize_player_box(frame())
    with pytest.raises(ValueError, match="future historical"):
        audit_history(data, as_of="2020-01-01T00:00:00Z")


def test_normalized_serialization_is_stable():
    data = normalize_player_box(frame())
    assert normalized_bytes(data) == normalized_bytes(normalize_player_box(frame()))


def test_all_star_game_is_excluded_even_when_coded_regular_season():
    data = normalize_player_box(frame())
    data["season_type"] = 2
    data["team_id_espn"] = "111353"
    assert competition_filter(data).empty
