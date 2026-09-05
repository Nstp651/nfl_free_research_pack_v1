import math
import pytest

from model.market_math import evaluate_price, side_probabilities


def test_half_point_reduces_to_standard_math():
    x = evaluate_price(0.55, 0.0, 2.0)
    assert x.p_loss == pytest.approx(0.45)
    assert x.p_break_even_win == pytest.approx(0.50)
    assert x.fair_price == pytest.approx(1 / 0.55)
    assert x.price_edge == pytest.approx(0.05)
    assert x.expected_roi == pytest.approx(0.10)


def test_integer_push_math():
    x = evaluate_price(0.50, 0.04, 2.0)
    assert x.p_loss == pytest.approx(0.46)
    assert x.p_break_even_win == pytest.approx(0.48)
    assert x.fair_price == pytest.approx(1.92)
    assert x.price_edge == pytest.approx(0.02)
    assert x.expected_roi == pytest.approx(0.04)
    # Conditional non-push win probability has the same sign vs 1/odds.
    assert 0.50 / 0.96 > 1 / 2.0


def test_push_can_make_flat_win_probability_profitable():
    x = evaluate_price(0.49, 0.04, 2.0)
    assert x.p_break_even_win == pytest.approx(0.48)
    assert x.expected_roi == pytest.approx(0.02)
    assert x.price_edge == pytest.approx(0.01)


def test_zero_win_probability_has_infinite_fair_price():
    x = evaluate_price(0.0, 0.05, 2.0)
    assert math.isinf(x.fair_price)
    assert x.expected_roi == pytest.approx(-0.95)


@pytest.mark.parametrize(
    "p_win,p_push,odds",
    [(-0.1, 0.0, 2.0), (1.1, 0.0, 2.0), (0.5, -0.1, 2.0), (0.7, 0.4, 2.0), (0.5, 0.0, 1.0)],
)
def test_invalid_inputs_fail_closed(p_win, p_push, odds):
    with pytest.raises(ValueError):
        evaluate_price(p_win, p_push, odds)


def test_side_probability_mapping_requires_frozen_push():
    row = {"line": 49.0, "over": 0.47, "push": 0.03, "under": 0.50}
    assert side_probabilities(row, "Over") == pytest.approx((0.47, 0.03))
    assert side_probabilities(row, "under") == pytest.approx((0.50, 0.03))
    with pytest.raises(ValueError):
        side_probabilities({"line": 49.0, "over": 0.47, "under": 0.50}, "Over")
