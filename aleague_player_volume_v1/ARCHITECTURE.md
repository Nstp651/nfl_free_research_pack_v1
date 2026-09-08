# A-League Player Volume V1 — Architecture

## 1. Design decision

Build one A-League Men match engine with a shared research state and three mathematically linked but separately auditable heads:

- `PLAYER_SHOTS`
- `PLAYER_SHOTS_ON_TARGET`
- `GOALKEEPER_SAVES`

Default run mode is `ALL`. Optional diagnostic modes may isolate a head, but production freeze must explicitly record requested heads and may not silently drop a failed head.

The engine follows the repository Platform V1 lifecycle and uses physically separated pre-market and post-freeze market services.

## 2. Structured data plane

Canonical repository assets will ultimately include:

- `team_match_shooting` — team shots/SoT for and against by fixture;
- `player_match_shooting` — player minutes, starts, shots, SoT where source coverage permits;
- `goalkeeper_match` — minutes, shots on target faced, saves/goals allowed and advanced keeper fields where available;
- `roster_identity` — canonical team/player IDs plus source aliases;
- `qbase_team_shots` — leakage-safe team attacking/defensive priors;
- `qbase_player_shots` — leakage-safe player shot-rate/share priors;
- `qbase_player_sot` — shrunk `P(SoT | shot)` priors;
- `qbase_keeper_saves` — shrunk save-rate priors;
- `manifest` — canonical hashes, schema versions and publication revision.

Historical and current-season asset builds must distinguish event date from retrieval date and must never use post-event information when constructing a historical pre-match feature row.

## 3. Source-lock standard

Every run locks the exact published manifest plus SHA-256 hashes of every asset consumed. Source-control commit may be retained as metadata but runtime correctness cannot depend on the GitHub API being reachable.

Any publication race between manifest and object bytes is rejected or retried.

## 4. Layer 1 current research

The structured pack is prior evidence, not a current-role oracle. Current research must resolve:

- fixture identity and kickoff;
- current squad/availability/suspensions;
- expected XI and formation;
- projected minutes low/mean/high;
- player attacking role and position;
- striker/wing hierarchy and teammate competition;
- set-piece role where relevant to shot profile;
- manager/system change;
- preseason/current-season deployment;
- transfer/import prior-competition context;
- opponent defensive personnel and tactical shape;
- expected possession/territory and likely match-state pathways;
- goalkeeper starter confidence.

Every adjustment must bind to evidence IDs and a declared model pathway. Missing advanced metrics are `UNAVAILABLE`, never zero.

## 5. Team shot environment

Layer 2 begins by estimating market-blind team shot means.

Baseline inputs should include leakage-safe own attacking shots/90 and opponent shots allowed/90, shrunk toward league baselines and separated by home/away when sample supports it.

Current-information scenario multipliers may adjust the baseline for lineup, formation/system, role redistribution and opponent personnel. Multipliers must be bounded and receipt-bearing. They cannot be derived from sportsbook totals, spreads, prices or implied probabilities.

The first calibration family is Negative Binomial with mean `mu_team_shots` and dispersion `k_team`. Alternative count families may replace it only after out-of-sample challenge.

## 6. Player shot allocation

For each projected outfield player:

`mu_player_shots = mu_team_shots * normalized_shot_share * minutes_mean/90 * role_multiplier`

Production implementation must avoid double-counting minutes inside both the share prior and the explicit minutes term. Shot-share priors therefore need a precisely documented exposure basis.

Allocation audit:

`sum(mu_player_shots) + mu_unmodelled_shots ~= mu_team_shots`

within a hard tolerance defined by the Worker. The unmodelled bucket covers bench/low-minute/uncertain players and may not be silently discarded.

Player shot counts use a calibrated Negative Binomial (`mean`, `dispersion`). Dispersion may be player-class or hierarchical rather than individual when samples are thin.

## 7. Shots on target head

For player `i`:

`p_sot_i = shrink(observed_sot_i / observed_shots_i, position/league prior)`

then apply only evidence-supported current-role/shot-quality scenarios.

`mu_player_sot = mu_player_shots * p_sot_i`

Under Poisson-Gamma binomial thinning, the SoT marginal remains Negative Binomial with the same dispersion parameter as its parent shot process. This is the V1 structural prior, not an unquestioned truth; calibration must challenge both mean and tails.

Hard coherence audits:

- `0 <= p_sot_i <= 1`
- `mu_player_sot <= mu_player_shots`
- `P(2+ SoT) <= P(1+ SoT)` etc.

## 8. Goalkeeper saves head

For the projected goalkeeper:

`mu_saves = mu_opponent_sot * p_save * minutes_mean/90`

where `p_save` is hierarchically shrunk from goalkeeper/team/league evidence and may incorporate validated shot-quality information such as post-shot xG when available under an approved data path.

V1 uses thinning-compatible Negative Binomial tails as the initial family. Before production sign-off it must be tested against alternatives and must pass calibration by threshold, team-strength band and projected SoT band.

## 9. Prior-competition translation

New-to-A-League players cannot be assigned a fake A-League history. They use `PRIOR_COMP_TRANSLATION` with explicit source league, role, minutes, shots/90, SoT/90 and uncertainty widening.

There is no universal league multiplier. Translation must be evidence-backed and more uncertain than an otherwise equivalent established A-League prior unless validation proves otherwise.

## 10. Research checkpoint

The pre-market Worker persists:

- run/fixture/source identity;
- evidence ledger;
- player availability and projected minutes bands;
- role scenarios and weights;
- team shot environment scenarios;
- prior-competition translation records;
- declared unavailable fields;
- explicit assertion that no market-derived input was used.

Only `RESEARCH_COMPLETE` may enter Layer 2.

## 11. Immutable freeze

Requested heads freeze atomically. Each player/head artifact contains:

- prior/QBASE anchor;
- scenario ledger;
- final mean;
- dispersion;
- distribution family/version;
- at-least ladder;
- Confidence and Fragility;
- model hash.

Run-level freeze returns an immutable receipt binding source revision, research hash and every frozen player hash. Repeated compute after freeze returns the original artifact.

## 12. Post-freeze market service

The market Worker cannot create probabilities. It requires an authoritative frozen run and exact freeze receipt before evaluating a market row.

Accepted adapters may include `odds_api`, `screenshot` and explicitly approved public sources. Rows are normalized to:

`fixture_id + player_id + stat + side + threshold + decimal_price + book + captured_at`

Only exact frozen thresholds are eligible. Highest valid current price is retained for identical keys. Integer lines, if any, require push-aware EV.

## 13. Ranking

Rank across all enabled heads using deterministic fair price, implied probability, edge and expected ROI. Ranking may apply model-confidence and fragility safeguards defined before market access.

`NO BET` is always valid. No head is owed a selection.

## 14. Production boundary

A source being visible on the web does not authorize unattended scraping. Scheduled ingestion is permitted only when the source route is explicitly approved in `source_registry.json`. Research-only sources can enrich Layer 1 without becoming automated production dependencies.
