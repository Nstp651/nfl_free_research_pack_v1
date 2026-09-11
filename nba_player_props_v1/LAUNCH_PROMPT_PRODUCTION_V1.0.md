# NBA ASSISTS + REBOUNDS V1.0 — LAUNCH PROMPT

```text
NEW NBA ASSISTS + REBOUNDS MODEL RUN — V1.0

NBA League Date (America/New_York): [YYYY-MM-DD]
Run Mode: BOTH

Run the complete installed V1.0 production workflow automatically across the entire still-eligible NBA slate for that ET league date.

Complete:
1. Research / Market / Bet Tracker preflight and exact fixture validation.
2. Create and preserve one stable Research start request_id, then start one NEW persistent whole-slate run. If start delivery times out, retry the exact same request_id/date/mode; do not create a duplicate run.
3. Layer 1 using the server-enforced 1–2 game checkpoint loop. Research only the games returned in the current batch, checkpoint them, verify persisted research receipts, then request the next batch. If checkpoint delivery times out, retry the exact same payload only.
4. Complete the full installed current-information research methodology for every meaningful rotation player, including evidence-bound rotation role, creator/frontcourt hierarchy, teammate competition, lineup dependencies, role breakpoints, projected minutes and current opponent Assists/Rebounds environment. Apply heavy early-season role translation where relevant.
5. After and only after RESEARCH_COMPLETE, execute the server-authoritative whole-slate Layer 2 freeze. If freeze delivery times out, retry the same run; preserve the original immutable freeze.
6. Require immutable P_model freeze before any sportsbook access.
7. Run the post-freeze Odds API gateway for standard and alternate Assists/Rebounds Overs using the Australian market region by default.
8. Complete Layer 4 global ranking: BEST SINGLE, Top 10 combined positives, assists positives, rebounds positives, or NO BET.
9. If Layer 4 has actionable positive-edge selections, create exactly one Bet Tracker model run using those selections only and a mandatory stable tracker request_id. If Layer 4 is NO BET, do not fabricate a selection and do not create a tracker model run; report the tracker skip. If a later price refresh creates the first actionable positive edge, create the one tracker run then using the same immutable freeze.

No prices before freeze. No interpolation. No manual final-mean overrides. Do not work around server empirical transform guardrails. No forced bet. No staking advice. `recordBet` is consequential: do not log an actual wager unless I later explicitly confirm the exact stored selection, bookmaker, accepted odds and stake.

Complete automatically without pausing unless execution genuinely cannot continue.
```
