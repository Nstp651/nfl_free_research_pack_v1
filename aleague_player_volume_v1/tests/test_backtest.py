import unittest

from aleague_player_volume_v1.backtest import (
    CountForecastObservation,
    evaluate_acceptance,
    score_forecasts,
    select_dispersion_holdout,
)
from aleague_player_volume_v1.model_core import ModelIntegrityError


def obs(
    fixture_id,
    kickoff,
    created,
    player,
    head,
    mean,
    actual,
    *,
    dispersion=3.0,
    baseline_mean=None,
):
    return CountForecastObservation(
        fixture_id=fixture_id,
        kickoff_utc=kickoff,
        forecast_created_utc=created,
        player_id=player,
        head=head,
        mean=mean,
        dispersion=dispersion,
        actual_count=actual,
        baseline_mean=baseline_mean,
        source_run_id=f"run:{fixture_id}",
    )


class BacktestTests(unittest.TestCase):
    def test_forecast_must_preexist_kickoff(self):
        row = obs(
            "f1",
            "2026-10-10T08:00:00Z",
            "2026-10-10T08:00:00Z",
            "p1",
            "SHOTS",
            2.0,
            2,
        )
        with self.assertRaises(ModelIntegrityError):
            score_forecasts([row])

    def test_scoring_is_market_free_and_reports_baseline(self):
        rows = [
            obs(
                "f1",
                "2026-10-10T08:00:00Z",
                "2026-10-10T04:00:00Z",
                "p1",
                "SHOTS",
                2.1,
                2,
                baseline_mean=0.8,
            ),
            obs(
                "f2",
                "2026-10-17T08:00:00Z",
                "2026-10-17T04:00:00Z",
                "p1",
                "SHOTS",
                2.4,
                3,
                baseline_mean=0.9,
            ),
        ]
        report = score_forecasts(rows)
        self.assertFalse(report["market_data_used"])
        metrics = report["heads"]["SHOTS"]
        self.assertEqual(metrics["count"], 2)
        self.assertEqual(metrics["baseline_coverage_rate"], 1.0)
        self.assertIn("nll_improvement_vs_baseline", metrics)
        self.assertIn("brier_improvement_vs_baseline", metrics)
        self.assertGreater(len(metrics["calibration_bins"]), 0)

    def test_duplicate_fixture_player_head_fails(self):
        row = obs(
            "f1",
            "2026-10-10T08:00:00Z",
            "2026-10-10T04:00:00Z",
            "p1",
            "SOT",
            0.8,
            1,
        )
        with self.assertRaises(ModelIntegrityError):
            score_forecasts([row, row])

    def test_dispersion_selection_never_uses_validation(self):
        train = [
            obs("f1", "2026-01-01T08:00:00Z", "2026-01-01T04:00:00Z", "p1", "SHOTS", 1.5, 0),
            obs("f2", "2026-01-08T08:00:00Z", "2026-01-08T04:00:00Z", "p1", "SHOTS", 1.5, 4),
            obs("f3", "2026-01-15T08:00:00Z", "2026-01-15T04:00:00Z", "p1", "SHOTS", 1.5, 0),
            obs("f4", "2026-01-22T08:00:00Z", "2026-01-22T04:00:00Z", "p1", "SHOTS", 1.5, 4),
        ]
        validation_a = [
            obs("v1", "2026-02-05T08:00:00Z", "2026-02-05T04:00:00Z", "p1", "SHOTS", 1.5, 1),
            obs("v2", "2026-02-12T08:00:00Z", "2026-02-12T04:00:00Z", "p1", "SHOTS", 1.5, 2),
        ]
        validation_b = [
            obs("v1", "2026-02-05T08:00:00Z", "2026-02-05T04:00:00Z", "p1", "SHOTS", 1.5, 8),
            obs("v2", "2026-02-12T08:00:00Z", "2026-02-12T04:00:00Z", "p1", "SHOTS", 1.5, 9),
        ]
        a = select_dispersion_holdout(
            train + validation_a,
            head="SHOTS",
            validation_start_utc="2026-02-01T00:00:00Z",
            candidates=[0.5, 1.0, 3.0, 20.0],
        )
        b = select_dispersion_holdout(
            train + validation_b,
            head="SHOTS",
            validation_start_utc="2026-02-01T00:00:00Z",
            candidates=[0.5, 1.0, 3.0, 20.0],
        )
        self.assertEqual(a["selected_dispersion"], b["selected_dispersion"])
        self.assertFalse(a["selection_used_validation"])
        self.assertEqual(a["train_nll_by_candidate"], b["train_nll_by_candidate"])

    def test_acceptance_fails_closed_when_heads_missing(self):
        report = score_forecasts([
            obs(
                "f1",
                "2026-10-10T08:00:00Z",
                "2026-10-10T04:00:00Z",
                "p1",
                "SHOTS",
                2.0,
                2,
                baseline_mean=1.0,
            )
        ])
        acceptance = evaluate_acceptance(
            report,
            min_samples={"SHOTS": 1, "SOT": 1, "SAVES": 1},
            max_threshold_ece=1.0,
            max_abs_mean_bias_ratio=1.0,
            min_baseline_nll_improvement=-1.0,
            min_baseline_brier_improvement=-1.0,
            max_poisson_relative_regression=10.0,
        )
        self.assertEqual(acceptance["status"], "FAIL")
        self.assertIn("HEAD_MISSING", acceptance["heads"]["SOT"]["failures"])
        self.assertIn("HEAD_MISSING", acceptance["heads"]["SAVES"]["failures"])


if __name__ == "__main__":
    unittest.main()
