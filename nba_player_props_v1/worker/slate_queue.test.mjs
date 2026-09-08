import test from 'node:test';
import assert from 'node:assert/strict';
import {nextResearchBatch, pendingGameIds, researchStatus, validateCheckpointOrder} from './slate_queue.js';

const ids=['0022600001','0022600002','0022600003','0022600004','0022600005'];

test('returns only first two pending games',()=>{
  assert.deepEqual(nextResearchBatch(ids,[]),{
    batch_game_ids:ids.slice(0,2),
    pending_game_ids:ids,
    next_batch_after_checkpoint:true,
  });
});

test('checkpointing advances queue deterministically',()=>{
  const completed=ids.slice(0,2);
  assert.deepEqual(pendingGameIds(ids,completed),ids.slice(2));
  assert.deepEqual(nextResearchBatch(ids,completed).batch_game_ids,ids.slice(2,4));
});

test('rejects out of order checkpoint',()=>{
  assert.throws(()=>validateCheckpointOrder(ids,[],[ids[2]]),/current pending research batch/);
});

test('rejects duplicate checkpoint game',()=>{
  assert.throws(()=>validateCheckpointOrder(ids,[],[ids[0],ids[0]]),/duplicate/);
});

test('research is complete only when all games checkpointed',()=>{
  assert.equal(researchStatus(ids,ids.slice(0,4)),'RESEARCH_IN_PROGRESS');
  assert.equal(researchStatus(ids,ids),'RESEARCH_COMPLETE');
});