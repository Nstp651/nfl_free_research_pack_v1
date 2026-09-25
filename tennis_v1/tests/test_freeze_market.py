from pathlib import Path

from tennis_v1.freeze import freeze_payload, verify_freeze
from tennis_v1.market import Quote, price_quote
from tennis_v1.simulator import MatchInputs, MatchRules, TennisMatchSimulator


def test_freeze_round_trip(tmp_path: Path):
    receipt = freeze_payload("run-1", {"market_data_accessed": False, "p_a": 0.63}, tmp_path)
    assert receipt.status == "FROZEN"
    assert verify_freeze(receipt.artifact_path)


def test_freeze_rejects_market_access(tmp_path: Path):
    try:
        freeze_payload("run-2", {"market_data_accessed": True}, tmp_path)
    except ValueError:
        return
    assert False, "expected market-leak rejection"


def test_h2h_and_spread_pricing():
    dist = TennisMatchSimulator(seed=5).simulate(
        MatchInputs(0.65, 0.60, MatchRules(best_of=3)), n=5000
    )
    h2h = price_quote(dist, Quote("book", "h2h", "A", 1.80))
    spread = price_quote(dist, Quote("book", "spreads", "A", 1.91, -2.5))
    assert 0 <= h2h.p_win <= 1
    assert 0 <= spread.p_win <= 1
    assert abs(spread.p_win + spread.p_push + spread.p_loss - 1) < 1e-12
