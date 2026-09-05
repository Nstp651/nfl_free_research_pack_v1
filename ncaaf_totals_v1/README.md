# NCAA Football Totals V1.1

Status: PRODUCTION CANDIDATE — infrastructure live; V1.1 integer-line upgrade under final CI/merge validation.

This directory contains Nick's fully automated NCAA Football full-game totals stack. It reuses the proven NFL production controls (immutable revisions, source receipts, Action-size guards, freshness checks, actual numerical execution and hard market separation) while operating on one full FBS-v-FBS weekly slate.

## Non-negotiable boundary

Layers 0-2 are PRE-MARKET ONLY.

- No sportsbook odds, spreads, totals, betting consensus or bookmaker data enter the research builder or QBASE.
- Every research/QBASE API response carries `market_data: false`.
- The source allow-list excludes sportsdataverse betting-line products.
- A week-W model may consume current-season structured team evidence only through W-1.
- The Odds API market Worker is separate and `getNcaafTotalsBoard` is POST-FREEZE ONLY.

## Universe

- NCAA Football / FBS
- FBS vs FBS only for V1 betting selection
- One research revision covers the entire target week
- One QBASE revision aligns to exactly one research revision
- Full-game totals only
- Both integer and half-point totals are first-class markets in V1.1

## Structured sources

Free public sportsdataverse/cfbfastR release assets:

1. `cfb_schedules` — fixtures, IDs, kickoff, home/away, FBS flags.
2. `cfb_team_summaries_weekly` — core as-of team research substrate.
3. `cfb_ratings_weekly` — independent adjusted rating family when published.
4. `cfb_returning_production` — preseason continuity context when published.
5. `cfb_team_talent` — preseason roster/talent context when published.

Current-season and prior-season evidence remain separate. Missing optional releases are limitations, never zero-filled facts.

## As-of / leakage rule

For target week W:

`current structured evidence through_week <= W - 1`

Week 1 therefore uses no 2026 weekly performance observations. Prior-season numbers remain statistical priors while current QB/personnel/coaching/system truth is rebuilt from current research.

## Quantitative baseline

`model/qbase_v0.1.0.json` is the selected market-blind Ridge QBASE.

Training / validation receipt:
- 7,428 FBS-v-FBS games, 2016-2025
- 5,152 temporal walk-forward scored games
- OOS MAE 13.03, RMSE 16.45
- Week 0/1 MAE 13.70
- Weeks 2-4 MAE 13.24
- Week 5+ MAE 12.88

Nonlinear challengers were tested and did not beat Ridge out-of-sample, so they were not promoted.

QBASE is an anchor, not automatically the final P_model. Current QB/personnel/weather/system information is translated after QBASE and before freeze.

## Integer + half-point probability grid

V1.1 freezes a 0.5-step grid from 20.0 through 100.5 before market access.

Half-point lines:
- `P_push = 0`
- standard Over/Under complement.

Integer line n:
- `P_under ~= F(n-0.5)`
- `P_push ~= F(n+0.5)-F(n-0.5)`
- `P_over ~= 1-F(n+0.5)`

The grid is audited for monotonicity and `Over + Push + Under = 1` at every line.

Push-aware price math is executable in `model/market_math.py` and tested in `tests/test_market_math.py`.

## Build flow

```text
sportsdataverse / cfbfastR releases
        |
        v
build_pack.py
  - source metadata + SHA receipts
  - FBS-v-FBS weekly slate
  - W-1 leak-free snapshots
  - current/prior/preseason profiles
  - source-quality guards
  - market-field denylist
        |
        v
data/manifest.json + data/slates/<season>/<slate_id>.json
        |
        v
score_slate.py + QBASE artifact
  - market-blind expected total
  - temporal OOS residual calibration
  - integer/half-point Over/Push/Under grid
        |
        v
Cloudflare research Worker
        |
        v
GPT current-information research + Layer 2 execution
        |
        v
ENTIRE SLATE P_MODEL FREEZE
        |
        v
Cloudflare market Worker -> The Odds API region=au, market=totals
        |
        v
exact frozen mapping + push-aware EV + slate ranking
```

## Live services

Research/model Worker:
`https://ncaaf-totals-research-pack-v1.nickarnott01.workers.dev`

Market Worker:
`https://ncaaf-totals-market-v1.nickarnott01.workers.dev`

Cloudflare native Git integration owns production deployment. GitHub Actions verify/test source; they do not carry Cloudflare deployment credentials.

### Cloudflare Git configuration

Research Worker:
- project: `ncaaf-totals-research-pack-v1`
- repo: `Nstp651/nfl_free_research_pack_v1`
- production branch: `main`
- root: `ncaaf_totals_v1`
- build: blank
- deploy: `npx wrangler deploy`

Market Worker:
- project: `ncaaf-totals-market-v1`
- production branch: `main`
- root: `ncaaf_totals_v1/market_worker`
- build: blank
- deploy: `npx wrangler deploy && printf '%s' "$ODDS_API_KEY" | npx wrangler secret put ODDS_API_KEY`
- `ODDS_API_KEY` exists only as an encrypted Cloudflare build secret and is installed as a runtime Worker secret during deploy.

## Live acceptance evidence

Live research acceptance passed for 2026 Week 1:
- 51 FBS-v-FBS games
- `pack_revision=491a09bd18f8a6ed`
- research health live / recent
- QBASE V0.1.0 served successfully
- no market data in research/QBASE path

A controlled AU market-board acceptance also passed. The live board returned 49 NCAA games overall; the first page included Sportsbet, TAB, TABtouch and PlayUp. Both integer and half-point total lines were observed. This acceptance consumed one Odds API request and is now manual-only so normal CI cannot spend market quota.

## Core files

- `build_pack.py` — source ingestion / weekly research pack
- `validate_pack.py` — independent pack integrity guard
- `model/train_qbase.py` — temporal QBASE training
- `model/score_slate.py` — QBASE slate scoring + integer/half-point probability grid
- `model/market_math.py` — pure push-aware post-freeze price math
- `worker/index.js` — read-only research/QBASE Worker
- `market_worker/index.js` — post-freeze AU totals gateway
- `openapi_v1_1.yaml` — V1.1 pre-market GPT Action schema
- `market_openapi_v1_1.yaml` — V1.1 post-freeze GPT Action schema
- `NCAA_TOTALS_4_LAYER_MASTER_API_ACTION_PRODUCTION_V1.1.md` — authoritative methodology
- `GPT_INSTRUCTIONS_PRODUCTION_V1.1.md` — production GPT orchestration instructions
- `DEPLOYMENT.md` — live deployment/runbook

## Automation ownership

- `ncaaf-refresh.yml` refreshes the research pack on schedule.
- `ncaaf-qbase-score.yml` regenerates QBASE slate outputs after data/model changes.
- `ncaaf-unit-tests.yml` runs Python + both Worker contract tests.
- `ncaaf-worker-deploy.yml` is verification-only; Cloudflare Git deploys research Worker.
- `ncaaf-market-worker.yml` is verification-only; Cloudflare Git deploys market Worker.
- `ncaaf-live-acceptance.yml` validates live health without consuming odds-board quota.
- `ncaaf-market-board-acceptance.yml` is manual-only because it consumes one real Odds API board request.

## Remaining production sign-off

Before calling V1.1 fully signed off:
1. merge the integer-line branch after all CI is green;
2. confirm live research Worker serves probability schema 0.2.0 with integer push rows;
3. import V1.1 research + market Action schemas into the custom GPT;
4. attach V1.1 master and paste V1.1 Instructions;
5. run one complete market-blind slate dry run through Layer 2 freeze;
6. run one controlled post-freeze market integration and verify push-aware ranking on an integer line if one is offered.

No new paid data service is required beyond the user's existing The Odds API subscription.