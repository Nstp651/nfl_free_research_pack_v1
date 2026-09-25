# Tennis V1 Source Audit

## Decision standard

A source may enter the production P-model only if its usage rights are compatible with a persistent quantitative betting system. Public accessibility is not treated as permission for production use.

## Production candidates

### Sportradar Tennis API — preferred production source

**Status:** eligible subject to account/license terms.

Why it fits:
- ATP/WTA schedules, competitors and rankings.
- historical results and player histories.
- standard match stats including aces, double faults, first/second serve points won, first/second serves made, service games won and break points.
- point-by-point timelines for covered competitions.
- documented coverage tiers across Grand Slams, ATP and WTA events.

V1 use:
- ingest schedules/results, player IDs, ranking snapshots, surfaces, match stats and point timelines where licensed.
- do **not** ingest Sportradar probabilities or odds into P-model construction.

### API-Tennis — secondary vendor candidate

**Status:** technically suitable; commercial/legal review required before production promotion.

Why it fits:
- fixtures, scores, point-by-point and match statistics are exposed through a subscription API.
- product terms are written for application/developer use and do not impose the obvious non-commercial restriction seen in the excluded public datasets.

V1 use:
- optional adapter only after subscription terms are confirmed for K&J use.
- never ingest its odds endpoint; The Odds API remains the sole price source.

## Excluded from production P-model

### Jeff Sackmann / Tennis Abstract datasets

**Status:** excluded.

Reason: ATP/WTA match databases and Match Charting Project data are licensed CC BY-NC-SA 4.0 / non-commercial. The Match Charting Project explicitly states non-commercial use only.

This includes mirrors and derivatives that do not independently establish broader rights.

### ATP website/stat pages

**Status:** excluded from systematic production ingestion.

Reason: ATP terms prohibit systematic retrieval and prohibit gambling/wagering use without express permission.

### Tennis-Data.co.uk historical files

**Status:** excluded.

Reason: site states data is intended for private individuals only and not commercial/data-training products using automated bots/scrapers/AI. This is not a safe production ingestion basis.

### LiveTennisAPI academic point-by-point dataset

**Status:** excluded.

Reason: dataset is restricted to non-commercial academic research/teaching.

### UTR Engage API

**Status:** excluded from modelling.

Reason: published API terms restrict API data to narrow display/internal purposes and expressly prohibit analytics, research, AI/model use and persistent historical storage beyond short caching windows.

## Research-only references

Open-source simulation code may be reviewed for implementation ideas when its software license permits it, but no restricted dataset may be copied into the production pack. Model mathematics must be independently implemented and source data lineage retained.

## Pack data contract

The production pack stores normalized, source-attributed records rather than raw website scrapes:

- `players.parquet`
- `rankings.parquet`
- `matches.parquet`
- `match_stats.parquet`
- `points.parquet` where licensed
- `tournaments.parquet`
- `tournament_conditions.parquet`
- `player_state_daily.parquet`
- `run_inputs/<run_id>.json`

Every row includes `source_provider`, `source_record_id`, `retrieved_at_utc`, and a provider-license/version tag where available.
