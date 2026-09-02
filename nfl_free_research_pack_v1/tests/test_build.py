"""Synthetic regression tests. These do not validate live nflverse availability."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import pandas as pd
import build_pack as b
from validate_pack import validate, check_keys

class DataTests(unittest.TestCase):
    def test_missing_week_and_aggregate_rows_cannot_leak(self):
        self.assertTrue(b.current_season_cut(pd.DataFrame({'targets': [999]}), 5).empty)
        df = pd.DataFrame({'week': [0, 1, 4, 5, 8, None], 'targets': [999, 2, 4, 8, 99, 9]})
        self.assertEqual(b.current_season_cut(df, 5).targets.sum(), 6)
        self.assertTrue(b.current_season_cut(df, 1).empty)

    def test_regular_filter_excludes_all_postseason_data(self):
        self.assertTrue(b.filter_regular(pd.DataFrame({'game_type': ['POST', 'PRE']})).empty)

    def test_nullable_charting_flags(self):
        s = b.bool_series(pd.Series([1.0, 0.0, None, 'TRUE', 'unknown']))
        self.assertEqual(int(s.notna().sum()), 3)
        self.assertAlmostEqual(float(s.mean()), 2 / 3)

    def test_optional_team_columns_stay_missing(self):
        result = b.aggregate_team_stats(pd.DataFrame({'team': ['AA'], 'week': [1]}))['AA']
        self.assertIsNone(result['pass_attempts_per_game'])
        self.assertIsNone(result['completion_rate'])

    def test_receiver_missing_optional_yards(self):
        result = b.aggregate_receiver_window(pd.DataFrame({'player_id': ['p'], 'week': [1], 'targets': [4], 'receptions': [2]}))['p']
        self.assertEqual(result['catch_rate'], .5)
        self.assertIsNone(result['adot'])
        self.assertIsNone(result['receiving_yards'])

    def test_snap_share_does_not_weight_by_players_own_snaps(self):
        df = pd.DataFrame({'pfr_player_id': ['p', 'p'], 'week': [1, 2], 'offense_snaps': [90, 10], 'offense_pct': [.9, .1]})
        self.assertEqual(b.aggregate_snap(df, {'p': 'g'})['g']['offense_snap_pct'], .5)

    def test_ngs_excludes_full_season_aggregate_in_week5(self):
        df = pd.DataFrame({'season': [2026]*4, 'week': [0, 1, 4, 5], 'player_gsis_id': ['p']*4,
                           'targets': [1000, 2, 2, 100], 'receptions': [900, 1, 1, 90], 'avg_separation': [90, 2, 4, 100]})
        result = b.aggregate_ngs(b.current_season_cut(df, 5), 2026, False)['p']
        self.assertEqual(result['targets'], 4)
        self.assertEqual(result['avg_separation'], 3)

    def test_roster_preserves_unknown_ids_and_does_not_join_old_team_depth(self):
        roster = pd.DataFrame({'gsis_id': ['p', None, None], 'full_name': ['Test WR', 'Unknown A', 'Unknown B'],
                               'position': ['WR', 'TE', 'RB'], 'team': ['NEW']*3})
        depth = pd.DataFrame({'gsis_id': ['p'], 'team': ['OLD'], 'pos_rank': [1], 'dt': ['2026-09-01']})
        result = b.roster_skill_players(roster, depth)
        self.assertEqual(len(result), 3)
        self.assertTrue(result.pos_rank.isna().all())

    def charting(self):
        pbp = pd.DataFrame({'game_id': ['g']*4, 'play_id': [1,2,3,4], 'receiver_player_id': ['p','p','q','p'],
                            'posteam': ['AA']*4, 'complete_pass': [1,0,1,1], 'pass_attempt': [1]*4,
                            'two_point_attempt': [0,0,0,1]})
        ftn = pd.DataFrame({'nflverse_game_id': ['g']*4, 'nflverse_play_id': [1,2,3,4],
                            'is_catchable_ball': [1.0,None,1.0,1.0], 'is_drop': [0.0,None,0.0,0.0],
                            'read_thrown': ['0',None,'0','DES']})
        return pbp, ftn

    def test_charting_denominators_and_read_shares(self):
        pbp, ftn = self.charting()
        result, _ = b.ftn_receiver_metrics(ftn,pbp)
        p = result['p']
        self.assertEqual(p['charted_targets'], 2)
        self.assertEqual(p['catchable_ball_rate'], 1)
        self.assertEqual(p['catchable_ball_observed_targets'], 1)
        self.assertEqual(p['catchable_target_conversion'], 1)
        self.assertEqual(p['primary_read_share_by_source_team']['AA']['primary_read_target_share'], .5)
        self.assertEqual(p['read_thrown_unknown_or_missing'], 1)

    def test_duplicate_charting_rejected(self):
        pbp, ftn = self.charting()
        with self.assertRaises(ValueError):
            b.ftn_receiver_metrics(pd.concat([ftn, ftn.iloc[:1]]), pbp)

    def test_market_fields_rejected(self):
        with self.assertRaises(ValueError):
            check_keys({'fixture': {'home_moneyline': -100}})

    def test_active_week_does_not_skip_partial_week(self):
        schedule = pd.DataFrame({'season': [2026]*3, 'game_type': ['REG']*3, 'week': [1,1,2], 'result': [3,None,None]})
        self.assertEqual(b.resolve_active_week(schedule, 2026), 1)

    def inputs(self):
        empty = pd.DataFrame()
        result = {'season':2026, 'years':[2025,2026], 'players':empty, 'current_depth':empty, 'prior_rosters':{2025:empty}}
        result['schedule'] = pd.DataFrame({'season':[2026], 'game_type':['REG'], 'week':[1], 'result':[None],
           'game_id':['2026_01_AA_BB'], 'away_team':['AA'], 'home_team':['BB'], 'gameday':['2026-09-10'], 'gametime':['20:00']})
        result['current_roster'] = pd.DataFrame({'gsis_id':['p','q'], 'full_name':['Synthetic WR','Synthetic TE'],
            'position':['WR','TE'], 'team':['AA','BB'], 'years_exp':[3,0]})
        for source in ('player_stats','team_stats','pbp','ftn','snap','pfr_rec','ngs_receiving'):
            result[source] = {2025:empty, 2026:empty}
        result['player_stats'][2025] = pd.DataFrame({'season_type':['REG'], 'player_id':['p'], 'week':[1],
            'team':['OLD'], 'position':['WR'], 'targets':[4], 'receptions':[2]})
        result['pbp'][2025] = pd.DataFrame({'game_id':['oldgame'], 'play_id':[1], 'week':[1], 'posteam':['OLD'],
            'play_type':['pass'], 'receiver_player_id':['p'], 'air_yards':[3]})
        return result

    def test_week1_end_to_end_synthetic_output(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(b, 'load_inputs', return_value=self.inputs()):
            b.build_all(2026, Path(directory), 1, None)
            validate(directory)
            pack = json.loads((Path(directory)/'games/2026/2026_01_AA_BB.json').read_text())
            self.assertIsNone(pack['data_state']['current_season_data_through_week'])
            self.assertTrue(pack['players'][0]['team_change_since_prior_season'])
            self.assertTrue(pack['players'][1]['rookie_flag'])

    def test_current_data_outage_preserves_published_manifest(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(b,'load_inputs',return_value=self.inputs()):
            original = Path(directory)/'manifest.json'
            original.write_text('{"last_good": true}')
            data = self.inputs()
            data['schedule']['week'] = 2
            with patch.object(b, 'load_inputs', return_value=data), self.assertRaises(SystemExit):
                b.build_all(2026, Path(directory), 1, 2)
            self.assertEqual(original.read_text(), '{"last_good": true}')

if __name__ == '__main__':
    unittest.main()
