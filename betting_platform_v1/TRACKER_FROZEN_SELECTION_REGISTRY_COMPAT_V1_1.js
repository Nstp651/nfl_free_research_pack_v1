// ============================================================
// NICK BET TRACKER — FROZEN SELECTION REGISTRY COMPAT DELTA V1.1
// Target Worker: nick-betting-api
// Applies to: TRACKER_FROZEN_SELECTION_REGISTRY_PATCH_V1.js
//
// Existing NFL V5 tracker selections may store ladder threshold 6 for
// "6+ receptions", while the sportsbook/ensure contract correctly sends
// the exact sportsbook half-point line 5.5. These are the same frozen
// ladder point and MUST reuse the existing tracker selection ID.
//
// Replace ONLY findExistingFrozenNflSelection() in the V1 registry module
// with the function below. No D1 migration is required.
// ============================================================

async function findExistingFrozenNflSelection(
  env,
  modelRunId,
  playerName,
  threshold
) {
  const ladderThreshold = nflReceptionLadderKey(threshold);

  return await env.BET_DB
    .prepare(`
      SELECT *
      FROM model_selections
      WHERE model_run_id = ?1
        AND lower(trim(market_family)) = 'nfl_receptions'
        AND lower(trim(player_name)) = lower(trim(?2))
        AND lower(trim(COALESCE(side, ''))) = 'over'
        AND (
          ABS(threshold - ?3) < 0.000001
          OR ABS(threshold - ?4) < 0.000001
        )
      ORDER BY
        CASE WHEN ABS(threshold - ?3) < 0.000001 THEN 0 ELSE 1 END,
        created_at ASC
      LIMIT 1
    `)
    .bind(modelRunId, playerName, threshold, ladderThreshold)
    .first();
}
