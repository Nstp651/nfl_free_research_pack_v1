# NFL Free Research Pack V1.1 — Audited Production Candidate

A free, automated, **pre-market** structured data layer for an NFL player-receptions model.

## What this solves

It creates active-week matchup research packs without paying for Fantasy Points Data, FTN API access, PFF, or another commercial feed.

It does **not** try to replace live research.

### Free sources

- nflverse play-by-play
- nflverse player/team stats
- current rosters
- current depth charts
- NFL Next Gen Stats via nflverse
- Pro Football Reference snap counts via nflverse
- PFR advanced receiving via nflverse
- free FTN charting subset via nflverse

FTN charting is attributed to **FTN Data via nflverse** and is released in nflverse under CC-BY-SA 4.0.

## What it deliberately does NOT claim

- no sportsbook data
- no market consensus
- no betting projections
- no current nflverse injury feed
- no true in-season routes / route participation
- no automatic preseason route truth
- no unverified interpretation of FTN `read_thrown` category values

This is intentional model discipline.

## Week 1 usefulness

Yes. Before 2026 Week 1 the pack is useful as a **quantitative prior + current roster/depth translation layer**:

- 2025 targets / receptions / target share / aDOT / catch rate
- 2025 FTN catchability and contextual charting
- 2025 NFL Next Gen receiving metrics
- 2025 snap-share proxy
- 2025 team pass environment
- 2024 stabilization history
- current 2026 roster/team/depth context
- automatic flag when a player changed teams
- rookie flag

But before Week 1 it must NOT pretend those are 2026 usage rates. Current role still comes from camp, preseason, coaching, injuries, QB and beat/official research.

## Architecture

`nflverse -> GitHub Action -> compact JSON packs -> Cloudflare Worker -> GPT Action -> Layer 1`

The sportsbook action remains completely separate and post-freeze.

## Accounts / cost

Data-provider signup: **none**.

Recommended infrastructure:
- GitHub account/repository: free
- Cloudflare Worker: free tier is more than enough for this use

No FTN account is required for the nflverse FTN subset.

## Setup

### 1. Create a GitHub repo

Create a repo, for example:

`nfl-free-research-pack`

Upload this bundle to the repository root.

A public repo is simplest because the Worker can read generated JSON from `raw.githubusercontent.com` without a GitHub token.

### 2. Run the first build

Go to:

`GitHub -> Actions -> Refresh NFL Free Research Packs -> Run workflow`

Use season `2026`.

The action automatically resolves the earliest unplayed regular-season week and generates:

- `data/manifest.json`
- `data/games/2026/<active-week-game_id>.json`

and commit the files back to the repo.

### 3. Create / update the Cloudflare Worker

Copy `worker/index.js` into a Worker.

Set environment variable:

`DATA_BASE_URL=https://raw.githubusercontent.com/YOUR_GITHUB_USERNAME/YOUR_REPO/main/data`

Deploy it.

Test:

- `/health`
- `/v1/packs?season=2026&week=1`
- `/v1/packs/2026_01_NE_SEA`

### 4. Add the GPT Action

Edit `openapi.yaml` and replace:

`https://YOUR-WORKER.YOUR-SUBDOMAIN.workers.dev`

with the real Worker base URL.

Add the schema to the NFL receptions GPT.

### 5. Update model instructions

Apply `MODEL_INTEGRATION_PATCH.md`.

The data action must run in Layer 1 before the P_model freeze.

## Automatic refresh

The included workflow runs four times per day, shortly after the nflverse FTN polling windows. It rebuilds only the active week and refuses to replace good data if a required core source is missing.

It also supports `workflow_dispatch`, so you can manually refresh immediately.

## Look-ahead protection

Every game pack is generated using current-season records with:

`source week < target fixture week`

This means a Week 5 pack can use Weeks 1-4 but not Week 5 results.

Historical seasons remain available as priors.

## Important route warning

The free nflverse participation feed is not a current in-season route feed.

The pack therefore exposes:

`offense_snap_pct -> route opportunity PROXY ONLY`

It never converts that field into a fake route-participation number.

## Output design

Each game pack includes:

- fixture metadata
- data availability state
- team pass environment
- current roster/depth context
- current-season-to-date metrics when available
- historical receiving metrics
- FTN charting context
- Next Gen receiving metrics
- snap proxy
- PFR advanced receiving
- transfer/rookie warnings
- source receipt and limitations

The GPT still performs the model's full live research layer afterward.

## Next improvement after first successful run

Inspect:

`data/manifest.json -> source_status -> FTN_read_values_observed_by_prior_season`

Once we independently verify the semantics of the observed FTN `read_thrown` values, we can add first-read/designed-read labels safely rather than guessing.


## Pre-season production lock

Before declaring the system season-locked, complete the live deployment gates in `AUDIT_REPORT.md`. After the first successful GitHub run, freeze the exact Python environment and tag the repository `2026-season-lock`. Model instructions should then remain unchanged during the regular season.
