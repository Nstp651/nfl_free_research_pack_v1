#!/usr/bin/env python3
"""Reproduce temporal-OOS ladder reliability for shipped NBL QBASE heads."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from tail_policy import build_tail_audit, canonical_sha256
from train_heads import eligible_frame, walk_forward


def audit_head(raw: pd.DataFrame, artifact: dict[str, Any]) -> dict[str, Any]:
    head = str(artifact["stat_type"])
    selected = artifact["selected_model"]
    frame = eligible_frame(raw, head)
    predictions = walk_forward(frame, head, str(selected["family"]), float(selected["regularization_alpha"]))
    actual = predictions["actual"].to_numpy(float)
    means = predictions["pred"].to_numpy(float)
    alpha = float(artifact["walk_forward"]["nb2_alpha_oos"])
    contract = artifact["probability_contract"]
    tail = build_tail_audit(
        actual,
        means,
        alpha,
        contract["thresholds_used_for_selection"],
        int(contract["max_count"]),
    )
    result = {
        "stat_type": head,
        "model_version": artifact["model_version"],
        "selected_family": selected["family"],
        "selected_regularization_alpha": float(selected["regularization_alpha"]),
        "nb2_alpha_oos": alpha,
        "thresholds_used_for_selection": contract["thresholds_used_for_selection"],
        "oos_first_season": int(predictions["season_start"].min()),
        "oos_last_season": int(predictions["season_start"].max()),
        "oos_n": int(len(predictions)),
        **tail,
    }
    result["evidence_sha256"] = canonical_sha256(result)
    result["policy"]["evidence_sha256"] = result["evidence_sha256"]
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True)
    parser.add_argument("--assists-artifact", required=True)
    parser.add_argument("--rebounds-artifact", required=True)
    parser.add_argument("--output")
    parser.add_argument("--update-artifacts", action="store_true")
    args = parser.parse_args()
    raw = pd.read_csv(args.data, low_memory=False)
    result = {
        "schema_version": "nbl_qbase_tail_validation_audit_v1",
        "market_data": False,
        "heads": {},
    }
    for path in (args.assists_artifact, args.rebounds_artifact):
        artifact_path = Path(path)
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        audit = audit_head(raw, artifact)
        result["heads"][audit["stat_type"]] = audit
        if args.update_artifacts:
            artifact["probability_contract"]["threshold_validation_policy"] = audit["policy"]
            artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    text = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
