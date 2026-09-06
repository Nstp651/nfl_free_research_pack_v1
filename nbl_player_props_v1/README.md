# NBL Player Props V1

GitHub-first production build for Nick's NBL match-by-match player-prop model.

## Product shape
One Custom GPT / one fixture research pass / two independent quantitative heads:
- ASSISTS
- REBOUNDS

Run modes: `BOTH`, `ASSISTS_ONLY`, `REBOUNDS_ONLY`.

## Current build checkpoint
The feature branch now contains the complete V1 source architecture rather than only a data/model prototype:
- official NBL/Genius Rosetta fixture and roster client with strict market-boundary sanitization;
- free historical nblR/nblr_data player-game spine;
- leak-safe shifted pregame features and temporal walk-forward validation;
- independently trained ASSISTS and REBOUNDS QBASE heads;
- temporal-OOS NB2 dispersion and exact count / at-least / half-point / integer-push probability grids;
- canonical immutable QBASE artifacts and historical prior snapshot under `data/manifest.json`;
- routine prior refresh architecture with QBASE retraining explicit-only;
- server-side returning-player QBASE runtime scoring and minutes recomputation;
- explicit prior-competition translation contract for new-to-NBL players;
- evidence-bound current research checkpoint;
- Durable Object persistent match run and atomic dual-head freeze;
- immutable freeze receipt plus independent `player_model_sha256` binding for each full frozen player payload;
- separate post-freeze Market Worker with exact freeze/player binding, post-freeze timestamp enforcement, cross-source best-price deduplication, exact-threshold mapping and push-aware EV;
- Custom GPT Research and Market OpenAPI schemas;
- production methodology, Instructions, launch prompt and install guide;
- Python reference implementation and JS/Python integrity tests.

The branch remains a draft until repository verification, Cloudflare deployment health and real Custom GPT Action/E2E acceptance are all demonstrated. Source completeness is not the same as production acceptance.

## Source policy
Layers 0-2 never read sportsbook lines, odds, prices, consensus or betting-derived fields.

Current structured source: nbl.com.au Rosetta / Genius Sports.
Historical source: JaseZiv/nblr_data public GitHub releases.

Current reporting and official team/NBL evidence are researched separately by the GPT and checkpointed before freeze. Structured historical data is a prior, not current-role truth.

## Quantitative philosophy
Historical prediction uses only information available before the target game. Player/team/opponent rolling values are shifted one completed game before calculation. The historical heads are conditional on the player taking the court; current availability, minutes and role remain explicit live-research inputs.

Returning-player QBASE means are server-authoritative. Context can move the final P_model only through explicit evidence-bound scenarios. New-to-NBL players are handled through prior-competition translation with explicit uncertainty rather than silent average imputation.

Model promotion is based on temporal out-of-sample calibration and count error. Routine data refreshes update priors without silently retraining QBASE.

## Market optionality
Post-freeze Layer 3 may use:
1. The Odds API if NBL assists/rebounds props are actually returned;
2. user sportsbook screenshots, including Bet365;
3. clean public-web prices on a best-effort basis.

Every observation must be captured at or after the immutable `frozen_at`. Rows are resolved to the exact frozen player first, then the best valid price is retained for each exact player/stat/side/threshold. P_model never depends on market-source availability.

## Production files
- `NBL_ASSISTS_REBOUNDS_4_LAYER_MASTER_PRODUCTION_V1.0.md`
- `GPT_INSTRUCTIONS_PRODUCTION_V1.0.md`
- `LAUNCH_PROMPT_PRODUCTION_V1.0.md`
- `INSTALL_PRODUCTION_V1.0.md`
- `openapi_v1.yaml`
- `market_openapi_v1.yaml`

## Production acceptance gate
Do not call V1 production-ready until:
- unit/integrity suites pass;
- Research Worker verification passes;
- Market Worker verification passes;
- Cloudflare production health is confirmed;
- both Custom GPT Action schemas import cleanly;
- one live future-fixture BOTH run freezes atomically and preserves receipt/hash identity on retry;
- post-freeze market evaluation verifies exact freeze receipt and per-player payload hash;
- pre-freeze and pre-frozen_at market attempts are rejected.
