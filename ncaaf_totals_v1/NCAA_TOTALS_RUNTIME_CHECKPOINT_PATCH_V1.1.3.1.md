# NCAA TOTALS RUNTIME CHECKPOINT PATCH — V1.1.3.1

This is an orchestration-only hardening patch to V1.1.3. Quantitative methodology, QBASE, probability schema, identity binding, market boundary, freeze mathematics and market integration are unchanged.

The research Worker exposes a server-bounded queue of at most two pending eligible games. `getNcaafTotalsFreezeResearch` returns only the current queue head. Repeated reads before checkpoint return the same pending batch. `checkpointNcaafTotalsResearch` accepts at most two contexts and only IDs in that current queue head.

Required loop: retrieve <=2 pending games -> complete all mandatory live research for those games -> checkpoint immediately -> verify progress -> retrieve next batch. Never research/preload later games before the current batch is persisted.

If ChatGPT message delivery times out, recover the SAME run with `getNcaafTotalsFreezeRun` and continue only `pending_game_ids`. Do not silently start a replacement run. Compute freeze only when pending is empty.

Purpose: make research persistence survive conversational runtime limits without reducing research depth, weakening integrity gates, or allowing partial-slate freeze.
