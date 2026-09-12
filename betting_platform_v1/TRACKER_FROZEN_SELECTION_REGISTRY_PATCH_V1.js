// ============================================================
// NICK BET TRACKER — FROZEN SELECTION REGISTRY PATCH V1
// Target Worker: nick-betting-api
// Purpose: allow any exact NFL Receptions V5 frozen ladder point to
// be attached to an existing tracker model run on demand, without
// recreating the model run or trusting GPT-supplied P_model values.
//
// No D1 migration is required. This patch uses the existing
// model_runs + model_selections schema.
// ============================================================

const NFL_V5_CONTROL_BASE =
  "https://nfl-receptions-platform-v5.nickarnott01.workers.dev";

const FROZEN_SELECTION_PROB_TOLERANCE = 1e-10;

// ------------------------------------------------------------
// ROUTE INSERTION
// Add this AFTER authentication succeeds and BEFORE the global
// GET-only guard. Keep it before generic /tracker/model-runs/{id}
// handling for clarity.
// ------------------------------------------------------------
//
// const frozenSelectionMatch = url.pathname.match(
//   /^\/tracker\/model-runs\/([^/]+)\/selections\/ensure$/
// );
//
// if (frozenSelectionMatch && request.method === "POST") {
//   return await ensureNflReceptionsFrozenSelection(
//     request,
//     env,
//     decodeURIComponent(frozenSelectionMatch[1])
//   );
// }
//
// Also add this endpoint to the root available_endpoints array:
// /tracker/model-runs/{runId}/selections/ensure

async function ensureNflReceptionsFrozenSelection(
  request,
  env,
  trackerRunId
) {
  await trackerAssertSchema(env);

  const modelRunId = trackerText(trackerRunId);

  if (!modelRunId) {
    return jsonResponse({ error: "Missing tracker model run id." }, 400);
  }

  let body;
  try {
    body = await trackerJsonBody(request);
  } catch (error) {
    return jsonResponse({ error: error.message }, 400);
  }

  const v5RunId = trackerText(body?.v5_run_id);
  const freezeReceipt = trackerText(body?.freeze_receipt_sha256);
  const playerId = trackerText(body?.player_id);
  const threshold = trackerNumber(body?.threshold);

  if (!v5RunId || !/^[a-f0-9]{64}$/.test(v5RunId)) {
    return jsonResponse({ error: "Invalid v5_run_id." }, 400);
  }

  if (!freezeReceipt || !/^[a-f0-9]{64}$/.test(freezeReceipt)) {
    return jsonResponse(
      { error: "Invalid freeze_receipt_sha256." },
      400
    );
  }

  if (!playerId || !/^[A-Z0-9_-]{3,64}$/.test(playerId)) {
    return jsonResponse({ error: "Invalid player_id." }, 400);
  }

  if (!isNflReceptionHalfPoint(threshold)) {
    return jsonResponse(
      {
        error: "Invalid NFL reception threshold.",
        message: "Threshold must be an exact half-point from 0.5 through 19.5."
      },
      400
    );
  }

  const run = await env.BET_DB
    .prepare("SELECT * FROM model_runs WHERE id = ?1 LIMIT 1")
    .bind(modelRunId)
    .first();

  if (!run) {
    return jsonResponse({ error: "Tracker model run not found." }, 404);
  }

  if (
    normalizeText(run.sport) !== "nfl" ||
    normalizeText(run.league) !== "nfl" ||
    String(run.model_name || "") !== "NFL Receptions V5" ||
    String(run.model_status || "").toUpperCase() !== "FROZEN"
  ) {
    return jsonResponse(
      {
        error: "Tracker model run is not an eligible frozen NFL Receptions V5 run."
      },
      409
    );
  }

  const runNotes = String(run.notes || "");
  const boundToSourceRun =
    runNotes.includes(v5RunId) && runNotes.includes(freezeReceipt);

  if (!boundToSourceRun) {
    return jsonResponse(
      {
        error: "Tracker/source-run binding mismatch.",
        message:
          "The tracker run notes do not contain the supplied V5 run id and freeze receipt."
      },
      409
    );
  }

  const frozenPlayerUrl =
    `${NFL_V5_CONTROL_BASE}/v1/runs/${encodeURIComponent(v5RunId)}` +
    `/players/${encodeURIComponent(playerId)}`;

  let frozenResponse;
  try {
    frozenResponse = await fetch(frozenPlayerUrl, {
      method: "GET",
      headers: { Accept: "application/json" },
      signal: AbortSignal.timeout(12000)
    });
  } catch (error) {
    return jsonResponse(
      {
        error: "Frozen player verification unavailable.",
        message: error instanceof Error ? error.message : String(error)
      },
      502
    );
  }

  let frozenPayload;
  try {
    frozenPayload = await frozenResponse.json();
  } catch {
    return jsonResponse(
      { error: "Frozen player verification returned invalid JSON." },
      502
    );
  }

  if (!frozenResponse.ok) {
    return jsonResponse(
      {
        error: "Frozen player verification failed.",
        upstream_status: frozenResponse.status,
        details: frozenPayload
      },
      422
    );
  }

  if (frozenPayload?.freeze_receipt_sha256 !== freezeReceipt) {
    return jsonResponse(
      { error: "Freeze receipt mismatch during frozen selection verification." },
      409
    );
  }

  const player = frozenPayload?.player;

  if (!player || player.player_id !== playerId) {
    return jsonResponse(
      { error: "Frozen player identity mismatch." },
      422
    );
  }

  const ladderKey = nflReceptionLadderKey(threshold);
  const pModel = Number(player?.ladder?.[String(ladderKey)]);

  if (!(pModel > 0) || pModel > 1 || !Number.isFinite(pModel)) {
    return jsonResponse(
      {
        error: "Exact frozen ladder probability not found.",
        player_id: playerId,
        threshold,
        ladder_key: ladderKey
      },
      422
    );
  }

  const playerName = trackerText(player.player_name);
  const teamName = trackerText(player.team);

  if (!playerName) {
    return jsonResponse(
      { error: "Frozen player name is missing." },
      422
    );
  }

  const existing = await findExistingFrozenNflSelection(
    env,
    modelRunId,
    playerName,
    threshold
  );

  if (existing) {
    if (
      Math.abs(Number(existing.p_model) - pModel) >
      FROZEN_SELECTION_PROB_TOLERANCE
    ) {
      return jsonResponse(
        {
          error: "Existing tracker selection conflicts with frozen P_model.",
          model_selection_id: existing.id
        },
        409
      );
    }

    return jsonResponse({
      status: "existing",
      idempotent: true,
      model_run_id: modelRunId,
      model_selection_id: existing.id,
      v5_run_id: v5RunId,
      freeze_receipt_sha256: freezeReceipt,
      player_id: playerId,
      player_name: playerName,
      team_name: teamName,
      threshold,
      ladder_key: ladderKey,
      p_model: pModel,
      fair_odds: 1 / pModel
    });
  }

  const identity = [
    modelRunId,
    v5RunId,
    freezeReceipt,
    playerId,
    threshold.toFixed(1)
  ].join("|");

  const selectionHash = await trackerSha256Hex(identity);
  const selectionId = `sel_frozen_${selectionHash.slice(0, 32)}`;
  const createdAt = new Date().toISOString();
  const fairOdds = 1 / pModel;
  const selectionName = `${playerName} ${ladderKey}+ receptions`;
  const keyAssumptions = Array.isArray(player.key_assumptions)
    ? JSON.stringify(player.key_assumptions)
    : null;
  const notes = [
    "On-demand frozen selection registry.",
    `V5 run=${v5RunId}`,
    `freeze_receipt=${freezeReceipt}`,
    `player_id=${playerId}`,
    `Confidence=${String(player.confidence || "UNKNOWN")}`,
    `Fragility=${String(player.fragility || "UNKNOWN")}`
  ].join(" ");

  try {
    await env.BET_DB
      .prepare(`
        INSERT INTO model_selections (
          id,
          model_run_id,
          created_at,
          selection_name,
          player_name,
          team_name,
          market_family,
          market_key,
          side,
          threshold,
          p_model,
          fair_odds,
          confidence,
          market_price_at_integration,
          market_bookmaker_at_integration,
          p_market_at_integration,
          edge_at_integration,
          ranking_score,
          final_rank,
          final_play,
          key_assumptions,
          notes
        ) VALUES (
          ?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11,
          ?12, ?13, ?14, ?15, ?16, ?17, ?18, ?19, ?20, ?21, ?22
        )
      `)
      .bind(
        selectionId,
        modelRunId,
        createdAt,
        selectionName,
        playerName,
        teamName,
        "nfl_receptions",
        null,
        "Over",
        threshold,
        pModel,
        fairOdds,
        null,
        null,
        null,
        null,
        null,
        null,
        null,
        0,
        keyAssumptions,
        notes
      )
      .run();
  } catch (error) {
    // A concurrent identical ensure call can race the deterministic insert.
    // Resolve that race idempotently instead of creating a duplicate.
    const raced = await env.BET_DB
      .prepare("SELECT * FROM model_selections WHERE id = ?1 LIMIT 1")
      .bind(selectionId)
      .first();

    if (
      !raced ||
      raced.model_run_id !== modelRunId ||
      Math.abs(Number(raced.p_model) - pModel) >
        FROZEN_SELECTION_PROB_TOLERANCE
    ) {
      throw error;
    }

    return jsonResponse({
      status: "existing",
      idempotent: true,
      model_run_id: modelRunId,
      model_selection_id: raced.id,
      v5_run_id: v5RunId,
      freeze_receipt_sha256: freezeReceipt,
      player_id: playerId,
      player_name: playerName,
      team_name: teamName,
      threshold,
      ladder_key: ladderKey,
      p_model: pModel,
      fair_odds: fairOdds
    });
  }

  return jsonResponse(
    {
      status: "created",
      idempotent: false,
      model_run_id: modelRunId,
      model_selection_id: selectionId,
      v5_run_id: v5RunId,
      freeze_receipt_sha256: freezeReceipt,
      player_id: playerId,
      player_name: playerName,
      team_name: teamName,
      threshold,
      ladder_key: ladderKey,
      p_model: pModel,
      fair_odds: fairOdds
    },
    201
  );
}

async function findExistingFrozenNflSelection(
  env,
  modelRunId,
  playerName,
  threshold
) {
  return await env.BET_DB
    .prepare(`
      SELECT *
      FROM model_selections
      WHERE model_run_id = ?1
        AND lower(trim(market_family)) = 'nfl_receptions'
        AND lower(trim(player_name)) = lower(trim(?2))
        AND lower(trim(COALESCE(side, ''))) = 'over'
        AND ABS(threshold - ?3) < 0.000001
      ORDER BY created_at ASC
      LIMIT 1
    `)
    .bind(modelRunId, playerName, threshold)
    .first();
}

function isNflReceptionHalfPoint(value) {
  if (!Number.isFinite(value) || value < 0.5 || value > 19.5) {
    return false;
  }

  const doubled = value * 2;
  const nearest = Math.round(doubled);

  return (
    Math.abs(doubled - nearest) < 1e-9 &&
    Math.abs(nearest % 2) === 1
  );
}

function nflReceptionLadderKey(threshold) {
  const doubled = Math.round(threshold * 2);
  return (doubled + 1) / 2;
}

async function trackerSha256Hex(value) {
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(String(value))
  );

  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}
