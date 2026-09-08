import pandas as pd

from nba_player_props_v1.model.features import build_pregame_features, head_feature_columns


def games():
    rows=[]
    for n,date in enumerate(["2026-01-01T00:00:00Z","2026-01-03T00:00:00Z","2026-01-05T00:00:00Z"],start=1):
        game=f"40100000{n}"
        rows.extend([
            {
                "season":2026,"season_type":2,"game_id_espn":game,"game_start_utc":date,
                "player_id_espn":"10","team_id_espn":"1","opponent_team_id_espn":"2","starter":True,"minutes":36.0,
                "assists":4+n,"rebounds":5+n,"offensive_rebounds":1,"defensive_rebounds":4+n,"turnovers":2,
                "field_goals_made":6,"field_goals_attempted":12+n,"free_throws_attempted":4,
            },
            {
                "season":2026,"season_type":2,"game_id_espn":game,"game_start_utc":date,
                "player_id_espn":"20","team_id_espn":"2","opponent_team_id_espn":"1","starter":True,"minutes":35.0,
                "assists":7-n,"rebounds":8-n,"offensive_rebounds":2,"defensive_rebounds":6-n,"turnovers":3,
                "field_goals_made":7,"field_goals_attempted":14,"free_throws_attempted":5,
            },
        ])
    return pd.DataFrame(rows)


def player_row(frame,game,player):
    return frame[(frame.game_id_espn==game)&(frame.player_id_espn==player)].iloc[0]


def test_current_game_target_changes_do_not_change_current_pregame_features():
    base=games()
    original=build_pregame_features(base)
    changed=base.copy()
    mask=(changed.game_id_espn=="401000002")&(changed.player_id_espn=="10")
    changed.loc[mask,"assists"]=15
    changed.loc[mask,"rebounds"]=14
    changed.loc[mask,"defensive_rebounds"]=13
    mutated=build_pregame_features(changed)

    a=player_row(original,"401000002","10")
    b=player_row(mutated,"401000002","10")
    for col in set(head_feature_columns("assists")+head_feature_columns("rebounds")):
        left,right=a[col],b[col]
        if pd.isna(left) and pd.isna(right):
            continue
        assert left==right, f"current-game leakage in {col}"


def test_historical_change_can_affect_future_features():
    base=games()
    original=build_pregame_features(base)
    changed=base.copy()
    mask=(changed.game_id_espn=="401000002")&(changed.player_id_espn=="10")
    changed.loc[mask,"assists"]=15
    mutated=build_pregame_features(changed)
    a=player_row(original,"401000003","10")
    b=player_row(mutated,"401000003","10")
    assert a["assists_l5"] != b["assists_l5"]


def test_head_feature_sets_are_independent():
    assists=set(head_feature_columns("assists"))
    rebounds=set(head_feature_columns("rebounds"))
    assert "assists_l10" in assists and "assists_l10" not in rebounds
    assert "rebounds_l10" in rebounds and "rebounds_l10" not in assists
