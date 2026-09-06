#!/usr/bin/env python3
"""Publish immutable NBL QBASE heads plus refreshable historical prior assets.

QBASE files are only replaced when an explicit retrain/bootstrap workflow supplies
new validated artifacts. Routine refreshes update the prior snapshot and source
receipt while preserving the existing model files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "nbl_runtime_assets_v1"


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def canonical_sha(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def validate_qbase(value: dict[str, Any], stat: str) -> None:
    if value.get("market_data") is not False or value.get("stat_type") != stat:
        raise ValueError(f"{stat} QBASE identity/market boundary invalid")
    if value.get("model_version") != "0.1.0":
        raise ValueError(f"{stat} QBASE model_version not approved for V1")
    wf = value.get("walk_forward") or {}
    overall = wf.get("overall") or {}
    brier = wf.get("brier_at_least") or {}
    if int(overall.get("n", 0)) <= 5000:
        raise ValueError(f"{stat} QBASE insufficient walk-forward sample")
    if not (0 <= float(brier.get("mean", 1.0)) < 0.25):
        raise ValueError(f"{stat} QBASE Brier gate failed")
    if float(wf.get("nb2_alpha_oos", 0)) <= 0:
        raise ValueError(f"{stat} QBASE dispersion gate failed")


def publish(assists_path: str | Path, rebounds_path: str | Path, prior_path: str | Path,
            source_receipt_path: str | Path, output_dir: str | Path) -> dict[str, Any]:
    assists = load_json(assists_path); rebounds = load_json(rebounds_path)
    prior = load_json(prior_path); source_receipt = load_json(source_receipt_path)
    validate_qbase(assists, "assists"); validate_qbase(rebounds, "rebounds")
    if prior.get("market_data") is not False or prior.get("schema_version") != "nbl_historical_prior_snapshot_v1":
        raise ValueError("prior snapshot invalid")
    if source_receipt.get("market_data") is not False:
        raise ValueError("source receipt must be market-blind")

    out = Path(output_dir); model_dir = out / "model"; model_dir.mkdir(parents=True, exist_ok=True)
    model_files = {
        "assists": "model/qbase_assists_v0.1.0.json",
        "rebounds": "model/qbase_rebounds_v0.1.0.json",
    }
    (out / model_files["assists"]).write_text(json.dumps(assists, indent=2, sort_keys=True), encoding="utf-8")
    (out / model_files["rebounds"]).write_text(json.dumps(rebounds, indent=2, sort_keys=True), encoding="utf-8")
    (out / "prior_snapshot.json").write_text(json.dumps(prior, indent=2, sort_keys=True), encoding="utf-8")
    (out / "source_receipt.json").write_text(json.dumps(source_receipt, indent=2, sort_keys=True), encoding="utf-8")

    qhash = {"assists": canonical_sha(assists), "rebounds": canonical_sha(rebounds)}
    prior_hash = canonical_sha(prior); source_hash = canonical_sha(source_receipt)
    identity = {
        "qbase": qhash,
        "prior_snapshot": prior_hash,
        "snapshot_revision": str(prior.get("snapshot_revision") or ""),
        "runtime_source_receipt": source_hash,
    }
    asset_revision = canonical_sha(identity)[:20]
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "market_data": False,
        "asset_revision": asset_revision,
        "qbase": {
            "assists": {
                "path": model_files["assists"], "canonical_sha256": qhash["assists"],
                "model_version": assists["model_version"], "training_source_receipt_sha256": assists.get("source_receipt_sha256"),
            },
            "rebounds": {
                "path": model_files["rebounds"], "canonical_sha256": qhash["rebounds"],
                "model_version": rebounds["model_version"], "training_source_receipt_sha256": rebounds.get("source_receipt_sha256"),
            },
        },
        "prior_snapshot": {
            "path": "prior_snapshot.json", "canonical_sha256": prior_hash,
            "snapshot_revision": prior.get("snapshot_revision"),
        },
        "runtime_source_receipt": {"path": "source_receipt.json", "canonical_sha256": source_hash},
        "integrity": {
            "qbase_retraining_is_explicit_only": True,
            "routine_refresh_changes_prior_not_model": True,
            "market_data": False,
        },
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--assists", required=True); ap.add_argument("--rebounds", required=True)
    ap.add_argument("--prior", required=True); ap.add_argument("--source-receipt", required=True)
    ap.add_argument("--output-dir", default="nbl_player_props_v1/data")
    args = ap.parse_args()
    manifest = publish(args.assists, args.rebounds, args.prior, args.source_receipt, args.output_dir)
    print(json.dumps({"ok": True, "asset_revision": manifest["asset_revision"], "snapshot_revision": manifest["prior_snapshot"]["snapshot_revision"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
