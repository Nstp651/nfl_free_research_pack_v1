# NBL Player Props V1

GitHub-first production build for Nick's NBL match-by-match player-prop model.

## Product shape
One Custom GPT / one fixture research pass / two independent quantitative heads:
- ASSISTS
- REBOUNDS

Run modes: `BOTH`, `ASSISTS_ONLY`, `REBOUNDS_ONLY`.

## Current build checkpoint
This branch now implements the shared market-blind source/data foundation **and the first temporal QBASE candidates**:
- official NBL/Genius Rosetta client with a deep schedule allow-list that strips embedded odds before Layers 0-2
- matchup research-pack builder
- historical nblR/nblr_data player + team environment ingestion
- leak-safe shifted pregame features
- separate ASSISTS and REBOUNDS candidate models
- season-by-season walk-forward validation
- OOS Negative-Binomial dispersion and threshold Brier calibration
- exact count / at-least / half-point / integer-push probability grids
- provider-agnostic market adapter contract
- live source acceptance + model CI

The first quantitative heads are candidates, not automatically promoted. CI/backtest evidence must pass before we lock V1 QBASE. After QBASE selection we build current-role translation, atomic dual-head freeze, Actions, market adapters and production GPT kit.

## Source policy
Layers 0-2 never read sportsbook lines, odds, prices, consensus or betting-derived fields.

Current structured source: nbl.com.au Rosetta / Genius Sports.
Historical source: JaseZiv/nblr_data public GitHub releases.

## Quantitative philosophy
Historical prediction uses only information available before the target game. Player/team/opponent rolling values are shifted one completed game before calculation. The historical models are conditional on the player taking the court; current availability and projected minutes remain explicit live-research inputs before freeze.

Model promotion is based on temporal out-of-sample threshold calibration first, then count error. No model family is promoted because it sounds more sophisticated.

## Market optionality
Post-freeze Layer 3 may use:
1. The Odds API if NBL assists/rebounds props are actually returned;
2. user sportsbook screenshots;
3. clean public-web prices on a best-effort basis only.

All three normalize to the same canonical market record, so P_model does not depend on market-source availability.
