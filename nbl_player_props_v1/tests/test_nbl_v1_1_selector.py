import unittest

from nbl_player_props_v1.nbl_v1_1_selector import core_path, select_v11


def row(player, stat, threshold, p, edge, ev, *, conf="A", frag="LOW",
        state="DIRECT_VALIDATED", supported=True, side="over", odds=2.0):
    return {
        "player_name": player,
        "frozen_player_id": player.lower().replace(" ", "-"),
        "stat_type": stat,
        "side": side,
        "threshold": threshold,
        "decimal_price": odds,
        "bookmaker": "bet365",
        "conditional_win_probability": p,
        "probability_edge": edge,
        "ev_per_unit": ev,
        "confidence": conf,
        "fragility": frag,
        "threshold_validation": state,
        "threshold_best_single_supported": supported,
    }


class TestNblV11Selector(unittest.TestCase):
    def test_long_tail_cannot_choose_player(self):
        r = row("Rako", "rebounds", 10, .2878, .1339, .870)
        self.assertIsNone(core_path(r))

    def test_zylan_style_tail_cannot_choose_player(self):
        r = row("Zylan", "assists", 7, .2018, .0907, .816, frag="MEDIUM")
        self.assertIsNone(core_path(r))

    def test_standard_core(self):
        r = row("Rako", "rebounds", 8, .52, .07, .18)
        self.assertEqual(core_path(r), "STANDARD")

    def test_supported_lower_hit_requires_A_low_direct(self):
        good = row("Player", "assists", 5, .35, .05, .12)
        bad_b = row("Player", "assists", 5, .35, .05, .12, conf="B")
        bad_tail = row("Player", "assists", 5, .35, .05, .12, state="TAIL_SUPPORTED")
        self.assertEqual(core_path(good), "SUPPORTED_LOWER_HIT")
        self.assertIsNone(core_path(bad_b))
        self.assertIsNone(core_path(bad_tail))

    def test_confidence_c_and_high_fragility_cannot_core(self):
        self.assertIsNone(core_path(row("P", "rebounds", 6, .60, .10, .20, conf="C")))
        self.assertIsNone(core_path(row("P", "rebounds", 6, .60, .10, .20, frag="HIGH")))

    def test_edge_band_beats_raw_ev_tail(self):
        core_a = row("A", "rebounds", 7, .50, .075, .16, odds=2.3)
        core_b = row("B", "assists", 4, .55, .045, .30, odds=2.4)
        tail = row("B", "assists", 7, .20, .10, .90, odds=9.0)
        out = select_v11({"evaluated": [core_a, core_b, tail], "best_single": tail})
        self.assertEqual(out["status"], "BET")
        self.assertEqual(out["core"]["player_name"], "A")
        self.assertEqual(out["server_best_single_audit"]["threshold"], 7)

    def test_ladder_only_after_core_same_player_stat(self):
        core = row("Rako", "rebounds", 8, .52, .07, .18)
        ladder = row("Rako", "rebounds", 10, .2878, .1339, .87)
        other = row("Zylan", "assists", 4, .48, .03, .08)
        out = select_v11({"evaluated": [core, ladder, other]})
        self.assertEqual(out["core"]["player_name"], "Rako")
        self.assertEqual(out["optional_ladder"]["threshold"], 10)

    def test_stretch_independent(self):
        core = row("P", "assists", 4, .55, .05, .12)
        stretch = row("P", "assists", 8, .15, .04, .20)
        out = select_v11({"evaluated": [core, stretch]})
        self.assertIsNone(out["optional_ladder"])
        self.assertEqual(out["optional_stretch"]["threshold"], 8)

    def test_extreme_tail_never_core_or_ladder(self):
        core = row("P", "rebounds", 7, .50, .05, .12)
        extreme = row("P", "rebounds", 10, .25, .12, .60, state="EXTREME_TAIL", supported=False)
        out = select_v11({"evaluated": [core, extreme]})
        self.assertIsNone(out["optional_ladder"])

    def test_no_rows_market_input_required(self):
        self.assertEqual(select_v11({"evaluated": []})["status"], "MARKET_INPUT_REQUIRED")

    def test_valid_board_no_core_is_true_no_bet(self):
        weak = row("P", "rebounds", 7, .50, .01, .02)
        self.assertEqual(select_v11({"evaluated": [weak]})["status"], "NO_BET")


if __name__ == "__main__":
    unittest.main()
