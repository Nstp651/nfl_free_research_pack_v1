from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model"))

from prior_comp_translation import estimate_prior_comp_alpha, translate_prior_comp  # noqa: E402


def rows():
    return [
        {"minutes": 30, "assists": 6, "rebounds": 4, "date": "2026-01-01"},
        {"minutes": 28, "assists": 4, "rebounds": 7, "date": "2026-01-05"},
        {"minutes": 32, "assists": 7, "rebounds": 6, "date": "2026-01-09"},
        {"minutes": 26, "assists": 3, "rebounds": 5, "date": "2026-01-13"},
        {"minutes": 34, "assists": 8, "rebounds": 8, "date": "2026-01-17"},
    ]


def test_neutral_translation_is_observed_rate_times_researched_minutes():
    out = translate_prior_comp(
        "assists", rows(), competition="NCAA",
        projected_minutes={"low": 26, "mean": 30, "high": 34},
        evidence_source_ids=["ncaa_stats"],
        sample_filter_description="Last five healthy games in primary guard role",
    )
    total_assists = sum(r["assists"] for r in rows())
    total_minutes = sum(r["minutes"] for r in rows())
    expected = total_assists / total_minutes * 30
    assert out["base_mean"] == pytest.approx(expected)
    assert out["league_multiplier"] is None
    assert out["freeze_scenario"]["weight"] == 1.0
    assert out["freeze_scenario"]["mean"] == pytest.approx(expected)
    assert len(out["translation_receipt_sha256"]) == 64


def test_translation_reports_empirical_uncertainty_and_nonnegative_alpha():
    out = translate_prior_comp(
        "rebounds", rows(), competition="EuroCup",
        projected_minutes={"low": 20, "mean": 25, "high": 30},
        evidence_source_ids=["eurocup"],
        sample_filter_description="Healthy rotation games",
    )
    assert out["uncertainty_envelope"]["low_mean"] <= out["base_mean"]
    assert out["uncertainty_envelope"]["high_mean"] >= out["base_mean"]
    assert out["sample"]["prior_comp_nb2_alpha"] >= 0


def test_alpha_accounts_for_minutes_exposure():
    counts = [2.0, 4.0, 6.0, 8.0]
    minutes = [10.0, 20.0, 30.0, 40.0]
    rate = sum(counts) / sum(minutes)
    assert estimate_prior_comp_alpha(counts, minutes, rate) == pytest.approx(0.0)


def test_small_prior_sample_fails_instead_of_inventing_translation():
    with pytest.raises(ValueError, match="at least 3 games"):
        translate_prior_comp(
            "assists", rows()[:2], competition="G League",
            projected_minutes={"low": 20, "mean": 25, "high": 30},
            evidence_source_ids=["gleague"],
            sample_filter_description="Comparable games",
        )


def test_invalid_minutes_band_fails():
    with pytest.raises(ValueError, match="0<=low<=mean<=high<=50"):
        translate_prior_comp(
            "assists", rows(), competition="NCAA",
            projected_minutes={"low": 31, "mean": 30, "high": 34},
            evidence_source_ids=["ncaa"],
            sample_filter_description="Comparable games",
        )
