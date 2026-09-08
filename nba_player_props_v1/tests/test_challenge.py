import numpy as np
import pytest

from nba_player_props_v1.model.challenge import distribution, probability_metrics, fit_candidate, score_artifact
from nba_player_props_v1.model.features import build_pregame_features
from nba_player_props_v1.tests.test_features import games


@pytest.mark.parametrize("alpha", [0, .01, .3, 2])
def test_integer_partition_and_ladder(alpha):
    d = distribution(np.array([.1, 2., 15.]), alpha)
    previous = np.ones(3)
    for k in range(60):
        assert np.allclose(d.cdf(k - 1) + d.pmf(k) + d.sf(k), 1, atol=1e-12)
        assert (d.sf(k) <= previous).all()
        previous = d.sf(k)


def test_push_probability_is_not_half_point_probability():
    d = distribution(np.array([5.]), .2)
    assert d.pmf(5)[0] > 0
    assert d.sf(4)[0] > d.sf(5)[0]


@pytest.mark.parametrize("kind", ["shrunk_poisson", "shrunk_nb", "glm_poisson", "glm_nb"])
def test_exported_score_matches_fitted_estimator(kind):
    frame = build_pregame_features(games())
    frame["career_games_before"] = frame.groupby("player_id_espn").cumcount()
    predict, artifact = fit_candidate(frame, "assists", kind)
    assert np.allclose(predict(frame), score_artifact(artifact, frame, "assists"), atol=1e-12)
