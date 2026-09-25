# Tennis V1 Source Audit

## Current governing audit

The original Milestone 1 paid-vendor survey is superseded for the current build phase by:

- `M2_SOURCE_AUDIT.md` — fresh zero-cost / zero-upload audit;
- `M2_STATUS.md` — implementation and acceptance result.

The current requirement is **zero incremental data cost and zero manual uploads**. Paid vendors such as Sportradar and API-Tennis are therefore not part of the Milestone 2 solution even though they remain technically capable sources.

## Current production-source decision

Accepted:
- **Valuebetennis open data (CC BY 4.0)** for ATP/WTA results metadata from 2021-current. Its upstream betting-price columns are destroyed in memory at ingestion and never enter the quantitative pack.
- **UCI Tennis Major Tournament Match Statistics (CC BY 4.0)** only as a reference/schema test source for serve-stat fields. It covers only the 2013 majors and is not sufficient for player-state training.

Rejected or excluded:
- Jeff Sackmann / Tennis Abstract and mirrors — CC BY-NC-SA / non-commercial;
- TML — non-commercial and ATP-only for the useful detailed layer;
- ATP/WTA website scraping — terms/reliability conflict with this production workflow;
- TennisData.App — current terms prohibit scripts/systematic extraction and grant personal/non-commercial use;
- Live Tennis API academic point dataset — non-commercial academic restriction;
- paid Live Tennis API history/stat tiers — violates zero-cost requirement;
- Tennis-Data.co.uk and derivatives with unresolved upstream rights;
- legacy point-by-point mirrors with Sackmann lineage or no adequate license.

## Milestone 2 result

No audited free source currently supplies sufficiently deep and current **ATP + WTA match-level service-point statistics** with unattended access and suitable usage rights.

Accordingly:

`ZERO_UPLOAD_TEST = FAIL_SERVE_STATS_GAP`

This is a fail-closed integrity result, not a recommendation to purchase data or request manual files.
