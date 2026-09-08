# Nick NBA Assists + Rebounds V1

Status: **BUILDING — NOT PRODUCTION READY**

This directory is the isolated NBA implementation of the betting platform proven by `nbl_player_props_v1/`. It does not replace, import mutable state from, or change NBL production.

## Product

One daily-slate model with two mathematically independent heads:

- ASSISTS
- REBOUNDS

Default mode: `BOTH`.

Supported recommendation markets are player assists/rebounds overs and exact alternate-over ladders. There is no points head and no SGM logic. A positive edge is never forced.

## Non-negotiable integrity boundary

1. Resolve one exact NBA league-date slate and pin immutable runtime assets.
2. Research the entire eligible slate market-blind in server-enforced small batches.
3. Checkpoint each completed game before another batch can be retrieved.
4. Build requested heads from server-authoritative QBASE plus audited current-role translation.
5. Atomically freeze the **whole requested slate** before any sportsbook market operation is permitted.
6. Bind every evaluated market to the exact slate freeze receipt and exact frozen player/head hash.
7. Permit price refreshes and manual sportsbook screenshots only post-freeze, with no P_model mutation.
8. Treat material late news as invalidation, never silent mutation.
9. Bet Tracker remains downstream-only; a wager is logged only after explicit user confirmation of selection, bookmaker, accepted odds and stake.

## Planned services

- `nba-player-props-research-v1` — fixture/slate resolution, research queue/checkpoints, server QBASE, global freeze, invalidation state.
- `nba-player-props-market-v1` — post-freeze Odds API/screenshot ingestion, exact line binding, best-price merge, EV and slate ranking.
- existing Nick Bet Tracker — unchanged shared tracker architecture, with `sport=nba`, `league=nba`, `model_name=Nick NBA Assists + Rebounds`.

## Source architecture decision

Production historical authority will use a deterministic source build with immutable receipts:

- **Primary licensed backbone:** SportsDataverse/hoopR NBA schedule, player box, team box and play-by-play release assets.
- **Official enrichment:** NBA CDN / NBA Stats endpoints for fields that pass automated availability, schema and completeness gates (for example player tracking fields such as touches, passes, secondary assists and rebound chances).
- **Cross-source identity:** deterministic ESPN ↔ NBA game/team/player crosswalks; NBA game/player IDs are retained whenever available.
- **QA only:** other community NBA dumps may be compared for completeness, but are not production authority unless licensing and maintenance gates are explicitly passed.

Specialist metrics are feature-gated as `AVAILABLE`, `PARTIAL`, `UNAVAILABLE`, `BLOCKED`, or `NOT_RELIABLE`. Missing metrics are never zero-filled as evidence.

## Build order

1. Architecture + source audit and source receipt contract.
2. Deterministic historical build + identity crosswalk + source acceptance.
3. Assists/Rebounds feature generation and temporal walk-forward model challenge.
4. QBASE artifacts + exact distributions + promotion gates.
5. Daily-slate Research/Freeze Durable Object and research contract.
6. Post-freeze Market Worker + Odds API cost controls + screenshot merge.
7. OpenAPI, Master Knowledge, GPT Instructions, launch/install documents.
8. CI, live Cloudflare acceptance, Custom GPT production acceptance.

No component is called production-ready until all acceptance gates in `ARCHITECTURE.md` and the production acceptance suite pass.