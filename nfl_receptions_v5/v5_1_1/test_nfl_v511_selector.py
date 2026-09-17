import unittest
from copy import deepcopy
from nfl_v511_selector import select, minimum_price, passes, core_path, rung_tier


def player(pos="WR", **kw):
    base = dict(
        position=pos,
        include="INCLUDE",
        receiver_class="PRIMARY TARGET EARNER",
        role="STABLE",
        pathway_usable=True,
        evidence_score=14,
        availability_score=2,
        role_score=2,
        confidence="HIGH",
        fragility="LOW",
        evidence_ids=["e1"],
    )
    base.update(kw)
    return base


def row(pid, k, p, o, **kw):
    r = dict(
        player_id=pid,
        k=k,
        p=str(p),
        odds=str(o),
        book="book",
        quote_time=9900,
        market="standard",
        verified=True,
        threshold_fragility="LOW",
    )
    r.update(kw)
    return r


def fixture(rows, players=None):
    return dict(
        integrity_verified=True,
        complete_board=True,
        frozen=True,
        research_permission=True,
        run_id="synthetic-run",
        freeze_receipt="synthetic-receipt",
        now=10000,
        players=players or {"a": player(), "b": player("TE"), "c": player("RB")},
        rows=rows,
    )


class PolicyTests(unittest.TestCase):
    def test_palmer_style_tail_cannot_choose_player(self):
        x = select(fixture([row("a", 5, .0385, 41), row("b", 4, .45, 2.5)]))
        self.assertEqual(x["selected_player"], "b")

    def test_sub20_never_core_even_huge_price(self):
        self.assertEqual(select(fixture([row("a", 6, .1999, 100)]))["decision"], "NO BET")

    def test_standard_core_30pct_boundary(self):
        self.assertEqual(core_path(row("a", 4, ".30", "4.00"), player()), "STANDARD_CORE")

    def test_supported_lower_hit_path(self):
        self.assertEqual(core_path(row("a", 5, ".22", "5.40"), player()), "SUPPORTED_LOWER_HIT")

    def test_supported_lower_hit_requires_high_confidence(self):
        self.assertIsNone(core_path(row("a", 5, ".22", "5.40"), player(confidence="MEDIUM")))

    def test_supported_lower_hit_requires_low_player_fragility(self):
        self.assertIsNone(core_path(row("a", 5, ".22", "5.40"), player(fragility="MODERATE")))

    def test_supported_lower_hit_requires_explicit_low_threshold_fragility(self):
        self.assertIsNone(core_path(row("a", 5, ".22", "5.40", threshold_fragility=None), player()))

    def test_low_confidence_player_rejected(self):
        d = fixture([row("a", 2, .8, 2)])
        d["players"]["a"]["confidence"] = "LOW"
        self.assertEqual(select(d)["decision"], "NO BET")

    def test_high_fragility_player_rejected(self):
        d = fixture([row("a", 2, .8, 2)])
        d["players"]["a"]["fragility"] = "HIGH"
        self.assertEqual(select(d)["decision"], "NO BET")

    def test_missing_role_rejected(self):
        d = fixture([row("a", 2, .8, 2)])
        del d["players"]["a"]["role"]
        self.assertEqual(select(d)["decision"], "NO BET")

    def test_stale_higher_price_does_not_win(self):
        x = select(fixture([row("a", 3, .7, 4, quote_time=7000), row("a", 3, .7, 1.8)]))
        self.assertEqual(x["recommendations"][0]["odds"], "1.8")

    def test_current_best_quote(self):
        x = select(fixture([row("a", 3, .7, 1.8), row("a", 3, .7, 2)]))
        self.assertEqual(x["recommendations"][0]["odds"], "2")

    def test_rb_equal_treatment(self):
        x = select(fixture([row("a", 4, .6, 2), row("c", 3, .7, 2)]))
        self.assertEqual(x["selected_player"], "c")

    def test_verified_expansion_allowed(self):
        d = fixture([row("a", 3, .7, 2)])
        d["players"]["a"]["role"] = "VERIFIED_EXPANSION"
        self.assertEqual(select(d)["decision"], "BET")

    def test_upper_tail_cannot_create_player_anchor(self):
        x = select(fixture([row("a", 3, .7, 2), row("b", 7, .15, 100)]))
        self.assertEqual(x["selected_player"], "a")

    def test_ladder_and_stretch_max_three_recommendations(self):
        x = select(fixture([row("a", 3, .7, 2), row("a", 4, .4, 3), row("a", 5, .15, 9)]))
        self.assertEqual([r["tier"] for r in x["recommendations"]], ["CORE", "LADDER", "STRETCH"])

    def test_stretch_independent_of_missing_ladder(self):
        x = select(fixture([row("a", 3, .7, 2), row("a", 4, .19, 8)]))
        self.assertEqual([r["tier"] for r in x["recommendations"]], ["CORE", "STRETCH"])

    def test_core_can_stand_alone(self):
        x = select(fixture([row("a", 3, .7, 2), row("a", 4, .1, 20)]))
        self.assertEqual([r["tier"] for r in x["recommendations"]], ["CORE"])

    def test_standard_core_can_use_player_fragility_fallback(self):
        x = select(fixture([row("a", 3, .7, 2, threshold_fragility=None)]))
        self.assertEqual(x["decision"], "BET")

    def test_optional_rungs_require_explicit_threshold_fragility(self):
        x = select(fixture([row("a", 3, .7, 2), row("a", 4, .4, 3, threshold_fragility=None)]))
        self.assertEqual([r["tier"] for r in x["recommendations"]], ["CORE"])

    def test_negative_value_rejected(self):
        self.assertEqual(select(fixture([row("a", 3, .8, 1.1)]))["decision"], "NO BET")

    def test_refresh_removes_play(self):
        d = fixture([row("a", 3, .7, 2)])
        self.assertEqual(select(d)["decision"], "BET")
        d["rows"][0]["odds"] = "1.4"
        self.assertEqual(select(d)["decision"], "NO BET")

    def test_no_mutation(self):
        d = fixture([row("a", 3, .7, 2)])
        before = deepcopy(d)
        select(d)
        self.assertEqual(d, before)

    def test_partial_board_blocked(self):
        d = fixture([])
        d["complete_board"] = False
        with self.assertRaises(ValueError):
            select(d)

    def test_inversion_blocked(self):
        with self.assertRaises(RuntimeError):
            select(fixture([row("a", 3, .6, 2), row("a", 4, .7, 3)]))

    def test_conflicting_p_blocked(self):
        with self.assertRaises(RuntimeError):
            select(fixture([row("a", 3, .6, 2), row("a", 3, .7, 3)]))

    def test_invalid_odds_rejected(self):
        self.assertEqual(select(fixture([row("a", 3, .6, "NaN")]))["decision"], "NO BET")

    def test_future_quote_rejected(self):
        self.assertEqual(select(fixture([row("a", 3, .6, 2, quote_time=10001)]))["decision"], "NO BET")

    def test_min_price_standard_core(self):
        self.assertEqual(minimum_price(".6", "CORE"), "1.75")

    def test_min_price_supported_lower_core(self):
        self.assertEqual(minimum_price(".22", "CORE"), "5.27")

    def test_sample_positive_rows_not_automatic_no_bet(self):
        probs = [.0385,.1369,.0165,.0306,.1674,.0269,.024,.0298,.1529,.2209,.0935,.0773,.0546,.0557,.099,.0766,.2675,.3362,.0804,.0449,.0726,.2383]
        odds = [41,10,81,41,7.5,46,51,41,8,5.4,12.5,15,21,20,11,14,4,3.15,13,23,14,4.25]
        players = {str(i): player() for i in range(22)}
        d = fixture([row(str(i), 1, p, o) for i, (p, o) in enumerate(zip(probs, odds))], players)
        x = select(d)
        self.assertEqual(x["decision"], "BET")
        self.assertEqual(x["selected_player"], "9")
        self.assertEqual(x["recommendations"][0]["core_path"], "SUPPORTED_LOWER_HIT")

    def test_sample_lower_hit_fails_when_reliability_is_not_top_tier(self):
        probs = [.2209, .3362]
        odds = [5.4, 3.15]
        players = {"0": player(confidence="MEDIUM"), "1": player()}
        d = fixture([row("0", 1, probs[0], odds[0]), row("1", 1, probs[1], odds[1])], players)
        self.assertEqual(select(d)["decision"], "NO BET")

    def test_payoff_dominated_upper_rung_not_recommended(self):
        x = select(fixture([row("a", 3, .7, 4), row("a", 4, .4, 4)]))
        self.assertEqual(len(x["recommendations"]), 1)
        self.assertEqual(x["dominated"], [("a", 4)])

    def test_non_numeric_price_rejected(self):
        self.assertEqual(select(fixture([row("a", 3, .6, "missing")]))["decision"], "NO BET")

    def test_tie_reproducible(self):
        rows = [row("b", 3, .7, 2), row("a", 3, .7, 2)]
        self.assertEqual(select(fixture(rows))["selected_player"], select(fixture(rows[::-1]))["selected_player"])

    def test_core_prefers_standard_over_lower_hit_with_same_edge_band(self):
        x = select(fixture([row("a", 4, .40, 3), row("b", 5, .25, 5)]))
        self.assertEqual(x["selected_player"], "a")


if __name__ == "__main__":
    unittest.main(verbosity=2)
