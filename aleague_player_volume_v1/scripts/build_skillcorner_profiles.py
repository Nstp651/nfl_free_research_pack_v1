#!/usr/bin/env python3
"""Build a pinned, hash-checked advanced A-League role profile from SkillCorner open data."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.request import Request, urlopen

from aleague_player_volume_v1.ingest.skillcorner import (
    APPROVED_COMMIT,
    build_role_profiles,
    parse_aggregate,
    verify_git_blob,
)
from aleague_player_volume_v1.publication import build_manifest, write_jsonl


SOURCE_FILES = {
    "obr": {
        "path": "data/aggregates/aus1league_obraggregates_20242025.csv",
        "git_blob_sha1": "e02399fa68bded51b54ce1c97a463583225d3fee",
    },
    "passing": {
        "path": "data/aggregates/aus1league_passingaggregates_20242025.csv",
        "git_blob_sha1": "84c5e35a67282a689028fb500f529d5d11f003f8",
    },
    "physical": {
        "path": "data/aggregates/aus1league_physicalaggregates_20242025.csv",
        "git_blob_sha1": "b80308d7662c8923dc82e0721e0b6f17df827d2e",
    },
}


def fetch_pinned(path: str) -> bytes:
    url = f"https://raw.githubusercontent.com/SkillCorner/opendata/{APPROVED_COMMIT}/{path}"
    request = Request(url, headers={"User-Agent": "aleague-player-volume-v1-open-data/1.0", "Accept": "text/csv"})
    with urlopen(request, timeout=30) as response:
        return response.read()


def main() -> None:
    parsed = {}
    source_receipt = {"repository": "SkillCorner/opendata", "commit": APPROVED_COMMIT, "license": "MIT", "files": {}}
    for kind, meta in SOURCE_FILES.items():
        raw = fetch_pinned(meta["path"])
        verify_git_blob(raw, meta["git_blob_sha1"])
        parsed[kind] = parse_aggregate(raw.decode("utf-8-sig"), kind)
        source_receipt["files"][kind] = {**meta, "bytes": len(raw)}

    profiles, coverage = build_role_profiles(parsed["obr"], parsed["passing"], parsed["physical"])
    if len(profiles) < 100:
        raise RuntimeError(f"SkillCorner profile count unexpectedly low: {len(profiles)}")
    if coverage["complete_join_rate"] < 0.90:
        raise RuntimeError(f"SkillCorner three-family join rate below 90%: {coverage['complete_join_rate']:.3%}")

    base = Path("aleague_player_volume_v1/data/advanced/skillcorner_2024-25")
    asset = write_jsonl(base / "role_profiles.jsonl", profiles)
    asset["path"] = str(Path(asset["path"]).relative_to(Path("aleague_player_volume_v1")))
    source_receipt["coverage"] = coverage
    manifest = build_manifest(
        source_id="skillcorner_opendata",
        season="2024-25",
        assets=[asset],
        source_receipt=source_receipt,
    )
    (base / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "coverage": coverage, "manifest": str(base / "manifest.json")}, indent=2))


if __name__ == "__main__":
    main()
