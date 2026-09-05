# NCAA Football Totals Research Pack v0.1

Status: BUILD / VALIDATION — not production-locked.

This directory is the research-infrastructure scaffold for Nick's fully automated NCAA Football game-totals model. It deliberately reuses the proven NFL pack controls (versioned source receipts, immutable revisions, Action-size guards, freshness checks and market separation) while changing the research grain from one NFL player-prop fixture to one full FBS-v-FBS weekly slate.

## Non-negotiable boundary

This service is PRE-MARKET RESEARCH ONLY.

- No sportsbook odds, spreads, totals, betting consensus or bookmaker data are downloaded by the builder.
- Every API response carries `market_data: false`.
- The source allow-list is explicit. The sportsdataverse `cfb_betting_lines` / betting datasets are not allowed.
- A week-W model may only consume current-season team snapshots with `through_week <= W-1`.
- Odds API access belongs after the model distribution is frozen and is outside this service.

## Initial universe

- NCAA Football / FBS
- Regular season
- FBS vs FBS only
- One research revision covers the entire target week
- Completed games can remain in the research manifest for auditability; the model run must independently enforce kickoff eligibility.

## Structured sources

Free public `sportsdataverse` release assets:

1. `cfb_schedules` — fixture IDs, teams, venue, kickoff, FBS flags.
2. `cfb_team_summaries_weekly` — 384-column as-of team research substrate.
3. `cfb_ratings_weekly` — a second opponent-adjusted rating system with different filtering.
4. `cfb_returning_production` — preseason continuity context when available.
5. `cfb_team_talent` — preseason roster/talent context when available.

The pack keeps current and prior-season evidence separate. It does not silently blend them; the model owns the early-season weighting and must explain it.

## As-of / leakage rule

For a target game in week `W`:

`current structured evidence through_week <= W - 1`

Week 1 therefore has no current-season weekly performance snapshot. The pack exposes prior-season and preseason context rather than treating missing current data as zero.

## Build flow

```text
sportsdataverse releases
        |
        v
build_pack.py
  - source metadata + SHA receipts
  - FBS-v-FBS weekly schedule
  - leak-free as-of snapshots
  - current/prior/preseason team profiles
  - opponent-adjustment sanity check
  - market-field denylist
        |
        v
data/manifest.json
+ data/slates/<season>/<slate_id>.json
        |
        v
Cloudflare Worker
  /health
  /v1/slates?season=&week=
  /v1/slates/{slate_id}?offset=&limit=&revision=
        |
        v
GPT Layer 1 structured research
```

The Worker pages by GAME, not player. It dynamically reduces the number of returned games to stay below the Action response limit while preserving one immutable slate revision.

## Why weekly snapshots matter

`cfb_team_summaries_weekly` and `cfb_ratings_weekly` are as-of products. The upstream model code explicitly documents that a week-W game must join to information through week W-1. This repository repeats that rule as a hard validation gate so the later NCAA model can be backtested without same-week leakage.

## Source-quality guard

The upstream project documented a 2026 issue where one earlier opponent-adjusted EPA build was almost identical to raw EPA. The builder therefore calculates a correlation sanity check when enough current rows exist. A suspiciously high adjusted-vs-raw correlation is surfaced as `PARTIAL` source health rather than silently trusted.

## Files

- `build_pack.py` — download, validate and build the active weekly research pack.
- `validate_pack.py` — independent output guard.
- `worker/index.js` — read-only Cloudflare Worker.
- `worker/index.test.mjs` — Worker contract tests.
- `openapi.yaml` — GPT Action schema.
- `wrangler.toml` — dedicated Worker package.
- `tests/test_build_pack.py` — market-lock / as-of unit tests.
- `MODEL_ARCHITECTURE.md` — NCAA totals four-layer architecture derived from the NFL production model.

## GitHub automation

`.github/workflows/ncaaf-refresh.yml` validates the code and refreshes the active data pack on a schedule. It commits only the generated `ncaaf_totals_v1/data` directory on `main`.

`.github/workflows/ncaaf-worker-deploy.yml` dry-runs the Worker on every relevant change. If repository secrets `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` are present, the same workflow deploys the dedicated Worker automatically.

## Production-lock requirements

Do not call this production-ready until all are observed:

1. Real 2026 release ingestion succeeds.
2. Target-week FBS-v-FBS fixture reconciliation succeeds.
3. Every current snapshot satisfies the W-1 rule.
4. Source hashes / timestamps are recorded.
5. No market key/source can enter the pack.
6. Worker pagination retrieves every game at one revision.
7. Live workers.dev health/list/slate calls pass.
8. GPT Action import and retrieval pass.
9. At least two full slates are manually reconciled against the source fixtures.
10. NCAA scoring-model calibration / backtest is completed separately before betting use.

Zero new paid data/services are required by this research pack.