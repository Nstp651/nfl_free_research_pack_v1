from io import StringIO

import pandas as pd

from tennis_v1.data_pipeline import (
    build_players,
    build_tournaments,
    evaluate_coverage,
    normalize_results,
)
from tennis_v1.data_sources import (
    SOURCE_POLICIES,
    SourcePolicy,
    ValuebetennisSource,
    assert_market_blind,
    assert_source_policy_integrity,
    strip_market_columns,
)
from tennis_v1.ratings import build_player_states


CSV = """match_id,date,tournoi,tournoi_id,categorie,genre,surface,tour,joueur1,joueur1_id,joueur2,joueur2_id,cote1_ouverture,cote2_ouverture,cote1_cloture,cote2_cloture,vainqueur_id,score,duree_min
m1,2026-01-01T01:00:00Z,Sydney,11,Main tour,atp,hard,4,Alpha,1,Beta,2,1.50,2.70,1.55,2.60,1,6-4 6-4,90
m2,2026-01-03T01:00:00Z,Sydney,11,Main tour,atp,hard,5,Alpha,1,Gamma,3,1.40,3.00,1.45,2.90,3,4-6 6-3 4-6,130
m3,2026-01-01T03:00:00Z,Auckland,12,Main tour,wta,hard,4,Delta,4,Echo,5,1.80,2.00,1.85,1.95,4,6-2 6-3,70
"""


def normalized_fixture() -> pd.DataFrame:
    raw = pd.read_csv(StringIO(CSV))
    clean = strip_market_columns(raw)
    assert not any("cote" in c.lower() for c in clean.columns)
    return ValuebetennisSource().normalize(clean, pd.Timestamp("2026-01-04T00:00:00Z"))


def test_market_columns_are_destroyed_before_pack():
    df = normalized_fixture()
    assert_market_blind(df)
    assert not any("odds" in c.lower() or "cote" in c.lower() for c in df.columns)


def test_normalized_pack_has_stable_entities():
    matches = normalize_results([normalized_fixture()])
    players = build_players(matches)
    tournaments = build_tournaments(matches)
    assert len(matches) == 3
    assert set(players.player_id.astype(str)) == {"1", "2", "3", "4", "5"}
    assert len(tournaments) == 2


def test_states_are_pre_match_and_chronological():
    matches = normalize_results([normalized_fixture()])
    states = build_player_states(matches)
    alpha = states[(states.player_id.astype(str) == "1")].sort_values("event_date")
    assert len(alpha) == 2
    first, second = alpha.iloc[0], alpha.iloc[1]
    assert first.elo_overall_pre == 1500.0
    assert second.elo_overall_pre > first.elo_overall_pre
    assert second.matches_14d_pre == 1
    assert second.minutes_7d_pre == 90
    assert bool(second.surface_transition) is False


def test_zero_upload_gate_fails_without_current_multiseason_serve_stats():
    matches = normalize_results([normalized_fixture()])
    serve = pd.DataFrame({
        "tour": ["ATP", "WTA"],
        "event_year": [2013, 2013],
        "event_date": [pd.NaT, pd.NaT],
    })
    decision = evaluate_coverage(matches, serve, current_year=2026)
    assert decision.results_ready is True
    assert decision.serve_return_ready is False
    assert decision.tpi_ready is False
    assert decision.match_input_ready is False
    assert decision.zero_upload_status == "FAIL_SERVE_STATS_GAP"


def test_future_result_does_not_change_earlier_state():
    matches = normalize_results([normalized_fixture()])
    base = build_player_states(matches.iloc[:1])
    full = build_player_states(matches)
    base_a = base[(base.player_id.astype(str) == "1")].iloc[0]
    full_a = full[(full.player_id.astype(str) == "1")].sort_values("event_date").iloc[0]
    assert base_a.elo_overall_pre == full_a.elo_overall_pre == 1500.0



def test_all_registered_source_policies_pass_lineage_guard():
    assert_source_policy_integrity()
    assert SOURCE_POLICIES["valuebetennis_open_data"].production_eligible is True
    assert SOURCE_POLICIES["tennisvisuals_match_data"].production_eligible is False


def test_permissive_downstream_label_cannot_launder_prohibited_lineage():
    disguised = {
        "renamed_open_repo": SourcePolicy(
            key="renamed_open_repo",
            role="serve_stats",
            license="CC BY 4.0",
            automated_access=True,
            production_eligible=True,
            provenance_roots=("jeff_sackmann_tennis_abstract",),
            notes="A permissive downstream label cannot supersede upstream restrictions.",
        )
    }
    try:
        assert_source_policy_integrity(disguised)
    except AssertionError as exc:
        assert "prohibited provenance" in str(exc)
    else:
        raise AssertionError("prohibited upstream lineage was incorrectly accepted")


def test_nonautomated_source_cannot_be_marked_production_eligible():
    manual = {
        "manual_only": SourcePolicy(
            key="manual_only",
            role="serve_stats",
            license="CC BY 4.0",
            automated_access=False,
            production_eligible=True,
        )
    }
    try:
        assert_source_policy_integrity(manual)
    except AssertionError as exc:
        assert "not automatable" in str(exc)
    else:
        raise AssertionError("manual production dependency was incorrectly accepted")
