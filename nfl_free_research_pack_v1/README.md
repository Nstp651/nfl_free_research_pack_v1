# NFL Free Research Pack 1.1.1 — data build operational

Automated, pre-market NFL receptions research from nflverse. The real GitHub data build and source/handler acceptance have passed. Cloudflare deployment and live HTTP acceptance also pass. GPT integration and season lock are pending. Read BUILD_STATUS.md for evidence and ../DEPLOYMENT.md for the prepared deployment flow.

## Repository layout

The workflow is at repository-root `.github/workflows/refresh.yml`.
All application files and generated data are inside `nfl_free_research_pack_v1/`.
The workflow sets that working directory. Do not move only requirements.txt.

## Build

From the application folder:

```bash
pip install -r requirements.txt
python -m unittest discover -s tests -v
node --test worker/index.test.mjs
python build_pack.py --season 2026 --output data --history-seasons 2 --verify-sources
python validate_pack.py data
```

GitHub runs four scheduled refreshes daily and supports manual dispatch. The schedule is unchanged. Only a successful build and validation on main commits data. A change to workflow/application code on main starts a new run; old job reruns use the old commit.

`--week` is an optional statistical cutoff override. It is not a full historical backtest: roster/depth data are latest available. Missing prior/current core data stops publication. Optional source absence is disclosed.

## Dedicated research API

Use a NEW Cloudflare Worker called `nfl-free-research-pack-v1`. Import this existing repository using the root Wrangler configuration and the settings in ../DEPLOYMENT.md. Do not overwrite any existing betting gateway/tracker Worker. The source defaults to this repository's nested data folder; DATA_BASE_URL can override it.

- GET /health checks real upstream availability and age.
- GET /v1/packs?season=2026&week=1 resolves fixtures.
- GET /v1/packs/{game_id}?offset=0&limit=10&revision={pack_revision} returns players and context.

Fetch every page until pagination.next_offset is null. Hold revision constant. Changed revisions return 409; mismatched publication snapshots return 503. Responses are limited below 90,000 characters. Missing fixtures and invalid upstream data return explicit errors. No odds/model endpoint is implemented.

The verified deployed URL is already set in openapi.yaml. Select no authentication for these public, read-only research endpoints. Apply MODEL_INTEGRATION_PATCH.md to the private model only; the complete private model is not included in this public repository.

## Interpretation

Historical statistics are priors; current role and injury truth needs live research. Snap percentages are not routes or TPRR denominators. FTN flags use observed samples and verified read codes. NGS absence is not zero. A recent refresh timestamp is not proof that each provider has published every completed game. Weekly target-share averages are labelled and must not be mistaken for an aggregate season share.

## License and attribution

Includes derivatives of the FTN charting subset supplied through nflverse under CC-BY-SA 4.0. Attribute FTN Data and nflverse and preserve the applicable share-alike license for distributed derivatives. See https://creativecommons.org/licenses/by-sa/4.0/ and the source definitions in AUDIT_REPORT.md. Other source terms continue to apply.

## Acceptance and season lock

Real data generation, two-pack source reconciliation and live-GitHub Worker handler tests pass. Exact Python packages and action revisions are pinned. The separate data/live_acceptance.json report verifies the deployed Cloudflare HTTP API. Complete the GPT Action tests and two full pre-market model dry runs before tagging `2026-season-lock`. Automatic observations can refresh; infrastructure repairs may restore existing behavior.
