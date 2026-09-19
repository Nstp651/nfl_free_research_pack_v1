from pathlib import Path


def test_v11_instruction_contract():
    root = Path(__file__).resolve().parents[1]
    instructions = (root / "GPT_INSTRUCTIONS_PRODUCTION_V1.1.md").read_text()
    policy = (root / "NBL_ASSISTS_REBOUNDS_V1.1_PLAYER_FIRST_SELECTION_ADDENDUM.md").read_text()

    assert len(instructions.encode("utf-8")) < 8000
    assert "Do NOT call Odds API for NBL player props." in instructions
    assert "MARKET INPUT REQUIRED — upload sportsbook screenshots." in instructions
    assert "p < .30" in instructions
    assert "Raw EV rank never selects the winner." in instructions

    assert "NBL_PLAYER_PROPS_PLAYER_FIRST_1.1" in policy
    assert "screenshot-only" in policy
    assert "actionability probability >= 40%" in policy
    assert "30% <= actionability probability < 40%" in policy
    assert "can never be CORE" in policy
