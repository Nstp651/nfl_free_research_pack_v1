import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";

const schemaFiles = [
  "schemas/ibkr-market-input.schema.json",
  "schemas/research-pack.schema.json"
];

for (const path of schemaFiles) {
  const schema = JSON.parse(readFileSync(new URL(`../${path}`, import.meta.url), "utf8"));
  assert.equal(schema.$schema, "https://json-schema.org/draft/2020-12/schema", `${path} must use JSON Schema 2020-12`);
  assert.equal(schema.type, "object", `${path} root must be an object`);
  assert.ok(schema.$id && schema.title && schema.properties, `${path} lacks required schema metadata`);
}

const migration = readFileSync(new URL("../migrations/0001_earnings_desk_v1.sql", import.meta.url), "utf8");
const auditSql = `${migration}\nSELECT
  (SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name LIKE 'earnings_%') || '|' ||
  (SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' AND name LIKE 'earnings_%') || '|' ||
  (SELECT COUNT(*) FROM sqlite_master WHERE type='view' AND name LIKE 'earnings_%');\n`;
const sqlite = spawnSync("sqlite3", [":memory:"], { input: auditSql, encoding: "utf8" });
assert.equal(sqlite.status, 0, sqlite.stderr || "SQLite schema validation failed");
assert.equal(sqlite.stdout.trim().split("\n").at(-1), "20|18|1", "unexpected Earnings Desk schema object counts");

console.log("schema validation PASS: 2 JSON schemas, 20 tables, 18 triggers, 1 view");
