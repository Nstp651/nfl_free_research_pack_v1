from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

SOURCE_SCHEMA = "nba_source_receipt_v1"
METRIC_STATUSES = {"AVAILABLE", "PARTIAL", "UNAVAILABLE", "BLOCKED", "NOT_RELIABLE"}


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def receipt_hash(receipt: dict[str, Any]) -> str:
    payload = {k: v for k, v in receipt.items() if k != "source_receipt_sha256"}
    return sha256_bytes(canonical_json(payload))


def validate_metric_registry(registry: dict[str, Any]) -> None:
    if not isinstance(registry, dict) or not registry:
        raise ValueError("specialist metric registry required")
    for metric, row in registry.items():
        if not isinstance(metric, str) or not metric:
            raise ValueError("invalid specialist metric name")
        if not isinstance(row, dict) or row.get("status") not in METRIC_STATUSES:
            raise ValueError(f"invalid specialist metric status: {metric}")
        if row["status"] == "AVAILABLE":
            coverage = row.get("coverage")
            if not isinstance(coverage, (int, float)) or not 0 <= coverage <= 1:
                raise ValueError(f"AVAILABLE metric requires coverage: {metric}")


def validate_source_receipt(receipt: dict[str, Any]) -> None:
    if receipt.get("schema_version") != SOURCE_SCHEMA:
        raise ValueError("source receipt schema mismatch")
    if receipt.get("market_data") is not False:
        raise ValueError("historical source receipt must be market-blind")
    assets = receipt.get("upstream_assets")
    if not isinstance(assets, list) or not assets:
        raise ValueError("upstream_assets required")
    seen = set()
    for row in assets:
        if not isinstance(row, dict):
            raise ValueError("invalid asset receipt")
        key = (row.get("source"), row.get("immutable_id"), row.get("url"))
        if key in seen:
            raise ValueError("duplicate upstream asset")
        seen.add(key)
        digest = row.get("sha256")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("invalid upstream asset sha256")
        if type(row.get("bytes")) is not int or row["bytes"] <= 0:
            raise ValueError("invalid upstream asset size")
    normalized = receipt.get("normalized_player_games")
    if not isinstance(normalized, dict) or not re.fullmatch(r"[0-9a-f]{64}", str(normalized.get("sha256", ""))):
        raise ValueError("normalized player-game hash required")
    if not isinstance(normalized.get("rows"), int) or normalized["rows"] <= 0:
        raise ValueError("normalized player-game rows required")
    identity = receipt.get("identity_audit")
    if not isinstance(identity, dict):
        raise ValueError("identity audit required")
    for field in ("game_resolution_rate", "player_resolution_rate", "timestamp_non_null_rate"):
        value = identity.get(field)
        if not isinstance(value, (int, float)) or not 0 <= value <= 1:
            raise ValueError(f"invalid identity audit field: {field}")
    if identity.get("duplicate_canonical_player_games") != 0:
        raise ValueError("duplicate canonical player-game rows")
    validate_metric_registry(receipt.get("specialist_metrics"))
    expected = receipt_hash(receipt)
    if receipt.get("source_receipt_sha256") != expected:
        raise ValueError("source receipt hash mismatch")


def build_source_receipt(*, built_at_utc: str, builder_commit: str, upstream_assets: Iterable[dict[str, Any]], normalized_player_games: dict[str, Any], identity_audit: dict[str, Any], specialist_metrics: dict[str, Any], seasons: list[int], latest_completed_game_utc: str | None) -> dict[str, Any]:
    receipt = {
        "schema_version": SOURCE_SCHEMA,
        "market_data": False,
        "built_at_utc": built_at_utc,
        "builder_commit": builder_commit,
        "upstream_assets": sorted(list(upstream_assets), key=lambda x: (str(x.get("source")), str(x.get("immutable_id")), str(x.get("url")))),
        "normalized_player_games": normalized_player_games,
        "identity_audit": identity_audit,
        "specialist_metrics": specialist_metrics,
        "seasons": sorted(seasons),
        "latest_completed_game_utc": latest_completed_game_utc,
    }
    receipt["source_receipt_sha256"] = receipt_hash(receipt)
    validate_source_receipt(receipt)
    return receipt
