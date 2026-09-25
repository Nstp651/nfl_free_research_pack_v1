from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Dict


@dataclass(frozen=True)
class FreezeReceipt:
    run_id: str
    frozen_at_utc: str
    payload_sha256: str
    artifact_path: str
    status: str = "FROZEN"


def canonical_json(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def freeze_payload(run_id: str, payload: Dict[str, Any], output_dir: str | Path) -> FreezeReceipt:
    if payload.get("market_data_accessed"):
        raise ValueError("refusing to freeze a payload that declares market access")
    serialized = canonical_json(payload)
    digest = sha256(serialized.encode("utf-8")).hexdigest()
    frozen_at = datetime.now(timezone.utc).isoformat()
    envelope = {
        "run_id": run_id,
        "P_MODEL_STATUS": "FROZEN",
        "frozen_at_utc": frozen_at,
        "payload_sha256": digest,
        "payload": payload,
    }
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{run_id}.frozen.json"
    if path.exists():
        raise FileExistsError(f"freeze artifact already exists: {path}")
    path.write_text(json.dumps(envelope, indent=2, sort_keys=True), encoding="utf-8")
    return FreezeReceipt(run_id, frozen_at, digest, str(path))


def verify_freeze(path: str | Path) -> bool:
    envelope = json.loads(Path(path).read_text(encoding="utf-8"))
    if envelope.get("P_MODEL_STATUS") != "FROZEN":
        return False
    payload = envelope["payload"]
    digest = sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    return digest == envelope.get("payload_sha256")
