import json
from pathlib import Path

import pandas as pd

import build_pack as bp


def test_fbs_week_keeps_only_fbs_vs_fbs_and_target_week():
    df = pd.DataFrame([
        {"season": 2026, "week": 2, "game_id": 1, "fbs_game": True, "season_type": "regular", "start_date": "2026-09-05T00:00:00Z"},
        {"season": 2026, "week": 2, "game_id": 2, "fbs_game": False, "season_type": "regular", "start_date": "2026-09-05T01:00:00Z"},
        {"season": 2026, "week": 3, "game_id": 3, "fbs_game": True, "season_type": "regular", "start_date": "2026-09-12T00:00:00Z"},
    ])
    out = bp.fbs_week(df, 2026, 2)
    assert out["game_id"].tolist() == [1]


def test_latest_rows_enforces_cutoff():
    df = pd.DataFrame([
        {"team_id": 10, "season": 2026, "through_week": 1, "EPAplay_off": .1},
        {"team_id": 10, "season": 2026, "through_week": 2, "EPAplay_off": .2},
        {"team_id": 20, "season": 2026, "through_week": 1, "EPAplay_off": .3},
    ])
    rows, through = bp.latest_rows(df, 2026, 1)
    assert through == 1
    assert rows["10"]["EPAplay_off"] == .1
    assert rows["20"]["EPAplay_off"] == .3


def test_market_key_audit_rejects_market_fields():
    assert bp.market_key_audit({"research": {"EPAplay_off": .1}}) == []
    hits = bp.market_key_audit({"research": {"sportsbook_odds": 1.91}})
    assert hits


def test_profile_entrypoint_fix_handles_pandas_series():
    import build_pack_entry as entry
    current = {"10": pd.Series({"pos_team": "Alpha", "EPAplay_off": .1})}
    prior = {"10": pd.Series({"pos_team": "Alpha Old", "EPAplay_off": .2})}
    p = entry.fixed_profile("10", "Fallback", current, {}, prior, {}, {}, {})
    assert p["team_name"] == "Alpha"
    assert p["current"]["summary"]["EPAplay_off"] == .1


def test_validator_rejects_same_week_leakage(tmp_path: Path):
    from validate_pack import validate
    data = tmp_path
    (data / "slates" / "2026").mkdir(parents=True)
    pack = {
        "schema_version": "0.1.0", "market_data": False,
        "slate_id": "2026_02", "pack_revision": "0123456789abcdef",
        "season": 2026, "week": 2,
        "data_state": {"current_season_data_through_week": 2},
        "games": [{
            "game_id": "1",
            "fixture": {"fbs_game": True, "home_id": "10", "away_id": "20"},
            "home_profile": {"team_id": "10"}, "away_profile": {"team_id": "20"},
        }],
    }
    (data / "slates" / "2026" / "2026_02.json").write_text(json.dumps(pack))
    manifest = {
        "schema_version": "0.1.0", "market_data": False, "fixture_count": 1,
        "slates": [{"slate_id": "2026_02", "season": 2026, "week": 2,
                    "pack_revision": "0123456789abcdef", "game_count": 1}],
    }
    (data / "manifest.json").write_text(json.dumps(manifest))
    result = validate(data)
    assert not result["ok"]
    assert any("leakage cutoff failed" in e for e in result["errors"])
