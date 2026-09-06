# NBL Player Props V1 — One Match Engine, Dual Stat Heads

## Decision
Build ONE production NBL match engine with two independent quantitative heads:

1. ASSISTS
2. REBOUNDS

The engine is run match-by-match. A single Layer 0/1 research pass covers the fixture once, then Layer 2 branches into separate stat-specific P_models. The heads never share a probability distribution or force one stat to inherit the other's assumptions.

Run modes:
- `BOTH` (default): research once, freeze assists + rebounds together for the matchup.
- `ASSISTS_ONLY`: same shared research spine, only assists head executes.
- `REBOUNDS_ONLY`: same shared research spine, only rebounds head executes.

This avoids duplicating the expensive research layer while preserving stat-specific modelling integrity.

## Objective
Build one production NBL player-prop system sharing one free structured research/data spine and one fixture research state, with separate assists and rebounds model outputs.

The system must remain market-input agnostic. Layers 0-2 build and freeze P_model before any sportsbook prices are inspected. Layer 3 accepts whichever post-freeze market adapter is available without changing the frozen model.

## Core flow

`free NBL data pack -> one current fixture research pass -> ASSISTS head + REBOUNDS head -> atomic matchup freeze -> market adapter -> exact mapping -> stat-specific EV/ranking -> bet tracker`

## Shared Layer 0/1 data spine

Primary structured source: official NBL/Genius data exposed by nbl.com.au's Rosetta JSON proxy. No sportsbook data.

Target feeds:
- seasons
- teams
- schedule/results
- current rosters
- player season stats
- player game-log boxscores
- team season stats
- stat leaders
- official NBL news

Historical supporting source:
- nblR / nblr_data public GitHub releases where useful for historical player box scores, team box scores, play-by-play and shot data back to 2015-16.

Optional in-season support:
- current-season Welo supplied after Week 1; never prior-season Welo as a substitute for current team strength.

## One fixture research state
The shared research layer is authoritative for facts common to both stat heads:
- exact fixture/team identity
- current availability and injury state
- expected starters and rotation
- expected minutes bands
- returning/departed players
- imports/transfers/new arrivals
- coaching/system changes
- preseason/Blitz evidence
- current role hierarchy
- opponent context
- rest/travel
- late credible news
- expected game environment / pace

Every material research finding is timestamped and sourced once, then each stat head consumes only the pathways relevant to that stat.

## New/changed player translation
New/changed players require prior-competition translation from the most relevant competitive environment in the previous 12-18 months where possible: NBL, NBA/G League, NCAA, EuroLeague/EuroCup/domestic Europe, B.LEAGUE/Asia, FIBA, Summer League, NBL1, NZ NBL or other credible pro leagues.

No fixed league-to-NBL multiplier unless empirically validated later. Prior production is evidence; current NBL role/minutes remain the key translation target.

## ASSISTS head
Stat-specific pathways:
- minutes / rotation role
- primary vs secondary creator status
- touches / initiation responsibility
- potential assists where available
- AST%, AST/TO and passing role
- teammate shooting/conversion environment
- co-creator competition
- lineup-dependent creation share
- pace/possessions
- opponent scheme / turnover pressure / assist allowance where validated

Outputs:
- player expected assists
- count distribution
- exact threshold probabilities
- Confidence / Fragility
- stat-specific assumptions + adjustment ledger

## REBOUNDS head
Stat-specific pathways:
- minutes / frontcourt role
- ORB%, DRB%, TRB%
- rebound chances/share where available
- expected shot misses
- lineup size / small-ball / two-big structure
- teammate rebound competition
- opponent shot profile and miss environment
- pace/possessions
- opponent offensive/defensive rebounding environment where validated

Outputs:
- player expected rebounds
- count distribution
- exact threshold probabilities
- Confidence / Fragility
- stat-specific assumptions + adjustment ledger

## Early-season regime
Opening weeks receive extra emphasis on roster turnover, imports, new coaches/systems, vacated minutes and actual preseason/Blitz deployment. Prior-season production is a statistical prior only; current expected role must be rebuilt.

For BOTH mode, one researched minutes/rotation state is shared, but assists and rebounds may use different stat-specific scenarios if the same uncertainty has different consequences.

Example: a guard's uncertain starting role may materially change assists distribution but barely move rebounds. A centre's small-ball role may materially change rebounds but not assists.

## Freeze contract
The matchup freezes atomically only after both requested stat heads pass integrity checks.

For each requested head retain:
- exact fixture/player/stat identity
- input data revision
- role/minutes assumptions
- stat-specific ledger
- scenario weights
- expected count
- dispersion/distribution parameters
- complete supported threshold grid
- Confidence / Fragility
- input/output hashes
- original frozen timestamp

If run mode is BOTH and either stat head fails, do not partially expose markets for the other head unless the run was explicitly restarted in single-stat mode.

Material post-freeze availability/role/minutes news invalidates the affected matchup freeze rather than repricing from sportsbook information.

## Market adapter contract
Layer 3 is provider-agnostic. Supported adapters:

### A. Odds API adapter
Use The Odds API automatically if `basketball_nbl` player assists/rebounds markets are actually returned. Standard NBL sport/event coverage does not imply player-prop coverage.

### B. Screenshot adapter
If API player props are unavailable, ingest user-supplied sportsbook screenshots only after `P_MODEL_STATUS: FROZEN`. Extract bookmaker, player, stat, threshold, side, decimal price and capture time. Never alter P_model from screenshot content.

### C. Public-web adapter (best effort only)
A public sportsbook/web source may be used only if prices are directly accessible without login/auth/anti-bot bypass and can be validated reliably. This is optional convenience, never a production dependency.

All adapters normalize into one canonical market record:
`fixture_id, player_id/name, stat_type, side, threshold, decimal_price, bookmaker, captured_at, source_type`

## Layer 3/4 ranking
Keep assists and rebounds EV calculations separate, then allow one combined matchup ranking after exact post-freeze market mapping.

Outputs in BOTH mode:
- BEST SINGLE across assists + rebounds
- ranked assists positives
- ranked rebounds positives
- combined positive-edge ranking
- no forced bet

The ranking may select either stat. It does not require one assists and one rebounds recommendation.

## Runtime design
Use GitHub-first engineering and Cloudflare Worker patterns proven by NCAA:
- source-controlled ETL, models, schemas and tests
- scheduled data refresh
- immutable pack revisions
- resumable run state if required
- server-side freeze integrity checks
- one matchup research receipt shared by requested stat heads
- separate stat-head model receipts
- Custom GPT remains orchestration/research interface, not the sole integrity enforcement layer

Because the user runs match-by-match rather than full-slate, the runtime can be materially simpler than NCAA's slate checkpoint loop while still retaining resumability and immutable freeze state.

## Tracker
Use the existing Nick Bet Tracker after Layer 4. Assists and rebounds use distinct stat/market identifiers. Create model selections after final ranking; record a bet only after explicit user confirmation.

## Build order
1. Audit/live-test official NBL Rosetta feeds and nblR historical assets.
2. Build shared matchup research pack + validation/tests.
3. Build historical player-game training dataset.
4. Develop and walk-forward validate separate assists and rebounds quantitative heads.
5. Add shared current-role/minutes translation + stat-specific contextual ledgers.
6. Add atomic dual-head freeze runtime with `BOTH`, `ASSISTS_ONLY`, `REBOUNDS_ONLY` modes.
7. Implement provider-agnostic market adapter.
8. Add Odds API adapter if live NBL props exist; screenshot adapter regardless.
9. Add Bet Tracker integration.
10. Production acceptance and one NBL Custom GPT production kit capable of running both stats match-by-match.
