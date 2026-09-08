# NBA ASSISTS + REBOUNDS V1.0 — LAUNCH PROMPT

```text
NEW NBA ASSISTS + REBOUNDS MODEL RUN — V1.0

NBA League Date (America/New_York): [YYYY-MM-DD]
Run Mode: BOTH

Run the complete installed V1.0 production workflow automatically across the entire still-eligible NBA slate for that ET league date.

Complete:
1. Research / Market / Bet Tracker preflight and exact fixture validation.
2. Start one NEW persistent whole-slate run. Do not reuse an unrelated prior run.
3. Layer 1 using the server-enforced 1–2 game checkpoint loop. Research only the games returned in the current batch, checkpoint them, verify persistence, then request the next batch.
4. Complete the full installed current-information research methodology for every meaningful rotation player, with heavy early-season role translation where relevant.
5. After and only after RESEARCH_COMPLETE, execute the server-authoritative whole-slate Layer 2 freeze.
6. Require immutable P_model freeze before any sportsbook access.
7. Run the post-freeze Odds API gateway for standard and alternate Assists/Rebounds Overs.
8. Complete Layer 4 global ranking: BEST SINGLE, Top 10 combined positives, assists positives, rebounds positives, or NO BET.
9. Create the Bet Tracker model run only after completed Layer 4.

No prices before freeze. No interpolation. No manual final-mean overrides. No forced bet. No staking advice. Do not log an actual wager unless I later explicitly confirm the exact selection, bookmaker, accepted odds and stake.

Complete automatically without pausing unless execution genuinely cannot continue.
```
