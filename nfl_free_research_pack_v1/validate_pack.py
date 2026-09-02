"""Validate actual generated output before committing a refresh."""
import json
import sys
from pathlib import Path
from build_pack import payload_hash

FORBIDDEN = {'odds', 'price', 'spread_line', 'total_line', 'home_moneyline', 'away_moneyline',
             'implied_probability', 'p_model', 'fantasy_points', 'fantasy_points_ppr'}

def check_keys(value):
    if isinstance(value, dict):
        bad = FORBIDDEN.intersection(k.lower() for k in value)
        if bad:
            raise ValueError(f'Market/model fields in research pack: {sorted(bad)}')
        for child in value.values():
            check_keys(child)
    elif isinstance(value, list):
        for child in value:
            check_keys(child)

def validate(directory):
    root = Path(directory)
    manifest = json.loads((root / 'manifest.json').read_text())
    assert manifest['schema_version'] == '1.1.0'
    assert manifest['source_health']['status'] in {'PASS', 'PARTIAL'}
    assert manifest['games'], 'No fixtures'
    seen = set()
    for entry in manifest['games']:
        gid = entry['game_id']
        assert gid not in seen, 'Duplicate fixture'
        seen.add(gid)
        expected = f"games/{entry['season']}/{gid}.json"
        assert entry['path'] == expected
        pack = json.loads((root / expected).read_text())
        assert pack['schema_version'] == '1.1.0'
        assert pack['game_id'] == gid
        assert pack['pack_revision'] == entry['pack_revision']
        unversioned = {k: v for k, v in pack.items() if k != 'pack_revision'}
        assert payload_hash(unversioned) == entry['pack_revision'], 'Content revision mismatch'
        for key in ('season', 'week', 'away_team', 'home_team'):
            assert pack['fixture'][key] == entry[key], f'Fixture {key} mismatch'
        assert entry['week'] == manifest['active_week']
        state = pack['data_state']
        through = state['current_season_data_through_week']
        assert through is None or 1 <= through < entry['week'], 'Look-ahead evidence'
        assert pack['players'] and pack['source_receipt'] and pack['limitations']
        if entry['week'] == 1:
            assert through is None
            assert all(all(v is None for v in p['current_season_to_date'].values()) for p in pack['players'])
        ids = [p['player_id'] for p in pack['players'] if p['player_id']]
        assert len(ids) == len(set(ids)), 'Duplicate player IDs'
        assert {p['current_team'] for p in pack['players']} == {entry['away_team'], entry['home_team']}
        context = {k: v for k, v in pack.items() if k != 'players'}
        for player in pack['players']:
            assert len(json.dumps({**context, 'players': [player]}, ensure_ascii=False)) < 80000, 'Single record too large for Action'
        check_keys(pack)
    print(f'Validated {len(seen)} research packs for {manifest["season"]} week {manifest["active_week"]}')

if __name__ == '__main__':
    validate(sys.argv[1] if len(sys.argv) > 1 else 'data')
