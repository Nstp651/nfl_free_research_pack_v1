from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .market import PricedOpportunity


@dataclass(frozen=True)
class MarketDepthPolicy:
    h2h_min_books: int = 3
    totals_min_books: int = 2
    spreads_min_books: int = 2

    def min_books(self, market: str) -> int:
        return {
            "h2h": self.h2h_min_books,
            "totals": self.totals_min_books,
            "spreads": self.spreads_min_books,
        }[market]


def covered_markets(quotes: Iterable[dict], policy: MarketDepthPolicy) -> set[str]:
    books: dict[str, set[str]] = {"h2h": set(), "totals": set(), "spreads": set()}
    for q in quotes:
        market = q["market"]
        if market in books:
            books[market].add(q["bookmaker"])
    return {m for m, bs in books.items() if len(bs) >= policy.min_books(m)}


def rank_opportunities(rows: Iterable[PricedOpportunity], eligible_markets: set[str]) -> list[PricedOpportunity]:
    return sorted(
        [r for r in rows if r.quote.market in eligible_markets],
        key=lambda r: (r.ev, r.p_win),
        reverse=True,
    )
