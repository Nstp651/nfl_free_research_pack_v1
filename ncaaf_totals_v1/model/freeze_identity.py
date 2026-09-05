#!/usr/bin/env python3
"""Keyed pre-freeze identity and anchor-integrity checks for NCAA totals.

This module exists to make positional/index pairing impossible. Research, QBASE
and frozen game records are reconciled only by exact game_id, with team identity
and per-game QBASE anchor hashes checked before a slate can be certified frozen.

Hash material is deliberately transport-canonical: JSON runtimes may serialize
20.0 as 20 and 0.0 as 0. Numeric fields are normalized to fixed decimal strings
before hashing so the same logical artifact hashes identically before and after
Worker / Action JSON serialization.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any

TOL = 1e-9


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def _fixed(value: Any, places: int) -> str:
    x = float(value)
    if not math.isfinite(x):
        raise ValueError("Non-finite numeric value in identity hash material")
    return f"{x:.{places}f}"


def canonical_probability_grid(grid: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Normalize a probability grid independently of JSON number spelling."""
    out: list[dict[str, str]] = []
    for row in grid or []:
        out.append({
            "line": _fixed(row["line"], 1),
            "over": _fixed(row["over"], 8),
            "push": _fixed(row["push"], 8),
            "under": _fixed(row["under"], 8),
        })
    return out


def qbase_anchor_material(game: dict[str, Any]) -> dict[str, Any]:
    return {
        "game_id": str(game["game_id"]),
        "home_team": game.get("home_team"),
        "away_team": game.get("away_team"),
        "expected_total_qbase": _fixed(game.get("expected_total_qbase"), 6),
        "residual_bucket": game.get("residual_bucket"),
        "residual_sd": _fixed(game.get("residual_sd"), 6),
        "probability_grid": canonical_probability_grid(game.get("probability_grid", [])),
    }


def qbase_anchor_sha256(game: dict[str, Any]) -> str:
    return canonical_sha256(qbase_anchor_material(game))


def grid_sha256(grid: list[dict[str, Any]]) -> str:
    return canonical_sha256(canonical_probability_grid(grid))


def _index_unique(items: list[dict[str, Any]], label: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for item in items:
        gid = str(item.get("game_id", "")).strip()
        if not gid:
            raise ValueError(f"{label}: missing game_id")
        if gid in out:
            raise ValueError(f"{label}: duplicate game_id {gid}")
        out[gid] = item
    return out


def _research_teams(game: dict[str, Any]) -> tuple[str | None, str | None]:
    fx = game.get("fixture", {})
    return fx.get("home_team"), fx.get("away_team")


def build_keyed_anchor_receipts(
    research_games: list[dict[str, Any]],
    qbase_games: list[dict[str, Any]],
    eligible_game_ids: list[str],
) -> list[dict[str, Any]]:
    """Return exact per-game QBASE receipts in eligible identity order.

    The caller may shuffle either source arbitrarily; output correctness is
    unaffected because lookup is exclusively by game_id.
    """
    rmap = _index_unique(research_games, "research")
    qmap = _index_unique(qbase_games, "qbase")
    seen: set[str] = set()
    receipts: list[dict[str, Any]] = []
    for raw_gid in eligible_game_ids:
        gid = str(raw_gid)
        if gid in seen:
            raise ValueError(f"eligible: duplicate game_id {gid}")
        seen.add(gid)
        if gid not in rmap:
            raise ValueError(f"eligible game_id {gid} missing from research")
        if gid not in qmap:
            raise ValueError(f"eligible game_id {gid} missing from QBASE")
        rh, ra = _research_teams(rmap[gid])
        q = qmap[gid]
        if q.get("home_team") != rh or q.get("away_team") != ra:
            raise ValueError(
                f"game_id {gid} team identity mismatch: research={ra}@{rh} "
                f"qbase={q.get('away_team')}@{q.get('home_team')}"
            )
        actual_sha = qbase_anchor_sha256(q)
        declared_sha = q.get("qbase_anchor_sha256")
        if declared_sha is not None and declared_sha != actual_sha:
            raise ValueError(f"game_id {gid} QBASE anchor hash mismatch")
        receipts.append({
            "game_id": gid,
            "home_team": rh,
            "away_team": ra,
            "expected_total_qbase": q.get("expected_total_qbase"),
            "qbase_anchor_sha256": actual_sha,
            "qbase_probability_grid_sha256": grid_sha256(q.get("probability_grid", [])),
        })
    return receipts


def validate_frozen_identity(
    research_games: list[dict[str, Any]],
    qbase_games: list[dict[str, Any]],
    frozen_games: list[dict[str, Any]],
) -> dict[str, Any]:
    """Hard-gate a frozen slate against exact keyed research/QBASE anchors."""
    rmap = _index_unique(research_games, "research")
    qmap = _index_unique(qbase_games, "qbase")
    fmap = _index_unique(frozen_games, "frozen")
    if not fmap:
        raise ValueError("frozen: no games")

    per_game: list[dict[str, Any]] = []
    for gid in sorted(fmap):
        if gid not in rmap or gid not in qmap:
            raise ValueError(f"frozen game_id {gid} missing from research/QBASE")
        r, q, f = rmap[gid], qmap[gid], fmap[gid]
        rh, ra = _research_teams(r)
        identities = [
            (q.get("home_team"), q.get("away_team"), "qbase"),
            (f.get("home_team"), f.get("away_team"), "frozen"),
        ]
        for h, a, label in identities:
            if h != rh or a != ra:
                raise ValueError(f"game_id {gid} {label} team identity mismatch")

        q_anchor_sha = qbase_anchor_sha256(q)
        declared_q_sha = q.get("qbase_anchor_sha256")
        if declared_q_sha is not None and declared_q_sha != q_anchor_sha:
            raise ValueError(f"game_id {gid} source QBASE anchor hash mismatch")
        if f.get("qbase_anchor_sha256") != q_anchor_sha:
            raise ValueError(f"game_id {gid} frozen QBASE anchor hash mismatch")

        q_grid_sha = grid_sha256(q.get("probability_grid", []))
        if f.get("qbase_probability_grid_sha256") != q_grid_sha:
            raise ValueError(f"game_id {gid} frozen QBASE grid hash mismatch")

        shift = float(f.get("contextual_shift", 0.0))
        q_mu = float(q["expected_total_qbase"])
        final_mu = float(f["expected_total_final"])
        if not all(math.isfinite(x) for x in (shift, q_mu, final_mu)):
            raise ValueError(f"game_id {gid} non-finite freeze value")

        no_distribution_change = bool(f.get("distribution_changed", False)) is False
        if abs(shift) <= TOL and no_distribution_change:
            if abs(final_mu - q_mu) > TOL:
                raise ValueError(
                    f"game_id {gid} zero-shift anchor breach: final={final_mu} qbase={q_mu}"
                )
            frozen_grid_sha = grid_sha256(f.get("probability_grid", []))
            if frozen_grid_sha != q_grid_sha:
                raise ValueError(f"game_id {gid} zero-shift probability-grid breach")

        per_game.append({
            "game_id": gid,
            "qbase_anchor_sha256": q_anchor_sha,
            "qbase_probability_grid_sha256": q_grid_sha,
            "frozen_probability_grid_sha256": grid_sha256(f.get("probability_grid", [])),
            "expected_total_qbase": q_mu,
            "contextual_shift": shift,
            "expected_total_final": final_mu,
        })

    receipt = {
        "status": "PASS",
        "game_count": len(per_game),
        "game_ids": sorted(fmap),
        "per_game": per_game,
    }
    receipt["identity_receipt_sha256"] = canonical_sha256(receipt)
    return receipt
