# NBA V1 takeover evidence

Status: **BUILDING — NOT PRODUCTION READY. PR #20 remains draft.**

The takeover audited handoff head `7072c43a42cb01b3b03c7a1fbabdd50651308973`,
all 22 PR files and the NBL reference configuration. Both head workflows were
successful. The PR contained no NBL changes. Deployment ownership is unchanged.

## Implemented and executed

- SHA-256-pinned five-season historical builder with byte-count verification.
- Finite/integer count, boolean flag, identity, minutes-clock and shot validation.
- Explicit 30-franchise filtering: upstream All-Star games also use season type 2.
- 139,809 accepted NBA player-games, seasons ending 2022–2026, with zero duplicate
  ESPN player/game keys and complete timestamps. These are ESPN identities;
  the official NBA crosswalk has NOT passed.
- Two separate normalization builds from identical pinned cached inputs produced
  `b19e5ea32b9b257c57b9c4a16ced34b5d70a91608a99f042d2a34441705f933c`.
- Independent ASSISTS and REBOUNDS four-candidate temporal challenges: shrunk
  Poisson/NB and regularized count GLM with Poisson/NB distributions.
- Expanding 2024/2025 validation folds; 2026 held out from model selection.
- Early-season, team-change, starter-change, low-history and role-proxy slices.
- Deterministic parameter-export score checks, calibration bins, integer push
  probabilities, count likelihood, Brier, bias, MAE, RMSE and interval coverage.
- Read-only official-source probes and a non-promoted specialist metric registry.

## Candidate results, not promotion

Both heads independently selected `glm_nb`. The distribution's dispersion is
estimated on training residuals only. No sportsbook lines or prices were used.

| 2026 holdout (28,462 player-games) | Assists | Rebounds |
|---|---:|---:|
| Candidate Brier, fixed count grid | 0.059140 | 0.052230 |
| Shrunk Poisson baseline Brier | 0.061321 | 0.054296 |
| Candidate count NLL | 1.796993 | 2.210086 |
| Candidate MAE | 1.382406 | 1.952015 |

Brier values average a fixed head-specific grid, including low-probability tails;
they are not directly comparable between heads and are not a betting-return test.
Holdout evaluation uses rolling historical box features, not replayed current-news
research. Specialist features, rookie translations and researched current-role
transforms have not been validated. These artifacts are **experimental**, not live
QBASE authority. No model-family reselection using the holdout is permitted.

## Failed or unpassed dependencies

1. Official current schedule returned HTTP 403 locally; the published tracking
   example timed out. These are environment-specific probe results, not proof
   that the sources never work. CI repeats probes from its own environment.
2. Independent box reconciliation, official NBA identity crosswalk, current source
   freshness and full specialist coverage remain unpassed. Other specialist fields
   marked unavailable are absent from the audited core table; alternative sources
   are explicitly not yet audited.
3. Quantitative promotion remains blocked by source acceptance, specialist challenge,
   holdout cohort review, researched current-role runtime scoring and controlled
   prior-competition translation.
4. Per the handoff, full persistent Worker implementation follows quantitative
   promotion. No Research/Freeze Worker, live Market Worker, tracker acceptance or
   production GPT artifacts were represented as completed in this tranche.
5. No Cloudflare account tools are exposed in the takeover session. Plugin directory
   search for Cloudflare returned no results. No Worker/account configuration was
   changed. Cloudflare native Git must remain deployment owner.
6. Live whole-slate Custom GPT acceptance and post-freeze screenshot refresh have
   not run. Neither can be replaced by synthetic tests or merely green CI.

## Resume from this work

Inspect the latest branch and the JSON evidence in `evidence/`. Finish source
reconciliation and freshness from an environment with official source access.
Review holdout cohorts against predeclared promotion criteria; do not tune against
the holdout. Finish QBASE/current-role/prior-competition acceptance before implementing
the persistent freeze runtime. Then complete market networking, tracker, schemas,
GPT artifacts, Cloudflare verification and the real-slate/screenshot acceptance.

Rebuild the pinned source with:

```bash
python -m nba_player_props_v1.historical.build_history --manifest nba_player_props_v1/evidence/source_pins.json --cache /tmp/nba-source-cache --output /tmp/nba-source-rebuild --as-of 2026-09-08T16:00:00Z
python -m nba_player_props_v1.model.challenge --history /tmp/nba-source-rebuild/player_games.csv --output /tmp/nba-challenge
```

CI now independently downloads pinned inputs and compares the normalized table hash.
Its source-connectivity step is diagnostic: completing that step does not promote
the source. The resulting JSON records actual blocked/successful HTTP outcomes.
