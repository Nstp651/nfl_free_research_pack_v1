from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from math import pow
from typing import Deque

import pandas as pd


@dataclass
class EloState:
    overall: float = 1500.0
    matches: int = 0


def _expected(a: float, b: float) -> float:
    return 1.0 / (1.0 + pow(10.0, (b - a) / 400.0))


def _update(a: float, b: float, result_a: float, k: float) -> tuple[float, float]:
    ea = _expected(a, b)
    delta = k * (result_a - ea)
    return a + delta, b - delta


def build_player_states(matches: pd.DataFrame, k: float = 24.0, surface_prior_matches: float = 20.0) -> pd.DataFrame:
    """Chronological pre-match Elo/workload states. No future match can leak backward."""
    required = {"event_date", "tour", "surface", "player_a_id", "player_b_id", "winner_id", "duration_minutes", "source_record_id"}
    missing = required - set(matches.columns)
    if missing:
        raise ValueError(f"missing required match columns: {sorted(missing)}")

    m = matches.copy()
    m["event_date"] = pd.to_datetime(m["event_date"], utc=True, errors="coerce")
    m = m.dropna(subset=["event_date", "player_a_id", "player_b_id", "winner_id"]).sort_values(
        ["event_date", "source_record_id"], kind="stable"
    )

    overall: dict[tuple[str, str], EloState] = defaultdict(EloState)
    surface: dict[tuple[str, str, str], EloState] = defaultdict(EloState)
    histories: dict[tuple[str, str], Deque[tuple[pd.Timestamp, float, str]]] = defaultdict(deque)
    rows: list[dict] = []

    for row in m.itertuples(index=False):
        tour = str(row.tour).upper()
        surf = str(row.surface).lower()
        date = row.event_date
        a = str(row.player_a_id)
        b = str(row.player_b_id)
        winner = str(row.winner_id)
        duration = float(row.duration_minutes) if pd.notna(row.duration_minutes) else 0.0

        def snapshot(pid: str, opp: str) -> dict:
            o = overall[(tour, pid)]
            s = surface[(tour, surf, pid)]
            weight = s.matches / (s.matches + surface_prior_matches) if s.matches else 0.0
            surface_shrunk = weight * s.overall + (1.0 - weight) * o.overall
            h = histories[(tour, pid)]
            while h and (date - h[0][0]).total_seconds() > 14 * 86400:
                h.popleft()
            matches_14d = len(h)
            minutes_7d = sum(x[1] for x in h if (date - x[0]).total_seconds() <= 7 * 86400)
            last_surface = h[-1][2] if h else None
            return {
                "tour": tour,
                "player_id": pid,
                "event_date": date,
                "match_id": row.source_record_id,
                "surface": surf,
                "elo_overall_pre": o.overall,
                "elo_surface_raw_pre": s.overall,
                "elo_surface_shrunk_pre": surface_shrunk,
                "surface_matches_pre": s.matches,
                "opponent_elo_pre": overall[(tour, opp)].overall,
                "matches_14d_pre": matches_14d,
                "minutes_7d_pre": minutes_7d,
                "surface_transition": bool(last_surface is not None and last_surface != surf),
                "serve_strength_available": False,
                "return_strength_available": False,
                "first_serve_effectiveness": pd.NA,
                "second_serve_resilience": pd.NA,
                "ace_rate": pd.NA,
                "double_fault_rate": pd.NA,
                "quality_flags": "results_only_state|serve_return_stats_missing",
            }

        rows.append(snapshot(a, b))
        rows.append(snapshot(b, a))

        result_a = 1.0 if winner == a else 0.0
        oa, ob = overall[(tour, a)], overall[(tour, b)]
        oa.overall, ob.overall = _update(oa.overall, ob.overall, result_a, k)
        oa.matches += 1
        ob.matches += 1
        sa, sb = surface[(tour, surf, a)], surface[(tour, surf, b)]
        sa.overall, sb.overall = _update(sa.overall, sb.overall, result_a, k)
        sa.matches += 1
        sb.matches += 1
        histories[(tour, a)].append((date, duration, surf))
        histories[(tour, b)].append((date, duration, surf))

    return pd.DataFrame(rows)
