NEW NBL ASSISTS + REBOUNDS MODEL RUN — V1.0

Target Match: [TEAM A] vs [TEAM B]
AEST / Australia-Sydney Fixture Date: [DATE]
Run Mode: BOTH
Timing Mode: [PRE-MATCH / POST-TEAMS]

Start a NEW V1.0 run and complete the full four-layer workflow automatically for this exact NBL fixture.

1. Resolve the exact official fixture and start one persistent market-blind match run.
2. Retrieve the pinned research seed and complete the full current-information research layer for both teams and every relevant player. Rebuild current minutes/role/availability, with extra emphasis on imports, transfers, new roles, preseason/Blitz evidence, coaching/system changes and early-season uncertainty.
3. Checkpoint the completed research pack.
4. Build the independent ASSISTS and REBOUNDS P_models and atomically freeze BOTH heads before any sportsbook information is accessed.
5. Require P_MODEL_STATUS: FROZEN, immutable freeze receipt, per-player hashes and all required audits PASS.
6. Only after freeze, integrate valid post-freeze NBL player-prop markets available through the installed Market Action and/or screenshots I provide.
7. Use exact integer/half-point frozen probabilities, push-aware math, best valid price per exact market and no interpolation.
8. Rank BEST SINGLE plus genuine positive assists, rebounds and combined edges. Do not force a bet.

Maintain strict market blindness throughout Layers 0–2. Never change the frozen P_model after market access. If material basketball news invalidates the freeze, start a new market-blind run rather than repricing the old one.

Preserve the final run_id, frozen_at and freeze_receipt_sha256 so I can add supplemental post-freeze sportsbook screenshots to the same frozen model.
