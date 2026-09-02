# Dedicated research Worker — deployed and live-tested

The root `wrangler.toml` is ready for Cloudflare's native Git integration.
This creates only `nfl-free-research-pack-v1`. It has no database, paid data provider,
AI API, secret requirement, custom domain or scheduled Worker.

## Verified deployment

Live URL: https://nfl-free-research-pack-v1.nickarnott01.workers.dev

Cloudflare deployment and live HTTP acceptance succeeded on 2026-09-02.
The actual service name has the `-v1` suffix; repository configurations now match it.
Wrangler is pinned to 4.128.0 in the root package.json.

Live acceptance: https://github.com/Nstp651/nfl_free_research_pack_v1/actions/runs/33616689903

## Reproduction settings (already configured)

1. Open Cloudflare **Workers & Pages → Create application → Import a repository**.
2. Connect the GitHub account `Nstp651` and select the existing repository
   `nfl_free_research_pack_v1`.
3. Use the Workers **Free** plan/account. Do not upgrade or enable paid services.
4. Set these values, then select **Save and Deploy**:

| Setting | Value |
| --- | --- |
| Worker name | `nfl-free-research-pack-v1` |
| Production branch | `main` |
| Root directory | `/` |
| Build command | Leave blank |
| Deploy command | `npx --yes wrangler@4.128.0 deploy` |

The dedicated name must match the configuration file. Do not choose an existing
betting gateway or tracker Worker. Use the existing repository import flow;
template deploy buttons would create an unnecessary copy of the repository.

For subsequent automatic deployments, include `wrangler.toml` and
`nfl_free_research_pack_v1/worker/index.js` in build watch paths. The four daily
data updates need no Worker redeployment: the Worker reads GitHub directly.

## Repeat live acceptance when needed

Copy the exact `https://nfl-free-research-pack-v1.nickarnott01.workers.dev` URL.
Run the repository's **Test deployed NFL research API** Actions workflow with that
URL, season `2026`, and the week in the current data manifest.

This workflow checks live health, fixture identity, revisions, all player pages
for two real fixtures, missing values, cutoff, freshness, response sizes, and
invalid/write requests. Only after success does it commit
`data/live_acceptance.json` and set the real server URL in `openapi.yaml`.
It does not edit a GPT or tag the season lock.

## GPT completion

The live API has passed. Import `nfl_free_research_pack_v1/openapi.yaml` as a new
read-only research Action using no authentication. Keep the existing Odds API
Action. Install the full private candidate supplied separately, then test two
complete pre-market runs in the GPT. Research pages must all arrive before the
freeze; odds remain post-freeze. Tag `2026-season-lock` only after those tests.

## Costs and scope

The public repository uses standard GitHub-hosted runners. On Workers Free, the
request quota is capped; exceeding it does not opt into a paid plan. No paid
subscription has been enabled by this build. Billing settings were not changed.
For current Free-plan limits, use the official pricing reference below.

References: [Cloudflare Git import](https://developers.cloudflare.com/workers/ci-cd/builds/),
[build settings](https://developers.cloudflare.com/workers/ci-cd/builds/configuration/),
[Workers pricing](https://developers.cloudflare.com/workers/platform/pricing/),
[GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions).
