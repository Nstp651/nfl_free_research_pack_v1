"""Validate the V1.1.3 Worker snapshot without changing frozen values."""
import math
import struct
from freeze_identity import canonical_sha256, grid_sha256


def receipt_material(value):
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            raise ValueError('Non-finite receipt value')
        return 'f64:' + struct.pack('>d', 0.0 if value == 0 else float(value)).hex()
    if isinstance(value, list):
        return [receipt_material(v) for v in value]
    if isinstance(value, dict):
        return {k: receipt_material(v) for k, v in value.items()}
    raise ValueError('Invalid receipt material')


def receipt_hash(value):
    return canonical_sha256(receipt_material(value))


def validate_receipt(frozen):
    body = {k: v for k, v in frozen.items() if k != 'freeze_receipt_sha256'}
    if receipt_hash(body) != frozen.get('freeze_receipt_sha256'):
        raise ValueError('Frozen snapshot receipt mismatch')
    games = frozen['games']
    ids = [g['game_id'] for g in games]
    if not ids or ids != sorted(set(ids)) or ids != frozen['lock']['eligible_game_ids']:
        raise ValueError('Incomplete keyed frozen slate')
    if frozen.get('market_data') is not False or any(frozen.get(k) != 'PASS' for k in ('identity_binding_audit','probability_audit','zero_shift_audit')):
        raise ValueError('Freeze audit/boundary failure')
    if receipt_hash(games) != frozen['numerical_output_sha256']:
        raise ValueError('Numerical receipt mismatch')
    contexts = [g['context'] for g in games]
    if receipt_hash({'lock': frozen['lock'], 'contexts': contexts}) != frozen['input_sha256']:
        raise ValueError('Input receipt mismatch')
    for g in games:
        if grid_sha256(g['probability_grid']) != g['frozen_probability_grid_sha256']:
            raise ValueError('Frozen grid hash mismatch')
        if abs(g['contextual_shift']) <= 1e-9 and not g['distribution_changed']:
            if abs(g['expected_total_final'] - g['expected_total_qbase']) > 1e-9 or g['frozen_probability_grid_sha256'] != g['qbase_probability_grid_sha256']:
                raise ValueError('Zero-shift invariant failed')
