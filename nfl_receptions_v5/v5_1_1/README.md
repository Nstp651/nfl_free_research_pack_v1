# NFL Receptions V5.1.1 selection overlay

This directory contains the V5.1.1 **selection-policy revision** for the existing NFL Receptions V5 stack.

It is intentionally not a probability-engine or infrastructure rebuild.

## Files

- `NFL_RECEPTIONS_V5.1.1_SELECTION_POLICY.md` — authoritative V5.1.1 selection override.
- `GPT_INSTRUCTIONS_BUILDER_V5.1.1.md` — replacement Builder Instructions for this policy.
- `nfl_v511_selector.py` — deterministic downstream reference selector.
- `test_nfl_v511_selector.py` — synthetic regression suite.
- `AUDIT_AND_RELEASE_V5.1.1.md` — scope, rationale, tests and acceptance status.
- `RELEASE_VERIFICATION_V5.1.1.json` — release metadata and source hashes.

## Required underlying Knowledge

V5.1.1 is an overlay on the existing consolidated `NFL_RECEPTIONS_V5.1.0_MASTER.md` release. That full master is not reconstructed in this directory. Install the exact existing V5.1.0 master together with the V5.1.1 policy and Builder Instructions.

Do not substitute a partial/truncated copy of the master.

## Production status

Reference implementation only until actual V5 Action response mapping and authenticated live acceptance pass. Do not describe production as upgraded merely because the local regression suite passes.
