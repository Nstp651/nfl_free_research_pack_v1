# NBL Player Props V1

GitHub-first production build for Nick's NBL match-by-match player-prop model.

## Product shape
One Custom GPT / one fixture research pass / two independent quantitative heads:
- ASSISTS
- REBOUNDS

Run modes: `BOTH`, `ASSISTS_ONLY`, `REBOUNDS_ONLY`.

## Current build checkpoint
This branch implements the shared market-blind source/data foundation:
- official NBL/Genius Rosetta client
- matchup research-pack builder
- historical nblR/nblr_data player-game ingestion
- pack integrity / market-contamination checks
- provider-agnostic market adapter contract
- live source acceptance + unit CI

The quantitative heads, walk-forward validation, dual-head freeze Worker, Actions and production GPT kit come next.

## Source policy
Layers 0-2 never read sportsbook lines, odds, prices, consensus or betting-derived fields.

Current structured source: nbl.com.au Rosetta / Genius Sports.
Historical source: JaseZiv/nblr_data public GitHub releases.

## Market optionality
Post-freeze Layer 3 may use:
1. The Odds API if NBL assists/rebounds props are actually returned;
2. user sportsbook screenshots;
3. clean public-web prices on a best-effort basis only.

All three normalize to the same canonical market record, so the P_model does not depend on market-source availability.
