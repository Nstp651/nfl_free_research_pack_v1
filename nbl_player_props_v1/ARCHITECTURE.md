# NBL Player Props V1 — One Match Engine, Dual Stat Heads

## Decision
Build one production NBL matchup engine with a shared market-blind research state and two mathematically independent quantitative heads:

1. ASSISTS
2. REBOUNDS

Run modes:
- `BOTH` (default)
- `ASSISTS_ONLY`
- `REBOUNDS_ONLY`

One Layer 0/1 pass prevents duplicated research while separate Layer 2 distributions preserve stat-specific modelling integrity.

## End-to-end flow

`immutable free data assets -> exact fixture/run lock -> current basketball research -> research checkpoint -> server QBASE/current-role scenarios -> atomic requested-head freeze -> immutable receipt + per-player hashes -> separate post-freeze market gateway -> exact EV mapping -> no-forced-bet ranking`

The Custom GPT orchestrates research and Actions. It is not trusted as the sole integrity layer.

---

## 1. Structured data plane
Primary current structured source:
- official NBL/Genius Rosetta data exposed by nbl.com.au.

Historical source:
- nblR / nblr_data public GitHub releases.

Runtime assets committed under `data/`:
- immutable assists QBASE;
- immutable rebounds QBASE;
- historical next-game player/team prior snapshot;
- source receipt;
- manifest binding canonical hashes and revisions.

Routine scheduled refresh updates the prior snapshot. QBASE retraining is explicit-only, preventing silent model drift during the season.

Layers 0–2 reject market-like fields.

---

## 2. Persistent Research/Freeze Worker
Production project:
`nbl-player-props-research-v1`

A Durable Object `NblMatchRun` owns one matchup run.

At initialization it:
- resolves one exact future fixture;
- pins one GitHub `main` commit;
- loads the manifest from that pinned commit;
- verifies QBASE/prior canonical hashes;
- stores exact fixture/run/asset identity;
- rejects already-started fixtures.

The run remains market blind.

### Research seed
The Worker publishes:
- locked fixture/rosters;
- prior-NBL history state;
- returning-player server QBASE baselines;
- `PRIOR_COMP_TRANSLATION_REQUIRED` state for players without sufficient NBL history.

Structured data is explicitly labelled prior evidence. Current availability, minutes, role, lineup, imports, coaching and late news remain a separate current-research responsibility.

### Research checkpoint
The Custom GPT submits an evidence-bound current research context. The Worker validates:
- exact fixture/pack/run-mode identity;
- source receipts;
- player team membership;
- availability;
- projected minute bands;
- role state;
- market boundary.

A research hash is persisted before Layer 2.

---

## 3. Quantitative authority
### Returning players
The Worker owns the historical QBASE calculation.

Supported serverized paths:
- `QBASE_RUNTIME_SCORE`
- `QBASE_MINUTES_RECOMPUTE`

For these paths, the Worker calculates/overwrites the mean and quantitative receipt. A client cannot arbitrarily move the returning-player historical anchor.

`EMPIRICAL_ROLE_SPLIT` is retained for evidence-supported role changes that minutes alone cannot represent. It requires explicit evidence and quantitative receipt.

### New-to-NBL players
Players without NBL prior use `PRIOR_COMP_TRANSLATION` only for that head.

Translation is based on current research into the most relevant prior competition. There is no fixed universal league multiplier. Translated heads must use an explicit `MAX_QBASE_PRIOR_COMP` dispersion override that can widen but never narrow the QBASE temporal-OOS dispersion.

---

## 4. Independent stat heads
### ASSISTS
Primary pathways:
- minutes / starter probability;
- primary vs secondary creator role;
- initiation/touches/potential assists when available;
- co-creator competition;
- lineup-specific creation share;
- teammate conversion environment;
- pace/possessions;
- opponent pressure/assist environment where validated.

### REBOUNDS
Primary pathways:
- minutes / frontcourt role;
- ORB/DRB/TRB profile;
- lineup size and small-ball/two-big structure;
- teammate rebound competition;
- shot/miss environment;
- pace/possessions;
- opponent rebounding environment where validated.

The two heads may share the same researched minutes/rotation facts while translating them differently into stat-specific scenarios.

---

## 5. Atomic freeze
The Worker freezes all requested heads together.

BOTH mode cannot partially succeed for one stat while silently dropping the other.

Each frozen head contains:
- QBASE anchor;
- scenario ledger;
- final mean;
- temporal-OOS or explicitly widened dispersion;
- count distribution;
- at-least ladder;
- half-point grid;
- integer over/push/under grid;
- Confidence / Fragility.

The matchup returns:
- immutable `freeze_receipt_sha256`;
- original `frozen_at`;
- research/QBASE binding;
- PASS integrity audits;
- compact frozen player summaries.

Each full stored player payload also has an independent `player_model_sha256` exposed in the compact receipt. Frozen-player retrieval recomputes this hash server-side before returning the payload.

Repeated compute after freeze returns the original receipt rather than recomputing.

---

## 6. Separate Market Worker
Production project:
`nbl-player-props-market-v1`

This Worker cannot create P_model. It only evaluates post-freeze market observations.

Accepted source types:
- `odds_api`
- `screenshot`
- `public_web`

Before evaluating a row it requires:
- run is FROZEN;
- exact caller freeze receipt matches;
- fixture matches;
- market `captured_at >= frozen_at`;
- compact player hash exists;
- full frozen-player response carries the same receipt/timestamp/hash;
- independently recomputed full-player hash matches `player_model_sha256`.

Rows from different sources are first resolved to the exact frozen player identity. The highest valid price is then retained for each exact:
`fixture + frozen player + stat + side + threshold`.

This correctly allows an ID-bearing API row and name-only Bet365 screenshot row to compete for best price.

Only exact frozen integer/half-point thresholds are evaluated. No interpolation.

Integer lines use explicit push-aware EV.

---

## 7. Early-season edge regime
Opening weeks deliberately emphasize information that historical averages are slow to absorb:
- roster turnover;
- imports/transfers;
- vacated minutes/usage;
- coaching/system changes;
- preseason/Blitz deployment;
- injuries and temporary opportunity;
- actual current role hierarchy.

Prior-season NBL production is an anchor, not a current-role assumption.

Current-season Welo may be used as supporting team-strength evidence after Week 1 when supplied/available. Prior-season Welo is not used as a substitute for current team strength.

---

## 8. Custom GPT production package
- `NBL_ASSISTS_REBOUNDS_4_LAYER_MASTER_PRODUCTION_V1.0.md`
- `GPT_INSTRUCTIONS_PRODUCTION_V1.0.md`
- `LAUNCH_PROMPT_PRODUCTION_V1.0.md`
- `INSTALL_PRODUCTION_V1.0.md`
- `openapi_v1.yaml`
- `market_openapi_v1.yaml`

The Research Action performs fixture/run/research/freeze operations. The Market Action is physically separate and post-freeze only.

---

## 9. Final ranking
BOTH mode may output:
- BEST SINGLE across both stats;
- assists positive edges;
- rebounds positive edges;
- combined positive-edge ranking.

There is no requirement to produce one recommendation from each stat. NO BET is a valid production result.

Material post-freeze basketball news invalidates the run; it never justifies changing a frozen P_model because the market moved.

## Production acceptance
Source architecture is not sufficient for sign-off. Production requires passing repository verification, Cloudflare deployment health, clean Custom GPT schema imports and a live future-fixture E2E proving freeze persistence, per-player hash binding and post-freeze-only market evaluation.
