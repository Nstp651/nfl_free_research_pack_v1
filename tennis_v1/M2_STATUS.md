# Tennis V1 — Milestone 2 Build Status

## Status

**MILESTONE 2: BLOCKED — ZERO_UPLOAD_TEST = FAIL_SERVE_STATS_GAP**

This is an intentional fail-closed result.

## What is implemented

- unattended Valuebetennis result ingestion;
- immediate market-column destruction before persistence;
- UCI CC BY 4.0 reference serve-stat ingestion;
- normalized parquet pack writer;
- source/retrieval/schema/quality lineage;
- stable player and tournament tables;
- deduplication;
- chronological overall Elo;
- chronological surface Elo with shrinkage;
- opponent-quality state;
- 7-day minutes workload;
- 14-day match workload;
- surface-transition state;
- deterministic asset hashes and manifest;
- current-season refresh CLI;
- 2021-current historical rebuild CLI;
- clean-environment GitHub Actions probe;
- explicit zero-upload acceptance gate.

## Normalized pack

The build writes:

- `matches.parquet`
- `match_stats.parquet`
- `players.parquet`
- `tournaments.parquet`
- `player_state_daily.parquet`
- `tournament_conditions.parquet`
- `manifest.json`
- `ZERO_UPLOAD_TEST.json`

`rankings.parquet` is deliberately replaced by internal chronological ratings for V1.

`points.parquet` remains optional and is not required.

## Historical rebuild

```bash
pip install -r tennis_v1/requirements.txt
PYTHONPATH=tennis_v1/src \
python tennis_v1/scripts/build_data_pack.py rebuild \
  --through-year 2026 \
  --output /tmp/tennis-pack
```

This programmatically retrieves every Valuebetennis season from 2021 through the requested year plus the UCI reference archive. No local input file is accepted.

## Current-season refresh

```bash
PYTHONPATH=tennis_v1/src \
python tennis_v1/scripts/build_data_pack.py refresh \
  --through-year 2026 \
  --output /tmp/tennis-refresh
```

The scheduled GitHub workflow runs the live source probe without requiring Nick's computer.

## Acceptance semantics

A clean environment can retrieve and normalize the selected free sources and derive results-based player states. It **cannot** create a credible M1 match input containing separate serve/return point strengths.

For that reason:

`ZERO_UPLOAD_TEST = FAIL_SERVE_STATS_GAP`

The gate will not be changed to PASS until a zero-cost, automated, rights-compatible ATP+WTA source supplies sufficiently deep/current match-level service statistics.

## Why score-only estimation was rejected

It is mathematically possible to fit latent strength from winners and set scores, but final scores do not identify who served each game or how points were won. A results-only model can estimate general player strength; it cannot robustly decompose serve and return skill to the standard required by the accepted M1 architecture.

M2 therefore does not weaken M1 simply to reach a green status.

## Cloudflare

No Cloudflare connector/action is available in the current tool surface, so this branch does not mutate the live Worker/R2/D1 environment. The GitHub build is self-contained and Cloudflare-compatible, but no live Cloudflare deployment is claimed.

Because the data-sufficiency gate is currently red, production publishing to Cloudflare is intentionally not activated.
