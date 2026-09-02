# NFL Receptions Model — Free Research Pack Integration Patch

## Purpose

Add the free research pack to **Layer 1 only**, before the P_model freeze and before any sportsbook action.

The pack is football research data, not market data.

## Required action order

After fixture validation and before the broad/deep Layer-1 research sweep:

1. Call `listNflResearchPacks(season, week)`.
2. Resolve the exact fixture using BOTH teams and the official week.
3. Call `getNflResearchPack(game_id)`.
4. Verify the returned `fixture`, `game_id`, season, week, home team and away team.
5. Record the pack in **SOURCE / DATA RECEIPTS**.
6. Use it as structured evidence while continuing the complete live research layer.
7. Never call sportsbook/odds actions until Layer 2 is complete and `P_MODEL_STATUS: FROZEN`.

If the pack is unavailable, continue with the existing live research stack and state:
`FREE_NFL_RESEARCH_PACK_UNAVAILABLE — LIVE RESEARCH FALLBACK`

Do not fail the model solely because the free pack is unavailable.

---

## Evidence treatment

### Current roster/depth fields
Use as supporting current structural evidence, but official current reporting may override them.

Depth chart status DOES NOT prove route participation.

### Current-season player/team data
Use only when `data_state.current_season_data_through_week < target week`.

Never permit future-week/look-ahead data.

### Historical player/team data
Use as priors and comparable evidence only.

For Week 1 / early season:
- prior-season production is a baseline, not the current role;
- team-change flags require role translation;
- rookies require camp/preseason/current-role research;
- coaching/QB/personnel changes must be reconciled before modelling.

### Snap data
`offense_snap_pct` is **PROXY ONLY**.

Never print or treat snap share as:
- routes,
- route participation,
- route share,
- TPRR denominator.

This is particularly important for TE/RB because blocking can inflate snaps.

### FTN charting
Valid uses:
- catchable-ball rate,
- contested-target rate,
- drop context,
- screen-target rate,
- play-action target context,
- RPO target context,
- motion target context,
- raw `read_thrown` category distribution.

Until an independent category mapping is verified, raw `read_thrown` values MUST NOT be relabelled as first read / second read / designed read.

### NGS
Use:
- average separation,
- average cushion,
- average target depth,
- intended-air-yards share,
- catch context.

Missing NGS data does not equal zero because NFL NGS has qualification thresholds.

---

## Mandatory limitations

The free pack does NOT replace:
- live injury/practice research,
- official inactive status,
- current QB verification,
- camp/preseason role evidence,
- current routes/route participation,
- third-down/two-minute deployment research,
- current personnel-package research,
- contradiction search.

No nflverse injury feed may be treated as current truth.

---

## Week 1 handling

When `data_state.mode = PRE_WEEK_1_OR_NO_CURRENT_REGULAR_SEASON_DATA`:

Use:
- 2025 full-season player receiving baseline,
- 2025 late-season/recent context from the existing live Layer-1 audit,
- 2025 FTN charting baseline,
- 2025 NGS baseline,
- 2025 snap-share proxy,
- 2024 stabilization evidence where useful,
- current 2026 roster/depth/team assignment.

Do NOT pretend the pack contains 2026 regular-season usage.

The model must explicitly translate:
`PRIOR NFL OPPORTUNITY -> CURRENT 2026 ROLE`

using current coaching, QB, teammates, injuries, depth, camp/preseason and role reporting.

---

## Layer-1 receipt row

Add a receipt similar to:

`NFL FREE RESEARCH PACK | STRUCTURED ANALYTICS | {game_id} | current roster/depth + historical/current available receiving/FTN/NGS/snap/team evidence | Tier 1 supporting + Tier 2 quantitative | route truth unavailable; injuries live-research only`

---

## Completion gate additions

Add:

- [ ] free NFL research pack checked
- [ ] no look-ahead current-season data used
- [ ] historical-to-current team/role translation completed
- [ ] snap proxy not mislabelled as routes
- [ ] live injury/practice/preseason research remained primary for current role

---

## 2026 SEASON LOCK

Once the pre-season production acceptance test is complete:

- freeze this integration for the 2026 regular season;
- do not alter feature treatment, P_model construction, thresholds, confidence logic, research gates or market-freeze discipline based on results during the season;
- automatic data refreshes are inputs, not model changes;
- temporary pack failure triggers the existing live-research fallback and does not justify changing P_model methodology;
- a technical adapter repair caused by an upstream schema/availability change may restore the same approved fields but must not introduce new model features or changed modelling logic during the regular season.
