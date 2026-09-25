from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal, Optional

from .simulator import SimulationDistribution, expected_value_decimal

Market = Literal["h2h", "totals", "spreads"]


@dataclass(frozen=True)
class Quote:
    bookmaker: str
    market: Market
    selection: str
    odds: float
    line: Optional[float] = None


@dataclass(frozen=True)
class PricedOpportunity:
    quote: Quote
    p_win: float
    p_push: float
    p_loss: float
    fair_decimal: float
    ev: float


def _fair_decimal(p_win: float, p_loss: float) -> float:
    if p_win <= 0:
        return float("inf")
    return 1 + p_loss / p_win


def price_quote(dist: SimulationDistribution, quote: Quote) -> PricedOpportunity:
    if quote.market == "h2h":
        player = "A" if quote.selection == "A" else "B"
        p_win = dist.h2h(player)
        p_push = 0.0
        p_loss = 1 - p_win
    elif quote.market == "totals":
        if quote.line is None:
            raise ValueError("total quote requires line")
        side = quote.selection.lower()
        if side not in ("over", "under"):
            raise ValueError("total selection must be over or under")
        probs = dist.total(quote.line, side)
        p_win, p_push, p_loss = probs["win"], probs["push"], probs["loss"]
    elif quote.market == "spreads":
        if quote.line is None:
            raise ValueError("spread quote requires line")
        if quote.selection not in ("A", "B"):
            raise ValueError("spread selection must be A or B")
        probs = dist.spread(quote.selection, quote.line)
        p_win, p_push, p_loss = probs["win"], probs["push"], probs["loss"]
    else:
        raise ValueError(f"unsupported market: {quote.market}")

    return PricedOpportunity(
        quote=quote,
        p_win=p_win,
        p_push=p_push,
        p_loss=p_loss,
        fair_decimal=_fair_decimal(p_win, p_loss),
        ev=expected_value_decimal(quote.odds, p_win, p_push, p_loss),
    )


def best_prices(quotes: Iterable[Quote]) -> list[Quote]:
    best: dict[tuple[str, str, Optional[float]], Quote] = {}
    for q in quotes:
        key = (q.market, q.selection, q.line)
        if key not in best or q.odds > best[key].odds:
            best[key] = q
    return list(best.values())
