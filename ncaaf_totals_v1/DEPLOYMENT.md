# NCAA Totals V1 — Production Deployment Runbook

This deploys TWO dedicated Cloudflare Workers from the existing GitHub repository without changing the NFL Worker.

## Services

1. Research/model Worker
   - name: `ncaaf-totals-research-pack-v1`
   - config: `ncaaf_totals_v1/wrangler.toml`
   - serves market-blind research pack, QBASE artifact and paginated QBASE slate outputs
   - expected URL: `https://ncaaf-totals-research-pack-v1.nickarnott01.workers.dev`

2. Market Worker
   - name: `ncaaf-totals-market-v1`
   - config: `ncaaf_totals_v1/market_worker/wrangler.toml`
   - serves POST-FREEZE NCAA full-game totals from The Odds API `region=au&market=totals`
   - expected URL: `https://ncaaf-totals-market-v1.nickarnott01.workers.dev`

## GitHub Actions credentials

Repository Actions secrets required before main deployment:
- `CLOUDFLARE_API_TOKEN`
- `CLOUDFLARE_ACCOUNT_ID`
- `ODDS_API_KEY`

Do not place secret values in source code or wrangler variables. The market deployment workflow installs `ODDS_API_KEY` as a Cloudflare Worker secret after deployment.

The existing NFL service is not a deployment target of any NCAA workflow.

## Pre-merge gates

Require on `feature/ncaaf-totals-v1`:
- Python unit tests PASS.
- Worker contract tests PASS.
- Market Worker contract tests PASS.
- Wrangler dry runs PASS.
- Real-source 2026 pack build/validation PASS.
- QBASE scorer produces a market-blind slate with monotonic/complementary probability ladders.
- QBASE nonlinear challenger audit reviewed; do not promote a challenger automatically.
- no sportsbook/market fields in research/QBASE artifacts.

## Merge/deploy behavior

After merge to `main`:
- `ncaaf-refresh.yml` owns periodic research-pack refreshes.
- `ncaaf-qbase-score.yml` regenerates aligned QBASE slate outputs when research data/model changes.
- `ncaaf-worker-deploy.yml` verifies then deploys the research/model Worker when Cloudflare credentials exist.
- `ncaaf-market-worker.yml` verifies then deploys the market Worker and installs `ODDS_API_KEY` when all three secrets exist.

If secrets are absent, verification remains useful and the deploy job explicitly skips instead of fabricating success.

## Live acceptance

Research/model Worker:
1. `/health` returns HTTP 200, `service=NCAAF_TOTALS_RESEARCH_PACK`, `market_data=false`.
2. `/v1/slates?season=2026&week=<target>` resolves one exact slate.
3. Fetch all `/v1/slates/{slate_id}` pages at one `pack_revision`; total unique games = manifest `game_count`.
4. `/v1/model/qbase` returns model V0.1.0 with `market_data=false`.
5. Fetch all `/v1/qbase/{slate_id}` pages at one `qbase_revision`; require aligned `research_pack_revision` and identical game universe.

Market Worker:
1. `/health` returns HTTP 200, configured=true, `region=au`, `market_key=totals` and makes no odds request.
2. POST-FREEZE acceptance call to `/v1/totals` returns `sport_key=americanfootball_ncaaf`, `market_group=ncaaf-totals`, one immutable `board_revision`, valid decimal outcomes and no unsupported market family.
3. Reconcile at least three returned fixtures by both teams and kickoff.

## Custom GPT Actions

Install as separate Actions:
- pre-market schema: `ncaaf_totals_v1/openapi.yaml`
- post-freeze schema: `ncaaf_totals_v1/market_openapi.yaml`

Authentication: None at the GPT Action layer; the public Workers contain no user secret in responses. The market Worker keeps the Odds API key in Cloudflare secrets.

Paste `GPT_INSTRUCTIONS_PRODUCTION_V1.0.md` into the GPT Instructions and attach `NCAA_TOTALS_4_LAYER_MASTER_API_ACTION_PRODUCTION_V1.0.md` as authoritative Knowledge.

## Production sign-off

Production is signed off only after live Worker acceptance and one complete dry run through Layer 2 freeze plus one controlled post-freeze market integration. A successful GitHub build alone is not a claim that Cloudflare/Action production is live.