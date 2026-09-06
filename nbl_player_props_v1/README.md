# NBL Player Props V1

GitHub-first production build for Nick's match-by-match NBL player-prop model.

## Product shape
One Custom GPT / one fixture research pass / two independent quantitative heads:
- ASSISTS
- REBOUNDS

Run modes: `BOTH` (default), `ASSISTS_ONLY`, `REBOUNDS_ONLY`.

## Production architecture
`market-blind structured priors -> current fixture/player research -> stat-specific scenarios -> server-authoritative QBASE translation -> atomic P_model freeze -> separate post-freeze market gateway -> ranking -> Nick Bet Tracker`

The Custom GPT orchestrates and performs current qualitative research; server-side Workers own identity, QBASE authority, immutable run state, probability generation and freeze integrity.

### Research / freeze Worker
- official NBL/Genius Rosetta fixture + roster source;
- immutable source commit / runtime-asset revision lock per run;
- one evidence-bound current research checkpoint;
- returning-player QBASE runtime score and minutes recomputation performed server-side;
- explicit prior-competition translation path for new-to-NBL players;
- persistent Durable Object matchup run;
- atomic BOTH-head freeze;
- immutable freeze receipt and per-player model hashes.

### Market Worker
Separate Worker with no authority to create or modify P_model. It:
- accepts only post-freeze observations;
- binds to exact run / freeze receipt / player-model hash;
- rejects observations captured before `frozen_at`;
- resolves player identity before cross-source deduplication;
- keeps best price by exact player/stat/side/threshold;
- maps exact integer/half-point frozen lines only;
- uses explicit push-aware EV;
- never forces a bet.

### Bet Tracker
A third Custom GPT Action connects to the existing Nick Bet Tracker after Layer 4. Frozen model selections are stored once; a real wager is recorded only after Nick explicitly confirms bookmaker, accepted odds and stake. Tracker data never feeds Layers 1-2.

## Historical source and QBASE
Free historical source: `JaseZiv/nblr_data` public releases.

Canonical source currently covers:
- 2015-16 through 2025-26;
- 36,428 player-game rows;
- 616 players;
- 1,572 matches;
- 100% game-time coverage;
- 100% latest-season minutes coverage after row-level seconds -> minutes fallback.

The 2026-27 preseason QBASE promotion gate requires training and walk-forward scoring through the latest completed season (2025-26), not merely presence of those rows in the source table.

Latest validated candidate evidence from CI:

| Head | OOS N | MAE | RMSE | Bias actual-pred | Mean threshold Brier | NB2 alpha | Early-season MAE |
|---|---:|---:|---:|---:|---:|---:|---:|
| ASSISTS | 24,208 | 1.1324 | 1.5896 | -0.0393 | 0.06244 | 0.14517 | 1.1532 |
| REBOUNDS | 24,208 | 1.8158 | 2.3931 | +0.0247 | 0.07548 | 0.13447 | 1.9049 |

Both selected Poisson mean models with temporal-OOS NB2 dispersion. Model-family selection is driven by temporal threshold calibration first, then count error; sophistication is never preferred narratively.

## Source / leakage policy
Layers 0-2 never read sportsbook odds, lines, prices, betting consensus or betting-derived features.

Historical player/team/opponent rolling features are shifted one completed game before every target observation. The QBASE is conditional on the player taking the court; current availability, minutes, role, lineup, coaching and import context are rebuilt before freeze.

## Early-season edge design
2025-26 production is statistical prior evidence for 2026-27. Current role is reconstructed from:
- roster turnover and imports;
- vacated minutes / creation / rebounding responsibility;
- new coaches and systems;
- projected starters and rotation;
- preseason / Blitz deployment;
- injuries and late news;
- prior-competition translation for new arrivals.

Prior-season production is never treated as current role by default.

## Runtime assets
`nbl_player_props_v1/data/manifest.json` cryptographically binds:
- immutable ASSISTS QBASE;
- immutable REBOUNDS QBASE;
- refreshable historical prior snapshot;
- source receipt.

Routine scheduled refresh updates the prior/source assets only. QBASE retraining/promotion is explicit and must pass latest-season plus quantitative gates.

## Production files
- `NBL_ASSISTS_REBOUNDS_4_LAYER_MASTER_PRODUCTION_V1.0.md`
- `GPT_INSTRUCTIONS_PRODUCTION_V1.0.md`
- `LAUNCH_PROMPT_PRODUCTION_V1.0.md`
- `INSTALL_PRODUCTION_V1.0.md`
- `openapi_v1.yaml` — Research/Freeze Action
- `market_openapi_v1.yaml` — Market Action
- `tracker_openapi_v1.yaml` — Nick Bet Tracker Action

## Final acceptance
Do not call V1 production-ready until the PR's production acceptance gates are closed: final CI, coherent promoted assets, both Cloudflare Workers healthy, all three Custom GPT Actions import cleanly, one live future-fixture BOTH freeze E2E, post-freeze market hash/timestamp acceptance, and Tracker health / real later confirmed-wager path.
