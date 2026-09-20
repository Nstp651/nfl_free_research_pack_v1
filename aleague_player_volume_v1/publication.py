"""Canonical asset publication and source-lock manifest helpers."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Sequence

from .model_core import ModelIntegrityError


CANONICAL_SCHEMA_VERSION = "1.0.0"


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = [dict(row) for row in rows]
    normalized.sort(key=lambda row: tuple(str(row.get(key, "")) for key in ("kickoff_utc", "fixture_id", "team_id", "player_id")))
    content = b"".join(canonical_json_bytes(row) for row in normalized)
    path.write_bytes(content)
    return {"path": str(path), "sha256": sha256_bytes(content), "rows": len(normalized), "bytes": len(content)}


def build_manifest(*, source_id: str, season: str, assets: Sequence[Mapping[str, Any]], source_receipt: Mapping[str, Any]) -> Dict[str, Any]:
    if not source_id or not season or not assets:
        raise ModelIntegrityError("manifest source_id, season and assets are required")
    for asset in assets:
        if not asset.get("sha256") or int(asset.get("rows", 0)) < 0:
            raise ModelIntegrityError("invalid manifest asset")
    manifest = {
        "schema_version": CANONICAL_SCHEMA_VERSION,
        "model": "ALEAGUE_PLAYER_VOLUME_V1",
        "source_id": source_id,
        "season": season,
        "published_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "assets": list(assets),
        "source_receipt": dict(source_receipt),
    }
    digest_payload = dict(manifest)
    digest_payload.pop("published_at_utc", None)
    manifest["manifest_content_sha256"] = sha256_bytes(canonical_json_bytes(digest_payload))
    return manifest


def verify_manifest(root: Path, manifest: Mapping[str, Any]) -> None:
    for asset in manifest.get("assets", []):
        path = root / str(asset["path"])
        content = path.read_bytes()
        if sha256_bytes(content) != asset["sha256"]:
            raise ModelIntegrityError(f"asset hash mismatch: {path}")
