"""Pure post-freeze pricing math for NCAA full-game totals.

This module contains no market retrieval and no model mutation. It evaluates an
already-frozen side probability against an accepted decimal price. Integer
lines may push; half-point lines must have push=0.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import math


@dataclass(frozen=True)
class PriceEvaluation:
    p_win: float
    p_push: float
    p_loss: float
    odds: float
    p_break_even_win: float
    fair_price: float
    price_edge: float
    expected_roi: float

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


def _prob(name: str, value: float) -> float:
    x = float(value)
    if not math.isfinite(x) or x < 0.0 or x > 1.0:
        raise ValueError(f"{name} must be a finite probability in [0,1]")
    return x


def evaluate_price(p_win: float, p_push: float, odds: float) -> PriceEvaluation:
    """Evaluate one frozen total side at decimal odds.

    Push returns stake, so expected ROI per unit staked is:
      p_win * odds + p_push - 1

    Break-even unconditional win probability is:
      (1 - p_push) / odds

    Fair decimal odds for the offered side are:
      (1 - p_push) / p_win

    With p_push=0 these reduce to the usual half-point formulas.
    """
    win = _prob("p_win", p_win)
    push = _prob("p_push", p_push)
    dec = float(odds)
    if not math.isfinite(dec) or dec <= 1.0:
        raise ValueError("odds must be finite decimal odds > 1")
    if win + push > 1.0 + 1e-12:
        raise ValueError("p_win + p_push cannot exceed 1")
    loss = max(0.0, 1.0 - win - push)
    break_even = (1.0 - push) / dec
    fair = math.inf if win == 0.0 else (1.0 - push) / win
    edge = win - break_even
    roi = win * dec + push - 1.0
    return PriceEvaluation(
        p_win=win,
        p_push=push,
        p_loss=loss,
        odds=dec,
        p_break_even_win=break_even,
        fair_price=fair,
        price_edge=edge,
        expected_roi=roi,
    )


def side_probabilities(row: dict, side: str) -> tuple[float, float]:
    """Extract frozen win/push probabilities from one probability-grid row."""
    s = str(side).strip().lower()
    if s not in {"over", "under"}:
        raise ValueError("side must be Over or Under")
    if "push" not in row:
        raise ValueError("frozen probability row is missing push probability")
    return float(row[s]), float(row["push"])
