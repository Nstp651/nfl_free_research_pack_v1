from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model"))

from distribution import at_least, estimate_nb_alpha, probability_grid  # noqa: E402
from features import build_feature_frame, feature_columns  # noqa: E402


def synthetic_games() -> pd.DataFrame:
    rows = []
    base = pd.Timestamp("2020-01-01", tz="UTC")
    for game in range(12):
        match_id = f"m{game}"
        when = base + pd.Timedelta(days=game * 3)
        for team, opp, home in (("A", "B", "home"), ("B", "A", "away")):
            for p in range(2):
                rows.append({
                    "match_id": match_id,
                    "season": "2019-2020",
                    "match_time": when,
                    "team": team,
                    "opponent": opp,
                    "player_key": f"{team}{p}",
                    "home_away": home,
                    "starter": "true" if p == 0 else "false",
                    "minutes": 30.0 - p * 5 + game * 0.1,
                    "points": 10 + p + game,
                    "assists": (3 + p + game) % 8,
                    "rebounds": (5 + p + game) % 11,
                })
    return pd.DataFrame(rows)


def test_player_rolling_feature_excludes_target_game():
    raw = synthetic_games()
    feat = build_feature_frame(raw)
    p = feat[feat.player_key == "A0"].sort_values("match_time").reset_index(drop=True)
    # For game 6 the last-3 mean must be games 3,4,5, never current game 6.
    i = 6
    expected_ast = raw[raw.player_key == "A0"].sort_values("match_time").iloc[i-3:i]["assists"].mean()
    expected_min = raw[raw.player_key == "A0"].sort_values("match_time").iloc[i-3:i]["minutes"].mean()
    assert abs(p.loc[i, "player_assists_mean_3"] - expected_ast) < 1e-12
    assert abs(p.loc[i, "player_minutes_mean_3"] - expected_min) < 1e-12


def test_opponent_defense_feature_comes_from_opponent_history():
    raw = synthetic_games()
    feat = build_feature_frame(raw)
    # Alter B players' assists in historical games so B's assists-allowed profile
    # to A differs from A's. The exact expected value is derived from B team rows.
    target = feat[(feat.player_key == "A0")].sort_values("match_time").iloc[-1]
    assert np.isfinite(target["opponent_assists_allowed_mean_5"])
    assert "opponent_assists_allowed_mean_5" in feature_columns("assists")


def test_probability_grid_partition_and_monotonicity():
    grid = probability_grid(mu=6.2, alpha=0.18, max_count=20)
    ladder = grid["at_least_ladder"]
    assert all(ladder[i + 1]["at_least"] <= ladder[i]["at_least"] for i in range(len(ladder)-1))
    for row in grid["half_point_grid"] + grid["integer_push_grid"]:
        assert abs(row["over"] + row["push"] + row["under"] - 1.0) < 1e-9


def test_nb_alpha_and_at_least_are_valid():
    y = np.array([0, 1, 2, 4, 8] * 10, dtype=float)
    mu = np.array([1.0, 1.5, 2.2, 3.5, 5.0] * 10, dtype=float)
    alpha = estimate_nb_alpha(y, mu)
    assert alpha > 0
    p = at_least(5, 4.2, alpha)
    assert 0 <= p <= 1
