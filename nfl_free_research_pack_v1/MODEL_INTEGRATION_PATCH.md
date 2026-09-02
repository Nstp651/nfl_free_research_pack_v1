# NFL V4 — Free Research Pack integration 1.1.1

Status: implementation candidate; live acceptance and season lock are pending.

This integration adds structured evidence to Layer 1. Preserve the existing research depth, probability engine, confidence logic, candidate rules, ladder rankings, market order and staking exclusions.

After independent fixture validation, before player research:

1. Call `listNflResearchPacks(season, week)` and resolve exactly one fixture using both teams and home/away. Verify kickoff separately in Australia/Sydney.
2. Call `getNflResearchPack(game_id, offset=0, revision=pack_revision)` using the manifest revision.
3. Follow `pagination.next_offset` until null, sending the same revision on each request. Check the fixture and revision on every page; reconcile the unique player count to `total_players`. Repeated team context across pages is one observation, not additional evidence.
4. If the revision changes (409), reload the manifest and restart the full retrieval once. For transient 429/5xx/timeouts, retry once. If still incomplete, mark unavailable/partial and continue the original live-research workflow. Never silently treat an incomplete player page as the full candidate universe.
5. Record game ID, revision, generated time, last checked time, source availability, freshness and statistical cutoff in SOURCE / DATA RECEIPTS.
6. Complete all existing deep current research, contradiction checks and role translation before closing Layer 1. No research-pack call is allowed to alter a frozen model during a post-freeze market refresh.

Evidence rules:

- `current_season_data_through_week` must be null or below the target week. Null means no current-season usage, not week zero. Week 1 uses historical priors plus independently verified current roles.
- Pack refresh time is not the publication time of each upstream dataset. Inspect availability and through-week per source. STALE (>36 hours since source check) requires current facts to be reverified through live research; historical priors may remain usable with their dates stated. A current feed gap never becomes zero performance.
- Current roster and depth are latest available supporting context. Regenerated old-week packs are not point-in-time historical backtests. Do not use them to claim out-of-sample model performance.
- Historical player/team data are priors. Translate team, coach, QB, target competition, role, injuries and deployment changes. A null team-change flag means unknown. Retain rookie and unlisted-player research even without an NFL prior.
- Weekly statistical rows are not proof that every zero-target appearance is represented. Report denominators as observed source games. Use live game logs to reconcile a player's per-game baseline when material.
- `target_share` is a mean of observed weekly shares, not an aggregate season target share. Do not substitute it for targets divided by team targets without recomputing aligned denominators.
- `offense_snap_pct` is the mean of observed weekly snap percentages, never routes or route participation and never a TPRR denominator. Blocking makes this particularly weak for TE/RB.
- FTN rate denominators include only observed flags. Inspect observed sample counts. Primary-read shares use charted targeted passes for the corresponding source team, not all dropbacks. The verified read mapping is 0=primary, 1=second, 2=third-or-later, CHK=checkdown, DES=designed, SD=scramble drill. Missing/unknown values remain unknown. The primary code is only supported from 2023; 2022 missing reads cannot be inferred.
- FTN read definitions: https://nflreadr.nflverse.com/articles/dictionary_ftn_charting.html (verified 2026-09-02).
- NGS absence is not zero. Season-aggregate rows are excluded from current-season week-specific evidence; aggregated weekly NGS reflects qualifying observed weeks.
- No current injury feed, preseason routes, actual routes/route participation or full coverage matrix is promised. Official/live research remains necessary.
- The API provides research inputs, no P_model or markets. Never mechanically add a percentage to P_model for FTN/NGS fields; establish the football pathway using the existing model methodology.

At the Layer 1 completion gate confirm: pack loaded completely at one revision OR fallback declared; statistical cutoff checked; historical role translation completed; missing fields kept unknown; deep live research completed.

Failure label: `FREE_NFL_RESEARCH_PACK_UNAVAILABLE — LIVE RESEARCH FALLBACK`.
Partial label: `FREE_NFL_RESEARCH_PACK_PARTIAL — LIMITATIONS DECLARED`.
Success label: `FREE_RESEARCH_PACK_STATUS: LOADED`.

Season lock: only after a successful real-source build, two manually reconciled matchup packs, live API/GPT tests and two pre-market model dry runs. Then pin the tested dependencies and workflow actions, archive exact model/API/build versions, and tag `2026-season-lock`. Automatic observations may refresh; methodology must remain fixed. Infrastructure repairs may restore approved behavior without adding features. Do not declare lock complete from synthetic tests.
