# NCAA Totals V1.1 — Build Status

## Current state

**Branch:** `feature/ncaaf-integer-totals-v1.1`

**Target:** production promotion to `main` after all V1.1 code gates pass.

## Completed

- Fully automated FBS-v-FBS weekly research-pack builder.
- W-1 current-season leakage protection.
- Versioned immutable research slate revisions.
- Market-blind Ridge QBASE V0.1.0 with temporal walk-forward validation.
- Full-slate QBASE scoring.
- V1.1 probability schema 0.2.0 covering totals 20.0-100.5 in 0.5 increments.
- Explicit integer-line push probability and half-point push=0.
- Push-aware fair-price / break-even / edge / ROI math.
- Deterministic post-freeze fixture/line/price integration with conservative matching and freshness gates.
- Dedicated research and market Cloudflare Workers.
- Cloudflare native Git deployment connected to `main`.
- Market secret held in Cloudflare, not source control.
- Live research Worker health accepted.
- Live market Worker configuration health accepted without an odds-board request.
- Controlled one-time AU market-board acceptance passed; Sportsbet, TAB, TABtouch and PlayUp observed; both integer and half-point totals observed.
- Real market-board acceptance workflow converted to manual-only to protect Odds API quota and freeze discipline.
- GitHub Worker deployment workflows converted to verification-only so Cloudflare Git is the sole production deploy owner.
- Season-aware scheduled research refresh: January resolves prior NCAA season; August-December current season; no off-season cron runs.
- Dynamic live acceptance resolves the currently published slate and retrieves every research/QBASE page at one revision.
- V1.1 authoritative master, sub-8k GPT Instructions and separate research/market Action schemas prepared.
- Frozen P_model JSON contract schema added.

## Production gates required before merge

1. Python integrity tests PASS.
2. Research Worker contract tests PASS.
3. Market Worker contract tests PASS.
4. Both Wrangler dry-runs PASS.
5. Real 2026 Week 1 source build/validation PASS.
6. Real QBASE slate scoring PASS with probability schema 0.2.0.
7. Integer/half-point partition + monotonicity audits PASS.
8. V1.1 GPT Instructions < 8000 characters.
9. Market-boundary denylist PASS.
10. Compare branch to `main`; NCAA-only changes reviewed.

## Post-merge live acceptance

After merge, Cloudflare Git must deploy the research Worker automatically. Then require:
- research `/health` HTTP 200;
- current published research slate fully paginated at one revision;
- QBASE artifact valid;
- QBASE slate fully paginated at one revision;
- `probability_schema_version=0.2.0`;
- integer rows carry push probability;
- half-point rows have push=0;
- market `/health` configured=true;
- no market-board call during ordinary acceptance.

## Final custom-GPT sign-off

Manual GPT UI work remains after production code/live acceptance:
- import `openapi_v1_1.yaml`;
- import `market_openapi_v1_1.yaml`;
- attach `NCAA_TOTALS_4_LAYER_MASTER_API_ACTION_PRODUCTION_V1.1.md`;
- paste `GPT_INSTRUCTIONS_PRODUCTION_V1.1.md`;
- enable calculation/Data Analysis capability;
- run one full market-blind slate through Layer 2 freeze;
- only then run one controlled post-freeze market integration and verify an integer-line push calculation if offered.

Until those checks pass, status is **PRODUCTION CANDIDATE**, not signed-off production.