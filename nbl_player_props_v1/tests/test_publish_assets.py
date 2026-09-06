from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from publish_assets import canonical_sha, publish  # noqa: E402


def qbase(stat: str):
    return {
        "model_name": stat,
        "model_version": "0.1.0",
        "stat_type": stat,
        "market_data": False,
        "source_receipt_sha256": "a" * 64,
        "walk_forward": {"overall": {"n": 6000}, "brier_at_least": {"mean": 0.1}, "nb2_alpha_oos": 0.2},
        "probability_contract": {"max_count": 20},
    }


def test_publish_assets_is_stable_and_market_blind(tmp_path: Path):
    a=tmp_path/'a.json'; r=tmp_path/'r.json'; p=tmp_path/'p.json'; s=tmp_path/'s.json'; out=tmp_path/'out'
    a.write_text(json.dumps(qbase('assists'))); r.write_text(json.dumps(qbase('rebounds')))
    prior={"schema_version":"nbl_historical_prior_snapshot_v1","market_data":False,"snapshot_revision":"snap1","players":{},"teams":{}}
    receipt={"market_data":False,"rows":100}
    p.write_text(json.dumps(prior)); s.write_text(json.dumps(receipt))
    m1=publish(a,r,p,s,out); m2=publish(a,r,p,s,out)
    assert m1==m2
    assert m1['market_data'] is False
    assert len(m1['asset_revision'])==20
    assert m1['qbase']['assists']['canonical_sha256']==canonical_sha(qbase('assists'))
    assert json.loads((out/'manifest.json').read_text())==m1
    assert (out/'model/qbase_assists_v0.1.0.json').exists()
    assert (out/'prior_snapshot.json').exists()


def test_runtime_prior_change_does_not_change_qbase_hash(tmp_path: Path):
    a=tmp_path/'a.json'; r=tmp_path/'r.json'; p=tmp_path/'p.json'; s=tmp_path/'s.json'; out=tmp_path/'out'
    a.write_text(json.dumps(qbase('assists'))); r.write_text(json.dumps(qbase('rebounds'))); s.write_text(json.dumps({"market_data":False}))
    prior={"schema_version":"nbl_historical_prior_snapshot_v1","market_data":False,"snapshot_revision":"snap1","players":{},"teams":{}}
    p.write_text(json.dumps(prior)); m1=publish(a,r,p,s,out)
    prior['snapshot_revision']='snap2'; prior['players']={'x':{'features':{}}}; p.write_text(json.dumps(prior)); m2=publish(a,r,p,s,out)
    assert m1['qbase']['assists']['canonical_sha256']==m2['qbase']['assists']['canonical_sha256']
    assert m1['asset_revision']!=m2['asset_revision']
