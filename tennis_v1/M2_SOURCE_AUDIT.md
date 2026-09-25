# Tennis V1 — Milestone 2 Zero-Cost Source Audit

Audit date: 2026-09-25.

## Decision

A legitimate zero-cost automated **results** backbone exists. A legitimate zero-cost automated **current multi-season match-level serve/return statistics** backbone was not found.

Therefore Milestone 2 is **blocked**, not promoted.

## Decision table

| Source | ATP | WTA | Depth / freshness | Serve-return stats | Automation | Rights fit | M2 decision |
|---|---|---|---|---|---|---|---|
| Valuebetennis open CSV | Yes | Yes | 2021-current; current season refreshed | No | Stable per-season CSV URLs | CC BY 4.0; explicit commercial reuse | **ACCEPT results metadata only** |
| UCI Tennis Major Tournament Match Statistics | Yes | Yes | Four majors, 2013 only | Partial match-level serve stats | Stable ZIP download | CC BY 4.0 | **ACCEPT reference/test only; insufficient for training** |
| TennisData.App free CSV | Yes | Yes | 2021-current | Broad stats on site | CSV available, but ToS prohibit scripts/systematic extraction | Personal/non-commercial service terms | **REJECT** |
| Jeff Sackmann / Tennis Abstract / mirrors | Yes | Yes | Deep/current mirrors exist | Yes | GitHub | CC BY-NC-SA 4.0 | **REJECT** |
| TML Database | Yes | No production WTA equivalent | Deep/current ATP | Yes | GitHub/site API | Non-commercial; based on ATP/Sackmann sources | **REJECT** |
| serve-and-volley ATP scraper/data | Yes | No | 1991-2022/23 | Yes | GitHub | Scrapes ATP official site; ATP terms conflict with production wagering/systematic use | **REJECT** |
| Live Tennis API free tier | Yes | Yes | Live/upcoming only at free tier | Detailed stats are paid | API | Free tier insufficient; stats/historical bulk paid | **REJECT for zero-cost M2** |
| Tennis-API.com / SportsAPI365 Free | Yes | Yes | Core results/rankings; 50 requests/day | Exact match serve/return endpoints exist but advanced stats are not on Free | Authenticated REST API | Provider explicitly supports betting/model use, but useful serve-stat access requires paid tier and free quota cannot rebuild history | **REJECT for zero-cost M2** |
| Live Tennis API academic point data | Yes | Yes | 2023-current | Point-by-point | Bulk snapshots | Non-commercial academic research only | **REJECT** |
| ppaulojr / legacy point-by-point corpus | Yes | Yes | Mostly 2012-2015 | Point-by-point | GitHub | Sackmann lineage/non-commercial; stale | **REJECT** |
| Open Tennis Data v3 | Yes | Yes | 2020-current preview | Explicitly no match stats | GitHub Releases | Source-specific obligations; not a serve-stat source | **REJECT as unnecessary/incomplete** |
| Mendeley 2007-2021 derivative | Yes | Yes | Through 2021 | No required serve backbone | Downloadable | CC BY wrapper but derived from tennis-data.co.uk; upstream rights conflict unresolved | **REJECT** |
| Zenodo ATP 2020-23 aggregate stats | Yes | No | 2020-2023, limited players | Aggregated, not match-level | Downloadable | CC BY | **REJECT as insufficient** |
| TennisVisuals / tennis-match-data | Yes | Yes | Rich PBP, primarily legacy-era snapshots | PBP can reconstruct serve/return points | GitHub raw files | No dataset license; docs explicitly follow Sackmann PBP format and provenance cannot be separated cleanly | **REJECT** |
| sportsdatascience / setuppoints | Yes | Yes | ~2011-2017 legacy PBP | Rich PBP | GitHub | Explicit Jeff Sackmann source; CC BY-NC-SA 4.0 | **REJECT** |
| CourtVision GitHub | Yes | Yes | Pipeline-dependent | Serve/return analytics | Automated scraper | Explicit Tennis Abstract / Sackmann underlying data | **REJECT** |
| Racket Sports Multi-Dataset | Yes | Yes | 2018-2025 | Mostly match/result fields | OSF/GitHub | Downstream says CC BY 4.0, but ATP comes from Sackmann and WTA from tennis-data.co.uk | **REJECT — upstream rights control** |
| vitolytics tennis-data-pipeline | Yes | No | ATP key stats mainly 2021+ | Excellent ATP serve/return fields | Automated scraper | MIT applies to code; match data comes from ATP/Infosys systematic retrieval | **REJECT** |
| DataHub ATP World Tour repack | Yes | No | Through 2017 | Excellent ATP serve/return fields | Stable machine-readable files | Downstream CC BY claim, but source is ATP-site scraper lineage and stale/ATP-only | **REJECT** |

## GitHub hub deep audit

The GitHub ecosystem is large enough to solve the problem **technically**, but the apparent diversity collapses into a small number of upstream provenance roots.

### Sackmann / Tennis Abstract lineage

Multiple large-looking repos are not independent datasets:

- `TennisVisuals/tennis-match-data` contains ATP/WTA point-by-point files with server/returner outcomes and rich ace/double-fault coding. Its own PBP documentation says the format follows Jeff Sackmann's point-by-point repository; no dataset license is declared.
- `sportsdatascience/setuppoints` explicitly states its data comes from Jeff Sackmann and carries CC BY-NC-SA 4.0.
- `Snowstormme/tennisd` explicitly imports the Sackmann archive and carries the same non-commercial data licence.
- `TheCommishDeuce/courtvision` states that it scrapes Tennis Abstract and credits Jeff Sackmann as the underlying match-data source.
- `alexking100/tennis-stats` explicitly loads Sackmann ATP/WTA repositories under their non-commercial terms.

Renaming, transforming, validating, converting to Parquet/DuckDB, or attaching a different code license does not create independent data rights.

### ATP official-site scraper lineage

Several technically excellent repositories expose exactly the fields Tennis V1 needs, including first/second serve denominators, points won, aces, double faults, service games, return points and break points. However:

- `serve-and-volley/atp-world-tour-tennis-data`;
- `vitolytics/tennis-data-pipeline`;
- DataHub repackages of those files;

ultimately obtain the data through systematic ATP/Infosys retrieval. They are ATP-only and do not satisfy the already-adopted ATP-site terms rule. A permissive code or downstream dataset license is not treated as permission to reuse the underlying scraped data.

### Mixed-lineage downstream datasets

`Li02003121/racket-sports-dataset` claims CC BY 4.0 for its standardized data, but its own README identifies Jeff Sackmann as the ATP source and tennis-data.co.uk as the WTA source. Tennis V1 therefore treats the upstream restrictions as controlling and rejects the dataset.

### Engineering consequence

`SourcePolicy` now records `provenance_roots`. The production gate rejects any source marked production-eligible if its upstream lineage intersects:

- `jeff_sackmann_tennis_abstract`;
- `atp_official_systematic`;
- `tennis_data_co_uk`.

This prevents future workers from reintroducing a rejected data source through a mirror, transformed copy, permissive downstream label, or differently named GitHub repository.

## Selected zero-cost source stack

### Production-eligible results layer: Valuebetennis open data

Automated URL pattern:

`https://www.valuebetennis.com/datasets/valuebetennis-matchs-YYYY.csv`

Published fields used:
- stable match id;
- UTC match timestamp;
- tournament name/id;
- category;
- ATP/WTA tour;
- surface;
- draw round;
- player names and stable IDs;
- winner ID;
- final score;
- duration.

The upstream files also include Pinnacle opening/closing odds. The M2 adapter removes every market-derived column **in memory before any table can be returned or persisted**. No odds-bearing raw CSV is written to disk, committed, cached as a research asset, or exposed to player-state construction.

### Reference-only serve-stat layer: UCI 2013 majors

Programmatic ZIP:
`https://archive.ics.uci.edu/ml/machine-learning-databases/00300/Tennis-Major-Tournaments-Match-Statistics.zip`

Useful fields include:
- first-serve percentage;
- first-serve points won;
- second-serve percentage;
- second-serve points won;
- aces;
- double faults;
- break points created/won;
- total points and set scores.

It is CC BY 4.0 and suitable for schema/integration testing, but only covers the four 2013 majors. It lacks the historical breadth, freshness and exact per-match dates required for chronological production state estimation or Tournament Pace Index.

## Minimum viable Tennis V1 training dataset

Point-by-point is **not mandatory**.

For each match/player, the minimum credible serve-return backbone is:

### Required match context
- stable match/player IDs;
- event timestamp/date;
- tour (ATP/WTA);
- tournament;
- round;
- surface;
- score / completion status;
- best-of format when derivable;
- duration when available.

### Required service observations
At least:
- total service points;
- first serves in;
- first-serve points won;
- second-serve points won.

Strongly preferred:
- aces;
- double faults;
- service games;
- break points saved;
- break points faced.

These fields are enough to construct:
- service-point win rate;
- first-serve in rate;
- first-serve effectiveness;
- second-serve resilience;
- ace rate;
- double-fault rate;
- hold/break rates;
- opponent return-point performance.

Explicit return columns are not mandatory because return points can be reconstructed from the opponent's service-point totals when the service denominators are present.

Rankings are not mandatory. Milestone 2 implements chronological overall Elo and surface Elo with shrinkage, opponent quality, workload and surface-transition states from result history.

## Exact unresolved gap

No audited source simultaneously satisfies all of:

1. zero incremental cost;
2. unattended programmatic retrieval;
3. ATP **and** WTA;
4. multiple historical seasons plus current-season freshness;
5. match-level service-point denominators and serve outcomes;
6. terms compatible with this private betting research workflow.

The missing fields are specifically the current/deep match-level service observations:
- service points;
- first serves in;
- first-serve points won;
- second-serve points won;
- preferably service games, aces, double faults and break-point fields.

Without them, results/score/Elo can estimate general player strength but cannot credibly identify separate latent **serve strength** and **return strength** for the M1 point model.

## TPI decision

Valuebetennis supplies tournament/date/surface context but no serve statistics.

The UCI source supplies serve statistics but only for 2013 and without exact match timestamps.

Therefore production Tournament Pace Index cannot yet be built. The code returns an empty TPI table rather than using scores, odds, or later tournament observations as substitutes.

## Integrity rule

A future free source may be added only after:
- rights review;
- automated retrieval test;
- ATP/WTA coverage audit;
- market-field quarantine;
- chronological timestamp audit;
- schema/quality tests.

No rejected source may be silently reintroduced.
