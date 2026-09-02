# Build status — 2026-09-02

GitHub data pipeline: OPERATIONAL. Source reconciliation: PASS.
Worker handler with real GitHub data: PASS.
Cloudflare deployment: BLOCKED ON ACCOUNT CONNECTION.
GPT integration / full pre-market dry runs / season lock: PENDING.
Added paid services: NONE.

## Verified evidence

- Published the saved patch to main as `d9357a7f7cadf4c46ddda75728d7d4291777f74d`.
- First real build: https://github.com/Nstp651/nfl_free_research_pack_v1/actions/runs/33614515053 — success; generated and validated all 16 Week 1 packs.
- Pinned dependency/action versions and added source/handler acceptance in `b55a51e5b912858d2234ba3add3120a9ad715eda`.
- Acceptance build: https://github.com/Nstp651/nfl_free_research_pack_v1/actions/runs/33615250590 — success.
- Data commit tested by the handler: `db5370478db358d19c11b94e5444f0b6ad1ef8ec`.
- 14 Python regression tests and 9 Worker tests pass on GitHub.
- Real sources: 2026 schedule (272 fixtures), roster (2,800 rows), depth (490,107 source rows), and 2024/2025 receiving, team, PBP, FTN, snaps, PFR receiving and NGS data.
- Week 1 has no current-season regular-season usage. Missing 2026 data is not synthesized or substituted with history.
- Two real matchup packs reconcile to source totals, roster/depth identities, rookie/transfer flags, nullable FTN observations and NGS identities.

| Acceptance fixture | Players | Pages | Prior-year NGS identities | Largest response bytes |
| --- | ---: | ---: | ---: | ---: |
| 2026_01_NE_SEA | 35 | 4 | 9 | 46,280 |
| 2026_01_SF_LA | 32 | 4 | 9 | 52,888 |

The checks include 285 player-stat assertions and 1,602 FTN field/denominator assertions, plus roster/depth, team, identity, cutoff and pagination checks. FTN joined 17,013 eligible regular-season targeted passes in 2024 and 16,609 in 2025, with no unmatched eligible targeted passes. Raw FTN source files also contain playoff rows; those rows do not enter these joins.

Reports: `data/source_acceptance.json` and `data/handler_acceptance.json`.
The latter explicitly says `LOCAL_HANDLER_WITH_LIVE_GITHUB_SOURCE` and `deployment_verified: false`. It is NOT evidence of a deployed Cloudflare endpoint.

## Ready for the remaining deployment

- Root `wrangler.toml` names only `nfl-free-research-pack` and points at the existing nested Worker source.
- `DEPLOYMENT.md` supplies the native Cloudflare import settings without manual code changes.
- `Validate dedicated Worker deployment package` runs a no-authentication Wrangler dry run.
- `Test deployed NFL research API` accepts the dedicated workers.dev URL and, only after live success, saves `data/live_acceptance.json` and sets the real Action server URL.
- Exact Python dependencies and checkout/setup-python action revisions are pinned from a successful live-source run. Python is 3.12.14; standard runner is ubuntu-24.04. Wrangler 4.128.0 is pinned for packaging/deployment. Hosted OS images can still receive platform maintenance.

## Exact blockers and remaining gates

This session has authenticated GitHub access. It has no Cloudflare connector, Cloudflare environment credential or Wrangler login. No authenticated GPT editor capability is exposed. No Cloudflare resources or existing betting/tracker Workers were changed. Local dependency installation encountered a cancelled network approval; real source work and tests ran successfully in the authorized GitHub workflow.

Connect this existing repository through Cloudflare on Workers Free, deploy the dedicated Worker, and provide its real URL. Run the prepared HTTP acceptance workflow, then import the configured research Action into the existing NFL GPT while preserving its Odds API Action. Install the separately supplied private candidate. Complete two full pre-market GPT runs before tagging `2026-season-lock`.

No tag has been created. The full private probability model is not in this public repository. Latest roster/depth snapshots do not establish a historical point-in-time backtest. Current role/injury research and market freeze discipline remain mandatory.

## $0 constraint

Only standard GitHub-hosted runners on this public repository have been used. No paid API, subscription, hosting plan, database or AI calls were added. Cloudflare deployment must use Workers Free without a paid upgrade. The original four daily research refreshes remain in place.
