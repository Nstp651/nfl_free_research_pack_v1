# NCAA Totals V1.1.2 — Build Status

## Current state

**Production branch:** `main`

**V1.1.2 branch:** `hotfix/ncaaf-freeze-identity-v1.1.2`

**Repository hardening:** **PRODUCTION CANDIDATE — CI / LIVE REVALIDATION REQUIRED**

**Previous V1.1.1 freeze:** **RETIRED / INVALID**

The first full Custom GPT integration test proved the research and market transports but exposed an integrity contradiction between the recorded frozen P_model and the same QBASE revision. The market board correctly refused to be used against an uncertain anchor. V1.1.2 hardens the pre-freeze identity contract so this class of mismatch cannot pass freeze.

## V1.1.2 identity hardening

- Research and QBASE records MUST be joined by exact `game_id`; positional/index/zip/page-order pairing is prohibited.
- Missing or duplicate game IDs fail closed.
- QBASE home/away identity must equal the research fixture for the same game ID.
- Every QBASE game receives immutable `qbase_anchor_sha256` over game ID, teams, expected_total_qbase, residual bucket/SD and complete probability grid.
- Layer 2 must recompute and verify that anchor hash before using the game.
- Frozen receipt retains keyed QBASE total, anchor hash, QBASE-grid hash and frozen-grid hash per game.
- Zero contextual shift + unchanged distribution requires final total equal keyed QBASE total within 1e-9 and frozen-grid hash equal QBASE-grid hash.
- Entire eligible slate receives an order-independent `identity_receipt_sha256` before freeze.
- Post-freeze QBASE checks may verify the same keyed anchor only; they may never reconstruct or substitute a frozen value.
- New executable `model/freeze_identity.py` implements the identity/hash gate.
- Tests cover shuffled QBASE order, eligible subset filtering, duplicate/missing IDs, team mismatch, zero-shift anchor mismatch and zero-shift grid mismatch.
- New frozen contract: `model/frozen_pmodel_schema_v1_1_2.json`.
- New production master and sub-8k GPT Instructions: V1.1.2.

## Existing production controls retained

- Fully automated FBS-v-FBS market-blind research pack.
- W-1 leakage protection including Week 0/1 `NO_CURRENT_SEASON_STRUCTURED_DATA_USED` handling.
- Ridge QBASE V0.1.0 with temporal walk-forward validation.
- Probability schema 0.2.0, 20.0-100.5 in 0.5 increments.
- Explicit integer push probability and push-aware market math.
- Atomic research + QBASE refresh with exact research revision lock.
- Research and AU totals market Workers deployed through Cloudflare Git.
- Market board uses one NCAAF AU totals upstream call and applies requested time filtering locally.
- Exact post-freeze fixture/line mapping and market freshness gates.
- No sportsbook market access before P_model freeze.

## Required V1.1.2 sign-off sequence

1. Python/unit identity tests PASS.
2. Production gate PASS on a real 2026 slate.
3. Regenerated QBASE slate exposes valid per-game anchor hashes.
4. Research Worker serves the new QBASE revision cleanly.
5. Install V1.1.2 Instructions + Knowledge in the Custom GPT; update research Action schema only if required to expose the new anchor field. Market Action unchanged.
6. Start a BRAND-NEW conversation; the prior conversation is market-contaminated and its freeze is retired.
7. Run a clean pre-market dry run. Require `IDENTITY_BINDING_AUDIT: PASS`, `COMPLETE_MODEL_INTEGRITY_CONFIRMED`, and `P_MODEL_STATUS: FROZEN`.
8. Audit the per-game keyed QBASE/frozen identity receipt before any market call.
9. Run one controlled post-freeze market integration.
10. Only after `FINAL_NCAAF_TOTALS_SLATE_RANKING_COMPLETE` is reached may V1.1.2 be called end-to-end production live.

**Current V1.1.2 status: HARDENING BUILT; CI AND FRESH END-TO-END VALIDATION PENDING.**
