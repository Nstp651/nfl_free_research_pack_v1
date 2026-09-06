# Betting Platform V1 — Standard Architecture

Status: platform standard for all new Nick betting models.

## Purpose
Separate sport-specific modelling from shared production integrity. Each model keeps its own research and probability methodology, but every new production model uses the same control-plane lifecycle.

`versioned research -> authoritative run -> research checkpoint -> deterministic P_model -> immutable freeze -> server-gated market -> exact mapping -> deterministic edge/ranking -> receipts`

## Universal contracts
1. **Content-addressed source lock** — every run locks the exact published source revision plus cryptographic hashes of the exact research bytes loaded, fixture identity and eligibility timestamp before research. Runtime must not depend on a source-control REST API being available.
2. **Market blindness** — no sportsbook line, price, consensus, implied probability or betting-derived feature can enter Layers 0–2.
3. **Complete research checkpoint** — Layer 1 is persisted with evidence IDs, source/date, football/basketball pathway and declared gaps before Layer 2 can execute.
4. **Exact identity binding** — model records bind to checkpointed fixture/player IDs; no position-based or order-based joins.
5. **Deterministic numerical execution** — repeatable maths executes in code. Monte Carlo is used only where the model genuinely needs simulation and must preserve seed/draw receipts.
6. **Hard model audits** — allocation, probability coherence, scenario weights and model-specific invariants must pass in code before freeze.
7. **Immutable server freeze** — the complete model artifact is persisted atomically and receives cryptographic receipts.
8. **Server market gate** — the market service verifies the authoritative run and frozen artifact before any paid odds request is permitted.
9. **Exact post-freeze mapping** — only frozen thresholds/markets are eligible. No interpolation or post-market probability invention.
10. **Deterministic integration** — best price, implied probability, fair price, expected ROI and ranking are calculated in code from frozen probabilities and current prices.
11. **Post-freeze football/sport news** — material new information invalidates the run; prices alone never change P_model.
12. **Resumability/auditability** — a conversation failure must not destroy authoritative run state.
13. **Zero added infrastructure cost** — GitHub/open data + Cloudflare free-tier architecture by default; paid services require explicit approval.

## Shared platform state machine
`RESEARCH_IN_PROGRESS -> RESEARCH_COMPLETE -> FROZEN`

No reverse transition exists. Frozen state is immutable.

## Source-lock standard
For a published research object, the platform should persist a sport/model-specific published revision plus SHA-256 receipts over the exact bytes consumed by the run. The combined source anchor is checkpointed into Layer 1. A manifest/object publication race must be detected and retried or rejected. Source-control commit IDs may be stored as metadata when available, but must not be a runtime availability dependency.

## What remains model-specific
- research source stack and evidence hierarchy;
- feature engineering / role translation;
- probability distribution and calibration;
- market types and threshold semantics;
- confidence/fragility definitions;
- sport-specific ranking safeguards.

## Reference implementations
- NCAA Totals V1.1.3.1: first large-slate persistent/checkpointed architecture.
- NFL Receptions V5: first Platform V1 migration, content-addressed source lock and hard server-to-market freeze verification.
- NBL Assists/Rebounds and NBA Assists/Rebounds: build directly on Platform V1 rather than as standalone GPT architectures.

## Deployment ownership
GitHub stores code/data/tests and runs verification CI. Cloudflare native Git integration owns Worker deployment. Paid API keys remain encrypted Cloudflare runtime secrets and never enter GitHub.
