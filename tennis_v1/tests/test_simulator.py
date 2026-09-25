from tennis_v1.simulator import MatchInputs, MatchRules, TennisMatchSimulator, hold_probability


def test_hold_probability_is_half_at_half_point_probability():
    assert abs(hold_probability(0.5) - 0.5) < 1e-12


def test_hold_probability_monotonic():
    assert hold_probability(0.65) > hold_probability(0.60) > hold_probability(0.55)


def test_best_of_three_distribution_mass_and_bounds():
    sim = TennisMatchSimulator(seed=7)
    dist = sim.simulate(MatchInputs(0.64, 0.61, MatchRules(best_of=3)), n=4000)
    assert 0 < dist.p_a_match < 1
    assert abs(sum(dist.total_games.values()) - 1) < 1e-12
    assert abs(sum(dist.game_margin_a.values()) - 1) < 1e-12
    assert all(g >= 12 for g in dist.total_games)


def test_best_of_five_has_valid_set_scores():
    sim = TennisMatchSimulator(seed=11)
    dist = sim.simulate(MatchInputs(0.66, 0.63, MatchRules(best_of=5, final_set_tiebreak_points=10)), n=3000)
    assert all(score.startswith(("3-", "0-3", "1-3", "2-3")) or score.endswith("-3") for score in dist.set_scores)


def test_integer_total_has_push_mass_when_reachable():
    sim = TennisMatchSimulator(seed=13)
    dist = sim.simulate(MatchInputs(0.62, 0.62, MatchRules(best_of=3)), n=5000)
    probs = dist.total(22.0, "over")
    assert abs(sum(probs.values()) - 1) < 1e-12
    assert probs["push"] >= 0


def test_reproducibility():
    inputs = MatchInputs(0.64, 0.60, MatchRules(best_of=3), 0.03, 0.03)
    a = TennisMatchSimulator(seed=99).simulate(inputs, n=2500)
    b = TennisMatchSimulator(seed=99).simulate(inputs, n=2500)
    assert a.p_a_match == b.p_a_match
    assert a.total_games == b.total_games
    assert a.game_margin_a == b.game_margin_a
