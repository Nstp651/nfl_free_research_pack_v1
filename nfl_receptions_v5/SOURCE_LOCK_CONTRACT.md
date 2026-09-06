# Betting Platform V1 — Content-Addressed Source Lock

NFL Receptions V5 does not depend on GitHub's unauthenticated REST commit API at run time.

At run creation the control Worker loads the published raw `manifest.json` and the exact game pack, verifies fixture identity and matching `pack_revision`, then persists:

- `pack_revision` — deterministic research-pack revision published by the pack builder;
- `manifest_sha256` — SHA-256 of the exact manifest bytes loaded by the Worker;
- `pack_content_sha256` — SHA-256 of the exact game-pack bytes loaded by the Worker;
- `source_anchor_sha256` — SHA-256 over game_id + pack_revision + the two content hashes.

The research checkpoint must bind to `source_anchor_sha256`, `pack_revision`, and the complete retrieved-player count. A manifest/pack revision race is retried once and then rejected.

This is the Platform V1 default for future models: persist exact content identity rather than requiring an external source-control API to be available during a betting-model run.
