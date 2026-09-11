# NBA V1 — POST-DEPLOY PREFLIGHT GATE

This is the first live gate after Cloudflare deploy/configuration. It is deliberately read-only except for a safe unknown-run negative control that must fail before any Odds API call is possible.

It does **not** create a Research run, freeze a P_model, create a Bet Tracker model run, record a wager, or consume an Odds API credit.

## Command

Run from the repository root with Node 22+:

```bash
NBA_RESEARCH_URL="https://nba-player-props-research-v1.nickarnott01.workers.dev" \
NBA_MARKET_URL="https://nba-player-props-market-v1.nickarnott01.workers.dev" \
NBA_RESEARCH_ACTION_TOKEN="<research ACTION_TOKEN>" \
NBA_MARKET_ACTION_TOKEN="<market ACTION_TOKEN>" \
NBA_TRACKER_ACTION_KEY="<existing shared tracker key>" \
EXPECTED_SOURCE_COMMIT="<exact deployed 40-char Git SHA>" \
EXPECTED_TRACKER_SCHEMA="2.1.0" \
NBA_ACCEPTANCE_ET_DATE="YYYY-MM-DD" \
PREFLIGHT_RECEIPT_PATH="nba_preflight_receipt.json" \
node nba_player_props_v1/scripts/post_deploy_preflight.mjs
```

`NBA_ACCEPTANCE_ET_DATE` is optional until a future NBA slate is available. All other variables above are production requirements.

## Required PASS evidence

The generated receipt must have `passed=true` and prove:

- Research Worker requires authentication.
- Research health reports the exact deployed Git SHA.
- `source_commit_ready=true`.
- Research is `market_data=false`.
- `SLATE_RUNS / NbaSlateRun` is bound.
- Market Worker requires authentication.
- Market is `post_freeze_only=true`.
- `MARKET_RUNS / NbaMarketRun` is bound.
- `RESEARCH_SERVICE` binding is present.
- `ODDS_API_KEY` is configured without revealing it.
- default Odds API region is `au`.
- the only market keys are `player_assists`, `player_assists_alternate`, `player_rebounds`, `player_rebounds_alternate`.
- the shared Bet Tracker is healthy on schema `2.1.0` (or a later explicitly accepted schema passed through `EXPECTED_TRACKER_SCHEMA`).
- if an ET date is supplied, at least one eligible future fixture resolves.
- an unknown/unfrozen Market refresh is rejected at `RESEARCH_MARKET_ACCESS_GRANT` before the Odds API client can execute.
- no wager and no tracker model run were written.

## Fail-closed rules

Do not proceed to a full live slate acceptance if any check fails.

In particular, do not waive:

- source commit mismatch;
- missing auth;
- missing Durable Object/service binding;
- missing Odds API key;
- tracker schema mismatch;
- market region/allowlist mismatch;
- failure of the pre-freeze negative control.

Fix deployment/configuration, redeploy through the existing Cloudflare-native Git owner, and rerun this preflight against the exact new deployment commit.

## Relationship to full production acceptance

A PASS here clears only deployment/auth/binding preflight. It does **not** make V1 production-ready.

The remaining acceptance sequence is still:

1. one exact future ET slate;
2. full 1–2 game Research checkpoint loop;
3. atomic whole-slate freeze and immutable retry proof;
4. real post-freeze Odds API refresh and no-double-spend retry proof;
5. Layer 4 global ranking;
6. one shared Bet Tracker model-run handoff;
7. late-news invalidation immutability control on a safe acceptance scope;
8. post-freeze Bet365/manual screenshot refresh proving no P_model/freeze mutation.

PR #20 remains draft until every full acceptance gate passes.
