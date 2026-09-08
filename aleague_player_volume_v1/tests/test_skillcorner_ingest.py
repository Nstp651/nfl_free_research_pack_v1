import unittest

from aleague_player_volume_v1.ingest.skillcorner import build_role_profiles, git_blob_sha1, parse_aggregate, verify_git_blob
from aleague_player_volume_v1.model_core import ModelIntegrityError


OBR_HEADER = "competition_name,season_name,player_id,player_name,player_birthdate,team_id,team_name,position_group,minutes,offballrun_count_p30tip,behindrun_count_p30tip,aheadoftheballrun_count_p30tip,offballrun_count_shotwithin10s_p30tip,behindrun_count_shotwithin10s_p30tip,offballrun_count_targeted_p30tip,offballrun_count_received_p30tip,offballrun_count_penaltyarea_p30tip,offballrun_count_dangerous_p30tip,offballrun_count_dangerous_targeted_p30tip,offballrun_count_dangerous_received_p30tip\n"
PASS_HEADER = "competition_name,season_name,player_id,player_name,player_birthdate,team_id,team_name,position_group,minutes,passopportunity_count_p30tip,pass_count_shotwithin10s_p30tip,pass_count_attempted_p30tip,pass_count_completed_p30tip,pass_pct_completed,passopportunity_count_torun_p30tip,pass_count_torun_attempted_p30tip,pass_count_torun_completed_p30tip,pass_count_torun_shotwithin10s_p30tip,passopportunity_count_dangerous_p30tip,pass_count_dangerous_attempted_p30tip\n"
PHYS_HEADER = "competition_name,season_name,player_id,player_name,player_birthdate,team_id,team_name,position_group,minutes_full_all,total_metersperminute_full_all,hsr_count_full_all,sprint_count_full_all,hi_count_full_all,psv99,total_metersperminute_full_tip,hsr_count_full_tip,sprint_count_full_tip\n"


def row(prefix, values):
    return prefix + "," + ",".join(str(v) for v in values) + "\n"


class SkillCornerIngestTests(unittest.TestCase):
    def setUp(self):
        prefix = "AUS - A-League,2024/2025,211,Adam Taggart,1993-06-02,871,Perth Glory Football Club,Center Forward"
        self.obr = OBR_HEADER + row(prefix, [1000, 35, 9, 11, 3, 1, 15, 7, 9, 25, 10, 4])
        self.passing = PASS_HEADER + row(prefix, [1000, 50, 2, 20, 16, 80, 23, 9, 6, 1, 21, 6])
        self.physical = PHYS_HEADER + row(prefix, [1000, 108, 60, 11, 70, 29, 138, 30, 7])

    def test_git_blob_verification(self):
        raw = b"hello\n"
        expected = git_blob_sha1(raw)
        verify_git_blob(raw, expected)
        with self.assertRaises(ModelIntegrityError):
            verify_git_blob(raw, "0" * 40)

    def test_joined_profile_keeps_raw_feature_families(self):
        obr = parse_aggregate(self.obr, "obr")
        passing = parse_aggregate(self.passing, "passing")
        physical = parse_aggregate(self.physical, "physical")
        profiles, coverage = build_role_profiles(obr, passing, physical)
        self.assertEqual(len(profiles), 1)
        self.assertEqual(coverage["complete_join_rate"], 1.0)
        profile = profiles[0]
        self.assertEqual(profile["player_name"], "Adam Taggart")
        self.assertEqual(profile["model_use"], "ROLE_FEATURE_RESEARCH_ONLY_UNTIL_VALIDATED")
        self.assertEqual(profile["features"]["obr"]["offballrun_count_penaltyarea_p30tip"], 9.0)
        self.assertEqual(profile["features"]["physical"]["psv99"], 29.0)

    def test_wrong_competition_fails_closed(self):
        broken = self.obr.replace("AUS - A-League", "Other League")
        with self.assertRaises(ModelIntegrityError):
            parse_aggregate(broken, "obr")


if __name__ == "__main__":
    unittest.main()
