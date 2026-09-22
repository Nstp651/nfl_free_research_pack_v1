PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS earnings_schema_versions (
  version TEXT PRIMARY KEY,
  applied_at TEXT NOT NULL
) STRICT;

INSERT OR IGNORE INTO earnings_schema_versions(version, applied_at)
VALUES ('earnings_desk_schema_v1.1.0', datetime('now'));

CREATE TABLE IF NOT EXISTS earnings_model_versions (
  model_version TEXT PRIMARY KEY,
  model_kind TEXT NOT NULL CHECK (model_kind IN ('FEATURE_CONTRACT', 'P_MODEL', 'POST_EVENT_IV', 'VALUATION', 'SELECTION')),
  config_json TEXT NOT NULL CHECK (json_valid(config_json)),
  config_sha256 TEXT NOT NULL CHECK (length(config_sha256) = 64),
  created_at TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
) STRICT;

CREATE TABLE IF NOT EXISTS earnings_runs (
  run_id TEXT PRIMARY KEY,
  sydney_timestamp TEXT NOT NULL,
  sydney_local_date TEXT NOT NULL,
  us_trading_date TEXT NOT NULL,
  mode TEXT NOT NULL CHECK (mode IN ('SHADOW', 'LIVE')),
  status TEXT NOT NULL CHECK (status IN ('RUN_LOCKED', 'RESEARCH_IN_PROGRESS', 'PARTIALLY_FROZEN', 'FROZEN', 'VALUED', 'CLOSED')),
  model_version TEXT NOT NULL REFERENCES earnings_model_versions(model_version),
  research_cutoff TEXT NOT NULL,
  intended_exit_at TEXT NOT NULL,
  universe_sha256 TEXT NOT NULL CHECK (length(universe_sha256) = 64),
  max_core_positions INTEGER NOT NULL CHECK (max_core_positions BETWEEN 0 AND 20),
  max_daily_capital_usd REAL NOT NULL CHECK (max_daily_capital_usd > 0),
  operator_started_at TEXT NOT NULL,
  operator_minutes REAL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS earnings_events (
  event_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES earnings_runs(run_id),
  ticker TEXT NOT NULL,
  company_name TEXT NOT NULL,
  sector TEXT NOT NULL,
  market_cap_cohort TEXT NOT NULL,
  report_at TEXT NOT NULL,
  event_timing TEXT NOT NULL CHECK (event_timing IN ('AMC', 'BMO')),
  timing_source_url TEXT NOT NULL,
  timing_verified_at TEXT NOT NULL,
  timing_reliability TEXT NOT NULL CHECK (timing_reliability IN ('HIGH', 'MEDIUM')),
  intended_exit_at TEXT NOT NULL,
  realized_vol_20d REAL NOT NULL CHECK (realized_vol_20d > 0),
  pre_event_price REAL NOT NULL CHECK (pre_event_price > 0),
  liquid_us_listing INTEGER NOT NULL CHECK (liquid_us_listing IN (0, 1)),
  weekly_options_available INTEGER NOT NULL CHECK (weekly_options_available IN (0, 1)),
  eligible INTEGER NOT NULL CHECK (eligible IN (0, 1)),
  eligibility_reason TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE (run_id, ticker)
) STRICT;

CREATE TABLE IF NOT EXISTS earnings_research_packs (
  research_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES earnings_runs(run_id),
  event_id TEXT NOT NULL REFERENCES earnings_events(event_id),
  ticker TEXT NOT NULL,
  research_json TEXT NOT NULL CHECK (json_valid(research_json)),
  research_sha256 TEXT NOT NULL CHECK (length(research_sha256) = 64),
  evidence_quality TEXT NOT NULL CHECK (evidence_quality IN ('HIGH', 'MEDIUM', 'LOW')),
  feature_contract_version TEXT NOT NULL,
  submitted_at TEXT NOT NULL,
  UNIQUE (run_id, event_id)
) STRICT;

CREATE TABLE IF NOT EXISTS earnings_event_dispositions (
  disposition_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES earnings_runs(run_id),
  event_id TEXT NOT NULL UNIQUE REFERENCES earnings_events(event_id),
  disposition TEXT NOT NULL CHECK (disposition IN ('DATA_BLOCKED', 'PASS')),
  reason TEXT NOT NULL,
  created_at TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS earnings_history_batches (
  batch_id TEXT PRIMARY KEY,
  source_name TEXT NOT NULL,
  source_revision TEXT NOT NULL,
  source_url TEXT NOT NULL,
  as_of TEXT NOT NULL,
  manifest_json TEXT NOT NULL CHECK (json_valid(manifest_json)),
  manifest_sha256 TEXT NOT NULL CHECK (length(manifest_sha256) = 64),
  ingested_at TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS earnings_return_horizons (
  return_horizon_id TEXT PRIMARY KEY,
  methodology_version TEXT NOT NULL,
  timezone TEXT NOT NULL CHECK (timezone = 'America/New_York'),
  pre_event_price_method TEXT NOT NULL,
  exit_price_method TEXT NOT NULL,
  approved INTEGER NOT NULL CHECK (approved IN (0, 1)),
  created_at TEXT NOT NULL,
  UNIQUE (return_horizon_id, methodology_version)
) STRICT;

INSERT OR IGNORE INTO earnings_return_horizons
  (return_horizon_id, methodology_version, timezone, pre_event_price_method, exit_price_method, approved, created_at)
VALUES
  ('PRE_EVENT_CLOSE_TO_POST_EVENT_CLOSE_ET_V1', 'earn-return-horizon-v1.0.0', 'America/New_York',
   'Official regular-session close at 16:00 America/New_York immediately before the earnings release',
   'Official regular-session close at 16:00 America/New_York on the first regular session after the earnings release',
   1, datetime('now'));

CREATE TABLE IF NOT EXISTS earnings_historical_event_versions (
  historical_id TEXT PRIMARY KEY,
  batch_id TEXT NOT NULL REFERENCES earnings_history_batches(batch_id),
  ticker TEXT NOT NULL,
  event_date TEXT NOT NULL,
  event_version INTEGER NOT NULL CHECK (event_version >= 1),
  event_timing TEXT NOT NULL CHECK (event_timing IN ('AMC', 'BMO')),
  sector TEXT NOT NULL,
  market_cap_cohort TEXT NOT NULL,
  pre_event_price REAL NOT NULL CHECK (pre_event_price > 0),
  pre_event_price_timestamp TEXT NOT NULL,
  pre_event_price_source_url TEXT NOT NULL CHECK (pre_event_price_source_url LIKE 'https://%'),
  exit_price REAL NOT NULL CHECK (exit_price > 0),
  exit_price_timestamp TEXT NOT NULL,
  exit_price_source_url TEXT NOT NULL CHECK (exit_price_source_url LIKE 'https://%'),
  return_horizon_id TEXT NOT NULL,
  return_horizon_methodology_version TEXT NOT NULL,
  event_return REAL NOT NULL,
  absolute_return REAL NOT NULL CHECK (absolute_return >= 0),
  gap_open_return REAL,
  realized_vol_20d REAL CHECK (realized_vol_20d > 0),
  pre_event_drift REAL,
  reported_eps REAL,
  consensus_eps REAL,
  reported_revenue REAL,
  consensus_revenue REAL,
  guidance_change_z REAL,
  estimate_revision_z REAL,
  consensus_dispersion_z REAL,
  sector_return REAL,
  market_return REAL,
  peer_variables_json TEXT CHECK (peer_variables_json IS NULL OR json_valid(peer_variables_json)),
  option_history_json TEXT CHECK (option_history_json IS NULL OR json_valid(option_history_json)),
  record_sha256 TEXT NOT NULL CHECK (length(record_sha256) = 64),
  created_at TEXT NOT NULL,
  FOREIGN KEY (return_horizon_id, return_horizon_methodology_version)
    REFERENCES earnings_return_horizons(return_horizon_id, methodology_version),
  UNIQUE (ticker, event_date, event_version)
) STRICT;

CREATE VIEW IF NOT EXISTS earnings_historical_events_current AS
SELECT h.*
FROM earnings_historical_event_versions h
JOIN (
  SELECT ticker, event_date, MAX(event_version) AS event_version
  FROM earnings_historical_event_versions
  GROUP BY ticker, event_date
) latest
  ON latest.ticker = h.ticker
 AND latest.event_date = h.event_date
 AND latest.event_version = h.event_version;

CREATE TABLE IF NOT EXISTS earnings_freezes (
  freeze_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES earnings_runs(run_id),
  event_id TEXT NOT NULL REFERENCES earnings_events(event_id),
  ticker TEXT NOT NULL,
  model_version TEXT NOT NULL REFERENCES earnings_model_versions(model_version),
  research_id TEXT NOT NULL REFERENCES earnings_research_packs(research_id),
  research_sha256 TEXT NOT NULL CHECK (length(research_sha256) = 64),
  freeze_json TEXT NOT NULL CHECK (json_valid(freeze_json)),
  freeze_receipt_sha256 TEXT NOT NULL CHECK (length(freeze_receipt_sha256) = 64),
  frozen_at TEXT NOT NULL,
  p_model_status TEXT NOT NULL CHECK (p_model_status = 'FROZEN'),
  confidence TEXT NOT NULL CHECK (confidence IN ('HIGH', 'MEDIUM', 'LOW')),
  UNIQUE (run_id, event_id),
  UNIQUE (freeze_receipt_sha256)
) STRICT;

CREATE TABLE IF NOT EXISTS earnings_market_inputs (
  market_input_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES earnings_runs(run_id),
  event_id TEXT NOT NULL REFERENCES earnings_events(event_id),
  freeze_id TEXT NOT NULL REFERENCES earnings_freezes(freeze_id),
  ticker TEXT NOT NULL,
  source_type TEXT NOT NULL CHECK (source_type = 'IBKR_SCREENSHOT'),
  screenshot_sha256 TEXT NOT NULL CHECK (length(screenshot_sha256) = 64),
  captured_at TEXT NOT NULL,
  underlying_price REAL NOT NULL CHECK (underlying_price > 0),
  market_input_json TEXT NOT NULL CHECK (json_valid(market_input_json)),
  market_input_sha256 TEXT NOT NULL CHECK (length(market_input_sha256) = 64),
  created_at TEXT NOT NULL,
  UNIQUE (market_input_sha256)
) STRICT;

CREATE TABLE IF NOT EXISTS earnings_option_quotes (
  quote_id TEXT PRIMARY KEY,
  market_input_id TEXT NOT NULL REFERENCES earnings_market_inputs(market_input_id),
  contract_key TEXT NOT NULL,
  expiry TEXT NOT NULL,
  strike REAL NOT NULL CHECK (strike > 0),
  right_type TEXT NOT NULL CHECK (right_type IN ('CALL', 'PUT')),
  bid REAL NOT NULL CHECK (bid >= 0),
  ask REAL NOT NULL CHECK (ask > 0 AND ask >= bid),
  visible_iv REAL,
  visible_delta REAL,
  open_interest INTEGER,
  volume INTEGER,
  spread_fraction REAL NOT NULL CHECK (spread_fraction >= 0),
  UNIQUE (market_input_id, contract_key)
) STRICT;

CREATE TABLE IF NOT EXISTS earnings_post_event_iv_observations (
  iv_observation_id TEXT PRIMARY KEY,
  ticker TEXT NOT NULL,
  event_date TEXT NOT NULL,
  sector TEXT NOT NULL,
  market_cap_cohort TEXT NOT NULL,
  moneyness_bucket TEXT NOT NULL,
  dte_bucket TEXT NOT NULL,
  residual_iv REAL NOT NULL CHECK (residual_iv > 0),
  exit_spread_fraction REAL CHECK (exit_spread_fraction >= 0),
  source TEXT NOT NULL,
  source_revision TEXT NOT NULL,
  observation_sha256 TEXT NOT NULL CHECK (length(observation_sha256) = 64),
  created_at TEXT NOT NULL,
  UNIQUE (observation_sha256)
) STRICT;

CREATE TABLE IF NOT EXISTS earnings_valuation_batches (
  valuation_batch_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES earnings_runs(run_id),
  event_id TEXT NOT NULL REFERENCES earnings_events(event_id),
  freeze_id TEXT NOT NULL REFERENCES earnings_freezes(freeze_id),
  market_input_id TEXT NOT NULL REFERENCES earnings_market_inputs(market_input_id),
  valuation_version TEXT NOT NULL,
  selection_version TEXT NOT NULL,
  risk_config_json TEXT NOT NULL CHECK (json_valid(risk_config_json)),
  created_at TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS earnings_valuations (
  valuation_id TEXT PRIMARY KEY,
  valuation_batch_id TEXT NOT NULL REFERENCES earnings_valuation_batches(valuation_batch_id),
  candidate_id TEXT NOT NULL,
  desk TEXT NOT NULL CHECK (desk IN ('EARN-DIRECTION', 'EARN-MOVE')),
  trade_type TEXT NOT NULL CHECK (trade_type IN ('CALL', 'PUT', 'STRADDLE', 'STRANGLE')),
  valuation_json TEXT NOT NULL CHECK (json_valid(valuation_json)),
  entry_ask REAL NOT NULL CHECK (entry_ask > 0),
  max_entry REAL NOT NULL CHECK (max_entry >= 0),
  expected_exit_value REAL NOT NULL CHECK (expected_exit_value >= 0),
  p_profit REAL NOT NULL CHECK (p_profit BETWEEN 0 AND 1),
  expected_net_dollars REAL NOT NULL,
  ev_per_dollar_risk REAL NOT NULL,
  max_loss REAL NOT NULL CHECK (max_loss > 0),
  model_edge REAL NOT NULL,
  confidence TEXT NOT NULL CHECK (confidence IN ('HIGH', 'MEDIUM', 'LOW')),
  selection TEXT NOT NULL CHECK (selection IN ('CORE', 'WATCH', 'PASS')),
  rank INTEGER NOT NULL CHECK (rank >= 1),
  created_at TEXT NOT NULL,
  UNIQUE (valuation_batch_id, candidate_id)
) STRICT;

CREATE TABLE IF NOT EXISTS earnings_positions (
  position_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES earnings_runs(run_id),
  event_id TEXT NOT NULL REFERENCES earnings_events(event_id),
  valuation_id TEXT NOT NULL REFERENCES earnings_valuations(valuation_id),
  mode TEXT NOT NULL CHECK (mode IN ('SHADOW', 'LIVE')),
  status TEXT NOT NULL CHECK (status IN ('OPEN', 'CLOSED', 'CANCELLED')),
  quantity INTEGER NOT NULL CHECK (quantity >= 1),
  opened_at TEXT NOT NULL,
  entry_fill_total REAL NOT NULL CHECK (entry_fill_total > 0),
  entry_fees REAL NOT NULL CHECK (entry_fees >= 0),
  max_capital_at_risk REAL NOT NULL CHECK (max_capital_at_risk > 0),
  execution_notes TEXT,
  closed_at TEXT
) STRICT;

CREATE TABLE IF NOT EXISTS earnings_position_legs (
  position_leg_id TEXT PRIMARY KEY,
  position_id TEXT NOT NULL REFERENCES earnings_positions(position_id),
  contract_key TEXT NOT NULL,
  expiry TEXT NOT NULL,
  strike REAL NOT NULL,
  right_type TEXT NOT NULL CHECK (right_type IN ('CALL', 'PUT')),
  entry_fill REAL NOT NULL CHECK (entry_fill > 0),
  quantity INTEGER NOT NULL CHECK (quantity >= 1),
  UNIQUE (position_id, contract_key)
) STRICT;

CREATE TABLE IF NOT EXISTS earnings_settlements (
  settlement_id TEXT PRIMARY KEY,
  position_id TEXT NOT NULL REFERENCES earnings_positions(position_id),
  screenshot_sha256 TEXT NOT NULL CHECK (length(screenshot_sha256) = 64),
  captured_at TEXT NOT NULL,
  guidance_json TEXT NOT NULL CHECK (json_valid(guidance_json)),
  executable_bid_total REAL NOT NULL CHECK (executable_bid_total >= 0),
  actual_exit_fill_total REAL NOT NULL CHECK (actual_exit_fill_total >= 0),
  exit_fees REAL NOT NULL CHECK (exit_fees >= 0),
  slippage_dollars REAL NOT NULL,
  realized_pnl REAL NOT NULL,
  settled_at TEXT NOT NULL,
  UNIQUE (position_id)
) STRICT;

CREATE TABLE IF NOT EXISTS earnings_model_outcomes (
  outcome_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES earnings_runs(run_id),
  event_id TEXT NOT NULL REFERENCES earnings_events(event_id),
  freeze_id TEXT NOT NULL REFERENCES earnings_freezes(freeze_id),
  actual_underlying_return REAL NOT NULL,
  actual_absolute_move REAL NOT NULL CHECK (actual_absolute_move >= 0),
  actual_gap_open_return REAL,
  forecast_percentile REAL NOT NULL CHECK (forecast_percentile BETWEEN 0 AND 1),
  observed_post_event_iv REAL,
  recorded_at TEXT NOT NULL,
  UNIQUE (event_id)
) STRICT;

CREATE TABLE IF NOT EXISTS earnings_decision_records (
  decision_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES earnings_runs(run_id),
  event_id TEXT REFERENCES earnings_events(event_id),
  record_type TEXT NOT NULL,
  record_json TEXT NOT NULL CHECK (json_valid(record_json)),
  record_sha256 TEXT NOT NULL CHECK (length(record_sha256) = 64),
  created_at TEXT NOT NULL,
  UNIQUE (record_sha256)
) STRICT;

CREATE INDEX IF NOT EXISTS idx_earnings_events_run ON earnings_events(run_id, eligible, report_at);
CREATE INDEX IF NOT EXISTS idx_earnings_history_ticker_date ON earnings_historical_event_versions(ticker, event_date);
CREATE INDEX IF NOT EXISTS idx_earnings_history_cohort ON earnings_historical_event_versions(sector, market_cap_cohort, event_date);
CREATE INDEX IF NOT EXISTS idx_earnings_iv_ticker ON earnings_post_event_iv_observations(ticker, moneyness_bucket, dte_bucket, event_date);
CREATE INDEX IF NOT EXISTS idx_earnings_iv_cohort ON earnings_post_event_iv_observations(sector, market_cap_cohort, moneyness_bucket, dte_bucket, event_date);
CREATE INDEX IF NOT EXISTS idx_earnings_positions_status ON earnings_positions(status, opened_at);
CREATE INDEX IF NOT EXISTS idx_earnings_decisions_run ON earnings_decision_records(run_id, created_at);

CREATE TRIGGER IF NOT EXISTS earnings_events_no_update
BEFORE UPDATE ON earnings_events BEGIN SELECT RAISE(ABORT, 'earnings events are run-locked'); END;
CREATE TRIGGER IF NOT EXISTS earnings_events_no_delete
BEFORE DELETE ON earnings_events BEGIN SELECT RAISE(ABORT, 'earnings events are run-locked'); END;
CREATE TRIGGER IF NOT EXISTS earnings_research_no_update
BEFORE UPDATE ON earnings_research_packs BEGIN SELECT RAISE(ABORT, 'research packs are append-only'); END;
CREATE TRIGGER IF NOT EXISTS earnings_research_no_delete
BEFORE DELETE ON earnings_research_packs BEGIN SELECT RAISE(ABORT, 'research packs are append-only'); END;
CREATE TRIGGER IF NOT EXISTS earnings_dispositions_no_update
BEFORE UPDATE ON earnings_event_dispositions BEGIN SELECT RAISE(ABORT, 'event dispositions are append-only'); END;
CREATE TRIGGER IF NOT EXISTS earnings_dispositions_no_delete
BEFORE DELETE ON earnings_event_dispositions BEGIN SELECT RAISE(ABORT, 'event dispositions are append-only'); END;
CREATE TRIGGER IF NOT EXISTS earnings_history_no_update
BEFORE UPDATE ON earnings_historical_event_versions BEGIN SELECT RAISE(ABORT, 'historical event versions are append-only'); END;
CREATE TRIGGER IF NOT EXISTS earnings_history_no_delete
BEFORE DELETE ON earnings_historical_event_versions BEGIN SELECT RAISE(ABORT, 'historical event versions are append-only'); END;
CREATE TRIGGER IF NOT EXISTS earnings_horizons_no_update
BEFORE UPDATE ON earnings_return_horizons BEGIN SELECT RAISE(ABORT, 'return horizon definitions are immutable'); END;
CREATE TRIGGER IF NOT EXISTS earnings_horizons_no_delete
BEFORE DELETE ON earnings_return_horizons BEGIN SELECT RAISE(ABORT, 'return horizon definitions are immutable'); END;
CREATE TRIGGER IF NOT EXISTS earnings_freezes_no_update
BEFORE UPDATE ON earnings_freezes BEGIN SELECT RAISE(ABORT, 'frozen P_MODEL is immutable'); END;
CREATE TRIGGER IF NOT EXISTS earnings_freezes_no_delete
BEFORE DELETE ON earnings_freezes BEGIN SELECT RAISE(ABORT, 'frozen P_MODEL is immutable'); END;
CREATE TRIGGER IF NOT EXISTS earnings_market_inputs_no_update
BEFORE UPDATE ON earnings_market_inputs BEGIN SELECT RAISE(ABORT, 'market inputs are append-only'); END;
CREATE TRIGGER IF NOT EXISTS earnings_market_inputs_no_delete
BEFORE DELETE ON earnings_market_inputs BEGIN SELECT RAISE(ABORT, 'market inputs are append-only'); END;
CREATE TRIGGER IF NOT EXISTS earnings_decisions_no_update
BEFORE UPDATE ON earnings_decision_records BEGIN SELECT RAISE(ABORT, 'decision records are append-only'); END;
CREATE TRIGGER IF NOT EXISTS earnings_decisions_no_delete
BEFORE DELETE ON earnings_decision_records BEGIN SELECT RAISE(ABORT, 'decision records are append-only'); END;

CREATE TRIGGER IF NOT EXISTS earnings_run_identity_immutable
BEFORE UPDATE ON earnings_runs
WHEN OLD.run_id != NEW.run_id
  OR OLD.sydney_timestamp != NEW.sydney_timestamp
  OR OLD.us_trading_date != NEW.us_trading_date
  OR OLD.mode != NEW.mode
  OR OLD.model_version != NEW.model_version
  OR OLD.research_cutoff != NEW.research_cutoff
  OR OLD.intended_exit_at != NEW.intended_exit_at
  OR OLD.universe_sha256 != NEW.universe_sha256
BEGIN SELECT RAISE(ABORT, 'run-lock identity is immutable'); END;

CREATE TRIGGER IF NOT EXISTS earnings_run_status_forward_only
BEFORE UPDATE OF status ON earnings_runs
WHEN NEW.status != OLD.status AND NOT (
  (OLD.status = 'RUN_LOCKED' AND NEW.status IN ('RESEARCH_IN_PROGRESS', 'PARTIALLY_FROZEN', 'FROZEN')) OR
  (OLD.status = 'RESEARCH_IN_PROGRESS' AND NEW.status IN ('PARTIALLY_FROZEN', 'FROZEN')) OR
  (OLD.status = 'PARTIALLY_FROZEN' AND NEW.status = 'FROZEN') OR
  (OLD.status = 'FROZEN' AND NEW.status = 'VALUED') OR
  (OLD.status = 'VALUED' AND NEW.status = 'CLOSED')
)
BEGIN SELECT RAISE(ABORT, 'invalid earnings run state transition'); END;
