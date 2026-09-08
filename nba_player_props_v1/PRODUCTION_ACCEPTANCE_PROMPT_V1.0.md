# NBA ASSISTS + REBOUNDS V1.0 — PRODUCTION ACCEPTANCE PROMPT

```text
NBA ASSISTS + REBOUNDS V1.0 — FULL PRODUCTION ACCEPTANCE

Run Mode: BOTH

Select one exact future NBA America/New_York league date that is available through the installed Research Action and has real post-freeze player-prop availability through the installed Market Action. Run the complete V1.0 production workflow across EVERY still-eligible game on that league date.

This is an acceptance run, not a demonstration. Do not use synthetic fixtures, synthetic prices, mock receipts or claimed calculations.

Acceptance requirements:

1. PREFLIGHT
- Research health PASS: market_data=false, Durable Object available, source_commit_ready=true.
- Market health PASS: post_freeze_only=true, Research service binding available, Market Durable Object available, Odds API key configured.
- Bet Tracker health PASS on current production schema.

2. LAYER 0 / RUN LOCK
- Resolve exact ET league-date fixture slate.
- Start one NEW persistent BOTH run.
- Preserve run_id, source commit, QBASE head versions/receipts and exact eligible games.

3. LAYER 1 — FULL SERVER BATCH LOOP
- Call the next research batch endpoint.
- Research ONLY the returned 1–2 game IDs.
- Complete the full installed current-information methodology for both teams and all meaningful rotation players.
- Checkpoint the completed current batch immediately.
- Verify those IDs moved to completed_game_ids before requesting another batch.
- Repeat until pending_count=0 and status=RESEARCH_COMPLETE.
- Never preload or research later pending games before the current batch is checkpointed.

For each game prove the checkpoint includes current availability, starters/rotation, minutes low/mean/high, creator/frontcourt hierarchy, trades/FA/vacated opportunity, coaching/system, preseason/camp evidence where relevant, lineup dependencies, assists/rebounds causal pathways, team environment and specialist-metric statuses.

4. LAYER 2 — WHOLE-SLATE SERVER FREEZE
- Call freeze only after RESEARCH_COMPLETE.
- No client final means.
- Require status=FROZEN.
- Capture original frozen_at and freeze_receipt_sha256.
- Verify all eligible games are represented in the immutable slate freeze and requested heads use exact probability grids.

5. MARKET-BLIND NEGATIVE CONTROL
- Confirm no sportsbook price was accessed before the successful freeze.
- If evidence shows pre-freeze price access, FAIL acceptance.

6. LAYER 3 — REAL ODDS API
- Refresh through the installed Market Action only after freeze.
- Confirm the Market Worker received the server market-access grant.
- Confirm exact one-to-one frozen fixture -> Odds API event resolution.
- Confirm only player_assists, player_assists_alternate, player_rebounds, player_rebounds_alternate were requested.
- Confirm Overs only are ranked.
- Capture market snapshot receipt / quota metadata.

7. LAYER 4
- Produce BEST SINGLE or NO BET.
- Produce Top 10 combined positive edges plus separate assists/rebounds positive rankings.
- Verify exact threshold mapping and push-aware integer math; no interpolation.

8. BET TRACKER
- Create exactly one model run AFTER completed Layer 4 with:
  sport=nba
  league=nba
  model_name=Nick NBA Assists + Rebounds
  model_version=1.0
- Preserve original frozen_at / freeze receipt and returned model_selection_ids.
- Do NOT log an actual wager.

9. BET365 / MANUAL SCREENSHOT ACCEPTANCE
If current post-freeze sportsbook screenshot(s) are attached to this acceptance run:
- extract every clearly visible valid Assists/Rebounds Over quote;
- ingest them through refreshNbaPlayerPropsManualMarkets using SAME run_id and exact freeze_receipt_sha256;
- rerun Layer 3/4 only;
- prove run_id unchanged;
- prove frozen_at unchanged;
- prove freeze_receipt_sha256 unchanged;
- prove no Layer 1 research was rerun;
- prove no frozen player probability/model mean changed;
- prove duplicate exact thresholds use the highest valid current price.

If no valid post-freeze screenshot is available, do NOT waive this gate. Report ACCEPTANCE_PENDING_SCREENSHOT_GATE and do not call V1 production-ready.

10. FINAL ACCEPTANCE REPORT
Return explicit PASS / FAIL for every gate above, plus:
- run_id
- ET league date
- eligible/completed game counts
- source commit
- Assists QBASE version/receipt
- Rebounds QBASE version/receipt
- frozen_at
- freeze_receipt_sha256
- Odds API snapshot receipt and event-resolution count
- Layer 4 BEST SINGLE / NO BET
- Tracker model_run_id and model_selection_ids
- screenshot refresh receipt if completed
- NBL isolation status

Do not merge PR #20 and do not call NBA V1 production-ready unless EVERY required gate, including the screenshot refresh gate, has actually passed.
```
