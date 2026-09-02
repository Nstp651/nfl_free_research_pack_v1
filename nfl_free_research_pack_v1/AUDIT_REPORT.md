# Research Pack 1.1.1 audit

Status: real data build, source reconciliation and live-GitHub handler acceptance PASS. Cloudflare deployment and GPT acceptance pending; see BUILD_STATUS.md.

The original package had not passed a live source pull. The saved patch has now been published and tested successfully against real data; the deployment boundary remains explicit.

Verified defects corrected:
1. Workflow commands used the repository root although uploaded files live in nfl_free_research_pack_v1.
2. Missing optional numeric columns could trigger scalar `.fillna` exceptions or become false zeros.
3. FTN float flags and missing observations could be classified incorrectly. Rates now declare observed denominators.
4. FTN joins could multiply targets when duplicate source play IDs existed; joins now require one-to-one keys.
5. Current-season rows without a usable week, week-zero aggregates, and all-postseason tables could escape filtering.
6. Roster rows with missing GSIS IDs could collapse; old-team depth could join solely on player ID.
7. Weekly snap percentages were weighted by the player's own snaps, overstating high-usage games. Now a labelled mean of weekly observed percentages.
8. All schedule weeks were aggregated even when publishing only the active week.
9. Original health endpoint reported success without checking data; original API omitted source health and had no response-size guard.
10. Original manifest/pack fetch could mix revisions; pagination now requires the same content revision and validates the fixture.
11. Unchanged content could leave refresh timestamps stale forever; manifest now records the latest successful source check separately.

The FTN dictionary now explicitly documents read codes. Verified against the official dictionary on 2026-09-02; raw codes remain available. Labels/counts and source-team shares use observed charted targeted passes; missing values remain unknown.

Definitions and constraints:
- https://nflreadr.nflverse.com/articles/dictionary_ftn_charting.html
- https://nflreadr.nflverse.com/articles/dictionary_nextgen_stats.html
- https://nflreadr.nflverse.com/articles/dictionary_snap_counts.html
- https://nflreadr.nflverse.com/articles/nflverse_data_schedule.html
- https://nflreadpy.nflverse.com/api/load_functions/
- https://developers.openai.com/api/docs/actions/production
- https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/set-default-values-for-jobs

Validation: 14 Python and 9 JavaScript regression tests pass. The real GitHub build generated all 16 Week 1 packs. Source reconciliation passes for 67 players across two fixtures; the Worker handler retrieved every player across eight pages from the exact published GitHub revision. See data/source_acceptance.json and data/handler_acceptance.json. This handler test is not a Cloudflare deployment test. No full historical backtest or live GPT run has occurred. Season lock remains pending.
