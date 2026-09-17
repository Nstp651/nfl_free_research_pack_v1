# NFL Receptions V5.1.1 selection overlay

This directory contains the V5.1.1 **player-first selection revision** for the existing NFL Receptions V5 stack. It is intentionally not a probability-engine or infrastructure rebuild.

## Authoritative package

- `NFL_RECEPTIONS_V5.1.1_SELECTION_POLICY.md` — authoritative V5.1.1 selection override.
- `NFL_RECEPTIONS_V5.1.1_INTEGRATION_CONTRACT.md` — receipt-bound eligibility registry and real Worker-response contract.
- `GPT_INSTRUCTIONS_BUILDER_V5.1.1_R2.md` — current replacement Builder Instructions.
- `nfl_v511_selector.py` — deterministic downstream selector.
- `nfl_v511_adapter.py` — adapter for actual V5 Control + Market Worker responses.
- `openapi_builder_v511.json` — response-complete Control Action schema for the existing Worker.
- `market_openapi_v511.yaml` — response-complete Market Action schema for the existing Worker.
- `TRACKER_COMPAT_V5.1.1.md` — tracker recommendation/rank semantics.
- `INSTALL_AND_LIVE_ACCEPTANCE_V5.1.1.md` — install order and production merge gates.
- `RELEASE_VERIFICATION_V5.1.1_R3.json` — current verification state.

Regression tests are split across selector policy, Worker-response adapter, Action/Builder contract and tracker contract files. The dedicated GitHub workflow discovers all `test_*.py` files in this directory.

## Required underlying Knowledge

V5.1.1 is an overlay on the exact approved 17 September 2026 `NFL_RECEPTIONS_V5.1.0_MASTER.md`. That full master is deliberately not reconstructed here from truncated excerpts. Install the exact approved master unchanged; V5.1.1 explicitly overrides only its conflicting selection cutoffs, ladder dependency, readiness states and integration details.

## Production status

Draft PR / live-qualification stage. The reference + integration implementation is tested, but production is not upgraded until the GPT Instructions/Knowledge/Action schemas are installed and the fresh authenticated acceptance gates pass. Do not merge or label production-ready solely from unit/CI success.
