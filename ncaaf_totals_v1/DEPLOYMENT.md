# NCAA Totals V1.1 — Production Deployment Runbook

Two dedicated Cloudflare Workers deploy from the existing GitHub repository via Cloudflare native Git integration. The NFL Worker is not a deployment target of either NCAA project.

## Services

### Research/model Worker
- name: `ncaaf-totals-research-pack-v1`
- root directory: `ncaaf_totals_v1`
- config: `wrangler.toml`
- production URL: `https://ncaaf-totals-research-pack-v1.nickarnott01.workers.dev`
- serves market-blind research pack, QBASE artifact and paginated QBASE slate outputs
- deploy command: `npx wrangler deploy`

### Market Worker
- name: `ncaaf-totals-market-v1`
- root directory: `ncaaf_totals_v1/market_worker`
- config: `wrangler.toml`
- production URL: `https://ncaaf-totals-market-v1.nickarnott01.workers.dev`
- serves POST-FREEZE The Odds API `region=au&market=totals`
- deploy command: `npx wrangler deploy && printf '%s' "$ODDS_API_KEY" | npx wrangler secret put ODDS_API_KEY`

## Secrets

Cloudflare, not GitHub, owns the market API secret.

`ODDS_API_KEY` is configured as an encrypted Cloudflare BUILD secret for the market project. The deploy command installs the same value as the runtime Worker secret expected by `env.ODDS_API_KEY`.

Do not commit the key, add it to wrangler vars, print it in CI, or place it in GitHub Actions secrets.

The research Worker requires no secret.

## Deployment ownership

Cloudflare native Git integration is the only production deployment owner.

On a `main` push affecting a project, Cloudflare builds from that project's configured root and deploys it. GitHub workflows are verification-only so two independent systems cannot race to deploy the same Worker.

GitHub automation:
- `ncaaf-refresh.yml` — scheduled source refresh + validated research-pack commit.
- `ncaaf-qbase-score.yml` — regenerate aligned QBASE slate outputs.
- `ncaaf-unit-tests.yml` — Python and Worker tests.
- `ncaaf-worker-deploy.yml` — research Worker source/dry-run verification only.
- `ncaaf-market-worker.yml` — market Worker source/dry-run verification only.
- `ncaaf-live-acceptance.yml` — live research + market health; no odds board request.
- `ncaaf-market-board-acceptance.yml` — manual-only live market acceptance; consumes Odds API quota.

## V1.1 pre-merge gates

Require:
- Python unit tests PASS, including push-aware market math.
- Research Worker contract tests PASS.
- Market Worker contract tests PASS.
- Both Wrangler dry-runs PASS.
- Real-source 2026 pack build/validation PASS.
- QBASE output is market-blind and aligned to research revision.
- probability schema 0.2.0 supports 20.0-100.5 in 0.5 increments.
- integer rows have explicit non-negative push probability.
- half-point rows have push=0.
- every row satisfies Over+Push+Under=1 and monotonicity audits.
- no sportsbook/market fields in research/QBASE artifacts.
- V1.1 master, GPT Instructions and both Action schemas agree on push-aware math.

## Live acceptance evidence already completed

### Research/model
Live health acceptance passed:
- service `NCAAF_TOTALS_RESEARCH_PACK`
- `market_data=false`
- 2026 Week 1 slate `2026_01`
- 51 games
- pack revision `491a09bd18f8a6ed`
- QBASE V0.1.0 served successfully

### Market gateway
Health acceptance passed with:
- configured=true
- sport_key `americanfootball_ncaaf`
- region `au`
- market_group `ncaaf-totals`
- market_key `totals`

A controlled live market-board acceptance then passed separately. It found 49 current NCAA games and AU totals from Sportsbet, TAB, TABtouch and PlayUp on the sampled page. Both whole-number and half-point totals were present. That test consumed one request and the workflow is now manual-only.

## Post-merge V1.1 acceptance

Research/model Worker:
1. `/health` -> HTTP 200, correct service, market_data=false.
2. `/v1/slates?season=2026&week=<target>` -> one exact slate.
3. all `/v1/slates/{slate_id}` pages -> one pack_revision, unique count = manifest game_count.
4. `/v1/model/qbase` -> QBASE V0.1.0, market_data=false.
5. all `/v1/qbase/{slate_id}` pages -> one qbase_revision aligned to research revision.
6. require `probability_schema_version=0.2.0`, `integer_line_method=continuity_corrected_discrete_mass`, integer push rows and half-point push=0.

Market Worker:
1. `/health` -> HTTP 200, configured=true; health must make no Odds API request.
2. Do not call `/v1/totals` in ordinary acceptance or before a model freeze.
3. A controlled POST-FREEZE run may call the board and must exact-map only to frozen integer/half-point lines.

## Custom GPT production files

Install TWO Actions with Authentication=None:
- pre-market: `ncaaf_totals_v1/openapi_v1_1.yaml`
- post-freeze: `ncaaf_totals_v1/market_openapi_v1_1.yaml`

Attach as authoritative Knowledge:
- `NCAA_TOTALS_4_LAYER_MASTER_API_ACTION_PRODUCTION_V1.1.md`

Paste into GPT Instructions:
- `GPT_INSTRUCTIONS_PRODUCTION_V1.1.md`

Do not install V1.0 schemas/instructions for the production GPT after V1.1 is promoted.

## Final production sign-off

V1.1 is fully signed off only after:
1. branch CI passes and V1.1 merges to `main`;
2. Cloudflare auto-deploy completes;
3. live research/QBASE endpoint shows the V1.1 probability schema;
4. both GPT Actions import and test successfully;
5. one complete full-slate run reaches a valid market-blind Layer 2 freeze;
6. one controlled post-freeze market integration completes and integer push math is verified if an integer line is available.

A green GitHub build alone is never represented as a successful live deployment.