# NFL Receptions V5.1.1 — Selection Audit and Release Note

## Scope

This revision addresses the post-V5.1 NO BET overcorrection without redesigning the receptions probability engine.

Unchanged:
- receptions-only scope;
- V5 control plane and exact HBB engine;
- market-blind research/checkpoint;
- immutable server freeze;
- Odds API market gateway;
- tracker and settlement architecture;
- player-first decision structure;
- WR/TE/RB equality based on actual receiving role;
- raw `positive_edge_ranked` retained for audit only.

Changed:
- universal 50% CORE floor removed;
- STANDARD CORE now starts at 30% with >=2pp edge and >=5% ROI;
- a stricter 20–30% SUPPORTED LOWER-HIT CORE path is permitted only at >=3pp edge, >=10% ROI, HIGH Confidence, LOW player Fragility and explicit LOW threshold Fragility;
- sub-20% rows cannot select the player;
- higher ladder rungs are assessed independently; a missing intermediate rung no longer blocks a supported stretch;
- edge bands (PLAYABLE / STRONG / PREMIUM) enter deterministic anchor ordering before raw edge;
- optional STRETCH floor is 12% with stronger reliability/value gates.

## Why

The V5.1.0 draft correctly solved the Palmer-style raw-ROI longshot problem, but the 50% CORE threshold turned hit probability into a blunt veto. That is unlike the desired actionable-edge model: model probability and market edge should be considered together after role/reliability gating.

V5.1.1 does not treat every positive edge as a bet. It creates two explicit primary paths and keeps true tails out of player selection.

## Regression result

`python3 -m unittest -v` against `test_nfl_v511_selector.py`:

- 36 tests run
- 36 passed

Coverage includes:
- Palmer-style tail exclusion;
- sub-20% primary exclusion regardless of price;
- 30% STANDARD CORE boundary;
- 20–30% supported-lower-hit qualification and reliability failures;
- LOW Confidence / HIGH Fragility rejection;
- WR/TE/RB equality;
- verified role expansion;
- stale/future quote rejection;
- current best-price deduplication;
- independent stretch without intermediate ladder;
- CORE-only result;
- missing threshold metadata behavior;
- negative value and price-refresh removal;
- complete-board gate;
- frozen probability conflict and ladder inversion failures;
- dynamic minimum-price rounding;
- payoff dominance;
- deterministic ties;
- old 22-row positive-edge example no longer being automatically NO BET when a synthetic candidate is given top-tier eligibility/reliability.

That final synthetic case is **not a live recommendation**. Real identity, role, evidence, Confidence, Fragility, exact unrounded probability and current price still control eligibility.

## Production status

This branch is a policy/reference implementation only until live acceptance is completed against actual V5 Action responses. Do not call production upgraded until:

1. Builder Instructions + V5.1 master + V5.1.1 policy are installed together;
2. the real response-to-selector adapter is verified with actual field names;
3. complete-board retrieval and timestamps are proven;
4. a fresh authenticated fixture run passes end-to-end without changing freeze hashes;
5. tracker recommendation semantics are verified or explicitly disclosed unsupported;
6. a price-only refresh changes only selection output;
7. prospective monitoring compares V5.0 raw ROI, V5.1.0 50% policy and V5.1.1 actionable policy using identical as-of inputs.

No Cloudflare deployment, Worker schema migration or tracker schema change is required by this revision.
