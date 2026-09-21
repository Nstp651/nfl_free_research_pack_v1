"""Deterministic NBL team identity canonicalisation shared by source/runtime helpers."""
from __future__ import annotations

import re
import unicodedata
from typing import Any

_CANONICAL_BY_KEY = {
    "adelaide36ers": "Adelaide 36ers",
    "brisbanebullets": "Brisbane Bullets",
    "cairnstaipans": "Cairns Taipans",
    "illawarrahawks": "Illawarra Hawks",
    "melbourneunited": "Melbourne United",
    "newzealandbreakers": "New Zealand Breakers",
    "perthwildcats": "Perth Wildcats",
    "southeastmelbournephoenix": "South East Melbourne Phoenix",
    "sydneykings": "Sydney Kings",
    "tasmaniajackjumpers": "Tasmania JackJumpers",
}

_TEAM_NAME_ALIASES = {
    "nzbreakers": "newzealandbreakers",
    "semelbournephoenix": "southeastmelbournephoenix",
}

# Historical source-era rename used only while rebuilding derived priors.
# It is deliberately not a runtime identity alias so old pinned snapshots that
# contain both labels still preserve the exactly-one-prior fail-closed invariant.
_HISTORICAL_SOURCE_ALIASES = {
    "thehawks": "illawarrahawks",
}


def norm_name(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "", text)


def norm_team_name(value: Any) -> str:
    key = norm_name(value)
    return _TEAM_NAME_ALIASES.get(key, key)


def canonical_team_name(value: Any) -> str:
    raw = str(value or "").strip()
    key = norm_team_name(raw)
    key = _HISTORICAL_SOURCE_ALIASES.get(key, key)
    return _CANONICAL_BY_KEY.get(key, raw)
