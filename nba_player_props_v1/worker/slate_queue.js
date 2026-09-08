export function requireThat(ok, message) {
  if (!ok) throw new Error(message);
}

export function pendingGameIds(eligibleGameIds, completedGameIds = []) {
  requireThat(Array.isArray(eligibleGameIds) && eligibleGameIds.length > 0, 'eligible_game_ids required');
  const done = new Set(completedGameIds);
  return eligibleGameIds.filter((id) => !done.has(id));
}

export function nextResearchBatch(eligibleGameIds, completedGameIds = [], batchSize = 2) {
  requireThat(Number.isInteger(batchSize) && batchSize >= 1 && batchSize <= 2, 'batch size must be 1 or 2');
  const pending = pendingGameIds(eligibleGameIds, completedGameIds);
  return {
    batch_game_ids: pending.slice(0, batchSize),
    pending_game_ids: pending,
    next_batch_after_checkpoint: pending.length > batchSize,
  };
}

export function validateCheckpointOrder(eligibleGameIds, completedGameIds, submittedGameIds) {
  requireThat(Array.isArray(submittedGameIds) && submittedGameIds.length >= 1 && submittedGameIds.length <= 2, 'submit 1 or 2 games');
  const expected = new Set(nextResearchBatch(eligibleGameIds, completedGameIds, 2).batch_game_ids);
  const seen = new Set();
  for (const id of submittedGameIds) {
    requireThat(expected.has(id), 'game is not in current pending research batch');
    requireThat(!seen.has(id), 'duplicate checkpoint game');
    seen.add(id);
  }
  return true;
}

export function researchStatus(eligibleGameIds, completedGameIds = []) {
  return pendingGameIds(eligibleGameIds, completedGameIds).length === 0
    ? 'RESEARCH_COMPLETE'
    : 'RESEARCH_IN_PROGRESS';
}