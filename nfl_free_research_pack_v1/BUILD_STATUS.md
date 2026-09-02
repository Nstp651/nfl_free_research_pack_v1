# Build status — 2026-09-02

Implementation candidate 1.1.1. NOT deployed or season-locked.

Repository: Nstp651/nfl_free_research_pack_v1
Base commit: deb4846bd4f87be967fd3c809e96069f2848bec1
Local branch: codex/research-pack-build

Completed locally:
- Retrieved the actual repository and fixed the nested working directory.
- Added regression tests and output validation to the workflow.
- Fixed missing-column crashes, nullable FTN flags, future/week-zero data, postseason filtering, duplicate charting joins, unknown player IDs and team-qualified depth joins.
- Corrected snap aggregation to a clearly labelled mean of weekly percentages; retained missing data as unknown.
- Added verified FTN read labels with observed samples and per-source-team primary-read shares.
- Limited current-season aggregation to the requested active week.
- Added source availability, checks before publication, fixture/content revisions and refresh timestamps.
- Added read-only API pagination, fixture/revision validation, upstream health checks and stale-source reporting.
- Prepared complete OpenAPI and model integration instructions.
- 14 Python regression tests and 9 Worker tests passed. Test data are synthetic and never published as real research.

Still pending:
- Authenticated GitHub write access. The plugin reports installed, but this session exposes no GitHub repository tools. The CLI can read the public repo but its dry-run push failed for missing authentication.
- Real dependency installation/source pull. This session's dependency download ended with network approval cancelled; nflreadpy/polars/pyarrow remain unavailable locally.
- Push/review the branch, then run Actions on main and inspect the actual JSON and source receipts. Do not use Re-run jobs for the old commit.
- Validate two real matchup packs against their source player/team totals and FTN/NGS identity joins.
- Deploy the dedicated Cloudflare Worker; never overwrite nick-betting-api or beatthebooks-v2. No Cloudflare connector is available in this session.
- Set the deployed workers.dev URL in openapi.yaml; test the API and all pages from the GPT Action editor.
- Install the private full NFL V4.1 candidate in the existing NFL GPT. The complete model was kept outside this public repository.
- Run two pre-market GPT dry runs; verify market freeze remains intact.
- Pin the exact dependencies/actions from the successful build and tag 2026-season-lock only after acceptance.

Known limitations:
- No true in-season routes, live injuries or full coverage matrix.
- Historical backtests cannot be validated from latest roster/depth snapshots. Statistical week-cutoff regression tests are not a full point-in-time backtest.
- No claim that more data guarantees a betting edge.
- Latest-source retrieval does not guarantee latest-game charting publication. Inspect per-source coverage and continue live research.
- Current-season core outage stops publication; previous outputs remain in GitHub. Optional sources disclose missing coverage.
- GitHub commit publication is atomic as a set; files are written individually during the local build. The workflow publishes only after all validation succeeds.
- Dependency ranges and action major tags are still candidates, not a completed season lock.
