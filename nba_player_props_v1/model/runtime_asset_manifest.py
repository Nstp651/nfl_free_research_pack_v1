from __future__ import annotations

import argparse
import json
from pathlib import Path

from nba_player_props_v1.source_receipt import canonical_json, sha256_bytes, sha256_file


def build_manifest(source: dict, assists: dict, rebounds: dict, prior_pack: dict, *, paths: dict[str, str], file_sha256s: dict[str, str] | None = None) -> dict:
    if source.get("status") != "PASS" or source.get("market_data") is not False:
        raise ValueError("accepted source state required")
    if source.get("history_sha256") != prior_pack.get("history_sha256"):
        raise ValueError("runtime prior history hash mismatch")
    for head, artifact in (("assists", assists), ("rebounds", rebounds)):
        if artifact.get("status") != "PROMOTED_CORE_V1" or artifact.get("head") != head or artifact.get("market_data") is not False:
            raise ValueError(f"{head} promoted artifact invalid")
        if artifact.get("source_acceptance_receipt_sha256") != source.get("receipt_sha256"):
            raise ValueError(f"{head} source acceptance lineage mismatch")
    hashes = file_sha256s or {}
    for key in ("assists", "rebounds", "prior"):
        if key in hashes and (not isinstance(hashes[key], str) or len(hashes[key]) != 64):
            raise ValueError(f"{key} file sha invalid")
    manifest = {
        "schema_version": "nba_runtime_assets_v1", "market_data": False, "asset_revision": "NBA_PLAYER_PROPS_V1.0.0",
        "history_sha256": source["history_sha256"], "source_acceptance_receipt_sha256": source["receipt_sha256"],
        "qbase_heads": {
            "assists": {"path": paths["assists"], "file_sha256": hashes.get("assists"), "model_version": assists["model_version"], "promotion_receipt_sha256": assists["promotion_receipt_sha256"]},
            "rebounds": {"path": paths["rebounds"], "file_sha256": hashes.get("rebounds"), "model_version": rebounds["model_version"], "promotion_receipt_sha256": rebounds["promotion_receipt_sha256"]},
        },
        "runtime_prior": {"path": paths["prior"], "file_sha256": hashes.get("prior"), "pack_sha256": prior_pack["pack_sha256"], "player_count": prior_pack["player_count"], "team_count": prior_pack["team_count"]},
        "specialist_metrics": "BASE_V1_WITHOUT_SPECIALIST_METRICS",
        "prior_competition_translation": "NO_ROUTE_PROMOTED_UNLESS_SEPARATELY_EVIDENCE_VALIDATED",
        "holdout_rule": "PASS_FAIL_REVIEW_ONLY_NO_MODEL_FAMILY_RESELECTION",
    }
    manifest["manifest_sha256"] = sha256_bytes(canonical_json(manifest))
    return manifest


def main() -> None:
    p = argparse.ArgumentParser(); p.add_argument("--source", required=True); p.add_argument("--assists", required=True); p.add_argument("--rebounds", required=True); p.add_argument("--prior", required=True); p.add_argument("--output", required=True); args = p.parse_args()
    source = json.loads(Path(args.source).read_text()); assists = json.loads(Path(args.assists).read_text()); rebounds = json.loads(Path(args.rebounds).read_text()); prior = json.loads(Path(args.prior).read_text())
    out = Path(args.output); out.parent.mkdir(parents=True, exist_ok=True)
    paths = {"assists": "promoted_assists_qbase.json", "rebounds": "promoted_rebounds_qbase.json", "prior": "runtime_prior_pack.json"}
    hashes = {"assists": sha256_file(args.assists), "rebounds": sha256_file(args.rebounds), "prior": sha256_file(args.prior)}
    manifest = build_manifest(source, assists, rebounds, prior, paths=paths, file_sha256s=hashes)
    out.write_bytes(canonical_json(manifest) + b"\n")
    print(json.dumps({"manifest_sha256": manifest["manifest_sha256"], "history_sha256": manifest["history_sha256"], "asset_revision": manifest["asset_revision"]}))


if __name__ == "__main__": main()
