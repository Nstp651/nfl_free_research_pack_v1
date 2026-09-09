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

2. LAYER 0 / RUN LOCK + START IDEMPOTENCY
- Resolve exact ET league-date fixture slate.
- Create one stable Research start request_id and start one NEW persistent BOTH run.
- Preserve request_id, run_id, source commit, QBASE head versions/receipts and exact eligible games.
- Retry the exact same start request_id/date/mode once and prove it returns the SAME run_id rather than creating a second run.
- A changed start payload under the same idempotency identity must not replace the existing run.

3. LAYER 1 — FULL SERVER BATCH LOOP
- Call the next research batch endpoint.
- Research ONLY the returned 1–2 game IDs.
- Complete the full installed current-information methodology for both teams and all meaningful rotation players.
- Checkpoint the completed current batch immediately.
- Verify those IDs moved to completed_game_ids and record their research_receipts before requesting another batch.
- For one completed batch, retry the EXACT same checkpoint payload and prove completed IDs/receipts do not change or duplicate.
- Confirm a deliberately changed retry would be rejected; do not overwrite persisted research.
- Repeat until pending_count=0 and status=RESEARCH_COMPLETE.
- Never preload or research later pending games before the current batch is checkpointed.

For each game prove the checkpoint includes current availability, starters/rotation, minutes low/mean/high, creator/frontcourt hierarchy, teammate competition, trades/FA/vacated opportunity, coaching/system, preseason/camp evidence where relevant, lineup dependencies, role breakpoints, assists/rebounds causal pathways, current team environment, current opponent assists/rebounds-allowed environment and specialist-metric statuses.

For each relevant player prove role_research contains evidence-bound rotation_role, hierarchy_and_competition, lineup_dependencies, role_breakpoints and change_summary.

4. LAYER 2 — WHOLE-SLATE SERVER FREEZE + RUNTIME GUARDRAILS
- Call freeze only after RESEARCH_COMPLETE.
- No client final means.
- Require status=FROZEN.
- Capture original frozen_at and freeze_receipt_sha256.
- Retry the same empty freeze call and prove frozen_at, freeze_receipt_sha256 and frozen P_model are identical.
- Verify all eligible games are represented in the immutable slate freeze and requested heads use exact probability grids.
- Verify frozen players/heads expose immutable player_model_sha256 and head_model_sha256 lineage.
- Verify current opponent features enter the typed head-specific lineup transform where those promoted features exist.
- Verify role/opportunity/lineup values are server-constrained to the promoted empirical feature envelope. A syntactically valid but absurd feature value must fail closed rather than create an extreme P_model.

5. MARKET-BLIND NEGATIVE CONTROL
- Confirm no sportsbook price was accessed before the successful freeze.
- If evidence shows pre-freeze price access, FAIL acceptance.

6. LAYER 3 — REAL ODDS API + MARKET IDEMPOTENCY
- Create one new stable market refresh_request_id and refresh through the installed Market Action only after freeze.
- Use Australian region coverage by default unless an explicit accepted override is needed.
- Confirm the Market Worker received the server market-access grant.
- Confirm exact one-to-one frozen fixture -> Odds API event resolution.
- Confirm only player_assists, player_assists_alternate, player_rebounds, player_rebounds_alternate were requested.
- Confirm Overs only are ranked.
- Confirm any market observation captured before frozen_at is rejected.
- Capture market snapshot receipt / quota metadata.
- Retry the EXACT same refresh_request_id once and prove `replayed=true`, identical current API snapshot identity, and no second Odds API request/quota spend.
- Confirm a genuinely new price pull requires a NEW refresh_request_id.
- Confirm a superseded old refresh_request_id cannot be reused ambiguously.

7. LAYER 4
- Produce BEST SINGLE or NO BET.
- Produce Top 10 combined positive edges plus separate assists/rebounds positive rankings.
- Verify exact threshold mapping and push-aware integer math; no interpolation.
- Verify ranked selections retain exact frozen player/head hashes and freeze receipt.

8. BET TRACKER
- Create exactly one model run AFTER completed Layer 4 with:
  sport=nba
  league=nba
  model_name=Nick NBA Assists + Rebounds
  model_version=1.0
- Preserve original frozen_at / freeze receipt and returned model_selection_ids.
- For integer lines preserve push-adjusted fair/market math and P_push.
- Do NOT log an actual wager.

9. LATE-NEWS IMMUTABILITY CONTROL
- After freeze, demonstrate that an invalidation event can mark an affected game FROZEN_BUT_INVALIDATED without changing frozen probabilities, frozen_at or freeze_receipt_sha256.
- Confirm the subsequent market-access grant excludes the invalidated game.
- Confirm a freeze retry after invalidation still returns the original freeze.
- Do not use this negative-control invalidation on the real recommendation slate unless a disposable acceptance run/scope has been selected for this purpose; otherwise use accepted live evidence from a dedicated acceptance run.

10. BET365 / MANUAL SCREENSHOT ACCEPTANCE
If current post-freeze sportsbook screenshot(s) are attached to this acceptance run:
- extract every clearly visible valid Assists/Rebounds Over quote;
- create a NEW manual refresh_request_id and ingest through refreshNbaPlayerPropsManualMarkets using SAME run_id and exact freeze_receipt_sha256;
- retry that exact manual refresh_request_id once and prove `replayed=true` with no duplicate snapshot/history write;
- rerun Layer 3/4 only;
- prove run_id unchanged;
- prove frozen_at unchanged;
- prove freeze_receipt_sha256 unchanged;
- prove no Layer 1 research was rerun;
- prove no frozen player probability/model mean/player/head hash changed;
- prove duplicate exact thresholds use the highest valid current price.

If no valid post-freeze screenshot is available, do NOT waive this gate. Report ACCEPTANCE_PENDING_SCREENSHOT_GATE and do not call V1 production-ready.

11. FINAL ACCEPTANCE REPORT
Return explicit PASS / FAIL for every gate above, plus:
- start request_id
- run_id
- ET league date
- eligible/completed game counts
- research receipts
- source commit
- Assists QBASE version/receipt
- Rebounds QBASE version/receipt
- frozen_at
- freeze_receipt_sha256
- Odds API refresh_request_id, snapshot receipt and event-resolution count
- Layer 4 BEST SINGLE / NO BET
- Tracker model_run_id and model_selection_ids
- manual refresh_request_id/screenshot refresh receipt if completed
- NBL isolation status

Do not merge PR #20 and do not call NBA V1 production-ready unless EVERY required gate, including the screenshot refresh gate, has actually passed.
```
