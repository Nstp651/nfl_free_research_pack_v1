from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from nba_player_props_v1.source_receipt import canonical_json, sha256_bytes

EARLY_COHORTS = ("games_0_2", "games_3_7")
ROLE_COHORTS = ("team_changers", "starter_changes", "low_history", "role_change_proxy")


def _need(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def _metric(report: dict, key: str) -> float:
    value = report.get(key)
    _need(isinstance(value, (int, float)), f"missing numeric metric {key}")
    return float(value)


def _predeclared_holdout_review(challenge: dict) -> dict:
    holdout = challenge.get("holdout") or {}
    overall = holdout.get("overall") or {}
    baseline = holdout.get("baseline") or {}
    _need(_metric(overall, "brier_over") <= _metric(baseline, "brier_over"), "holdout Brier regression vs locked baseline")
    _need(_metric(overall, "count_nll") <= _metric(baseline, "count_nll"), "holdout count NLL regression vs locked baseline")
    _need(abs(_metric(overall, "bias")) <= 0.25, "holdout count bias outside predeclared bound")
    coverage = _metric(overall, "coverage_90")
    _need(0.90 <= coverage <= 0.98, "holdout 90% interval coverage outside predeclared bound")
    _need(_metric(overall, "partition_max_error") <= 1e-10, "probability partition integrity failed")
    _need(int(overall.get("n", 0)) >= 10_000, "holdout sample too small")

    cohorts = holdout.get("cohorts") or {}
    early = {}
    for name in EARLY_COHORTS:
        row = cohorts.get(name) or {}
        _need(int(row.get("n", 0)) >= 500, f"holdout {name} sample too small")
        _need(_metric(row, "brier_over") <= 0.08, f"holdout {name} Brier outside predeclared bound")
        _need(abs(_metric(row, "bias")) <= 0.60, f"holdout {name} bias outside predeclared bound")
        c = _metric(row, "coverage_90")
        _need(0.85 <= c <= 0.99, f"holdout {name} coverage outside predeclared bound")
        early[name] = {"n": int(row["n"]), "brier_over": _metric(row, "brier_over"), "bias": _metric(row, "bias"), "coverage_90": c}

    restricted = []
    overall_brier = _metric(overall, "brier_over")
    diagnostics = {}
    for name in ROLE_COHORTS:
        row = cohorts.get(name)
        if not isinstance(row, dict) or int(row.get("n", 0)) == 0:
            restricted.append(name)
            diagnostics[name] = {"status": "NO_SAMPLE"}
            continue
        brier, bias, cov = _metric(row, "brier_over"), _metric(row, "bias"), _metric(row, "coverage_90")
        reasons = []
        if int(row.get("n", 0)) < 200:
            reasons.append("LOW_SAMPLE")
        if brier > overall_brier + 0.015:
            reasons.append("BRIER_DEGRADATION")
        if abs(bias) > 0.75:
            reasons.append("BIAS")
        if not 0.82 <= cov <= 0.99:
            reasons.append("COVERAGE")
        if reasons:
            restricted.append(name)
        diagnostics[name] = {"status": "RESTRICTED" if reasons else "PASS", "reasons": reasons,
                             "n": int(row.get("n", 0)), "brier_over": brier, "bias": bias, "coverage_90": cov}
    return {"overall": {"n": int(overall["n"]), "brier_over": _metric(overall, "brier_over"),
                         "baseline_brier_over": _metric(baseline, "brier_over"),
                         "count_nll": _metric(overall, "count_nll"), "baseline_count_nll": _metric(baseline, "count_nll"),
                         "bias": _metric(overall, "bias"), "coverage_90": coverage},
            "early_cohorts": early, "role_cohorts": diagnostics, "restricted_cohorts": sorted(set(restricted))}


def _validation_review(challenge: dict) -> dict:
    selected = str(challenge.get("selected_candidate") or "")
    candidates = challenge.get("candidates") or {}
    _need(selected in candidates, "selected candidate missing")
    _need(selected in (challenge.get("validation_eligible") or []), "selected candidate failed locked validation eligibility")
    baseline_folds = (candidates.get("shrunk_poisson") or {}).get("folds") or []
    selected_folds = (candidates.get(selected) or {}).get("folds") or []
    _need(len(baseline_folds) == len(selected_folds) and len(selected_folds) >= 2, "validation folds incomplete")
    folds = []
    for selected_fold, baseline_fold in zip(selected_folds, baseline_folds):
        _need(selected_fold.get("season") == baseline_fold.get("season"), "validation fold season mismatch")
        early = {}
        for cohort in EARLY_COHORTS:
            s = selected_fold["cohorts"][cohort]
            b = baseline_fold["cohorts"][cohort]
            _need(_metric(s, "brier_over") <= _metric(b, "brier_over") + 1e-12,
                  f"selected model regressed in locked validation {cohort}")
            early[cohort] = {"selected_brier": _metric(s, "brier_over"), "baseline_brier": _metric(b, "brier_over")}
        folds.append({"season": int(selected_fold["season"]), "early_cohorts": early})
    return {"selected_candidate": selected, "folds": folds}


def promote_head(challenge: dict, source_acceptance: dict, specialist_decision: dict, *, model_version: str) -> dict:
    head = str(challenge.get("head") or "")
    _need(head in {"assists", "rebounds"}, "head invalid")
    _need(challenge.get("market_data") is False, "challenge must be market blind")
    _need(challenge.get("runtime_score_reproduced") is True, "portable runtime score not reproduced")
    _need(source_acceptance.get("status") == "PASS", "source acceptance not PASS")
    _need(source_acceptance.get("market_data") is False, "source acceptance must be market blind")
    _need(specialist_decision.get("base_model_permitted") is True, "specialist decision blocks base model")
    _need(not specialist_decision.get("promoted_specialist_features"), "this promotion path is core-only")

    validation = _validation_review(challenge)
    holdout = _predeclared_holdout_review(challenge)
    artifact = copy.deepcopy(challenge.get("candidate_artifact") or {})
    _need(artifact.get("head") == head, "candidate artifact head mismatch")
    _need(artifact.get("family") == "regularized_poisson_glm", "unexpected selected family")
    _need(float(artifact.get("dispersion_alpha", -1)) >= 0, "dispersion invalid")
    artifact.update({
        "status": "PROMOTED_CORE_V1",
        "market_data": False,
        "model_version": model_version,
        "source_acceptance_receipt_sha256": source_acceptance.get("receipt_sha256"),
        "challenge_receipt_sha256": challenge.get("receipt_sha256"),
        "specialist_metric_decision": specialist_decision.get("decision"),
        "promoted_specialist_features": [],
        "restricted_cohorts": holdout["restricted_cohorts"],
        "promotion_validation": validation,
        "holdout_review": holdout,
        "holdout_use_rule": "PASS_FAIL_REVIEW_ONLY_NO_MODEL_FAMILY_RESELECTION",
    })
    receipt_input = copy.deepcopy(artifact)
    artifact["promotion_receipt_sha256"] = sha256_bytes(canonical_json(receipt_input))
    return artifact


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--challenge", required=True)
    parser.add_argument("--source-acceptance", required=True)
    parser.add_argument("--specialist-decision", required=True)
    parser.add_argument("--model-version", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    challenge = json.loads(Path(args.challenge).read_text())
    source = json.loads(Path(args.source_acceptance).read_text())
    specialist = json.loads(Path(args.specialist_decision).read_text())
    artifact = promote_head(challenge, source, specialist, model_version=args.model_version)
    Path(args.output).write_bytes(canonical_json(artifact) + b"\n")
    print(json.dumps({"head": artifact["head"], "status": artifact["status"],
                      "restricted_cohorts": artifact["restricted_cohorts"],
                      "promotion_receipt_sha256": artifact["promotion_receipt_sha256"]}))


if __name__ == "__main__":
    main()
