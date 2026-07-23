-- Winner Tilt AI Database Schema v1.0 (PostgreSQL-compatible)

CREATE TABLE business_stages (
  stage_id VARCHAR(8) PRIMARY KEY,
  stage_code VARCHAR(3) UNIQUE NOT NULL CHECK (stage_code IN ('EMG','GRW','MAT')),
  stage_name TEXT UNIQUE NOT NULL
);

CREATE TABLE quality_tiers (
  quality_tier_id VARCHAR(8) PRIMARY KEY,
  tier_code VARCHAR(1) UNIQUE NOT NULL CHECK (tier_code IN ('S','A','B','C')),
  tier_name TEXT UNIQUE NOT NULL
);

CREATE TABLE companies (
  company_id VARCHAR(12) PRIMARY KEY,
  legal_name TEXT NOT NULL,
  common_name TEXT,
  country_code CHAR(2),
  stage_id VARCHAR(8) REFERENCES business_stages(stage_id),
  quality_tier_id VARCHAR(8) REFERENCES quality_tiers(quality_tier_id),
  valid_from DATE NOT NULL,
  valid_to DATE,
  CHECK (valid_to IS NULL OR valid_to >= valid_from)
);

CREATE TABLE securities (
  security_id VARCHAR(12) PRIMARY KEY,
  company_id VARCHAR(12) NOT NULL REFERENCES companies(company_id),
  ticker TEXT NOT NULL,
  exchange_code TEXT NOT NULL,
  security_type TEXT NOT NULL,
  currency CHAR(3) NOT NULL DEFAULT 'USD',
  is_adr BOOLEAN NOT NULL DEFAULT FALSE,
  active_from DATE NOT NULL,
  active_to DATE,
  UNIQUE(exchange_code, ticker, active_from)
);

CREATE TABLE themes (
  theme_id VARCHAR(12) PRIMARY KEY,
  theme_name TEXT NOT NULL,
  taxonomy_version TEXT NOT NULL,
  UNIQUE(theme_name, taxonomy_version)
);

CREATE TABLE economic_exposures (
  exposure_id VARCHAR(12) PRIMARY KEY,
  exposure_name TEXT NOT NULL,
  taxonomy_version TEXT NOT NULL,
  UNIQUE(exposure_name, taxonomy_version)
);

CREATE TABLE company_themes (
  company_id VARCHAR(12) REFERENCES companies(company_id),
  theme_id VARCHAR(12) REFERENCES themes(theme_id),
  theme_role TEXT NOT NULL CHECK (theme_role IN ('PRIMARY','SECONDARY')),
  valid_from DATE NOT NULL,
  valid_to DATE,
  PRIMARY KEY(company_id, theme_id, valid_from)
);

CREATE TABLE company_exposures (
  company_id VARCHAR(12) REFERENCES companies(company_id),
  exposure_id VARCHAR(12) REFERENCES economic_exposures(exposure_id),
  exposure_role TEXT NOT NULL CHECK (exposure_role IN ('PRIMARY','SECONDARY','HEDGE')),
  sensitivity TEXT NOT NULL CHECK (sensitivity IN ('LOW','MEDIUM','HIGH')),
  direction TEXT NOT NULL CHECK (direction IN ('POSITIVE','NEGATIVE','MIXED')),
  valid_from DATE NOT NULL,
  valid_to DATE,
  PRIMARY KEY(company_id, exposure_id, valid_from)
);

CREATE TABLE universe_versions (
  universe_version_id VARCHAR(16) PRIMARY KEY,
  version_name TEXT UNIQUE NOT NULL,
  effective_date DATE NOT NULL,
  frozen_at TIMESTAMPTZ NOT NULL,
  total_target INTEGER NOT NULL,
  core_target INTEGER NOT NULL,
  emerging_target INTEGER NOT NULL,
  methodology_version TEXT NOT NULL
);

CREATE TABLE universe_memberships (
  universe_version_id VARCHAR(16) REFERENCES universe_versions(universe_version_id),
  security_id VARCHAR(12) REFERENCES securities(security_id),
  pool_code TEXT NOT NULL CHECK (pool_code IN ('CORE','EMERGING')),
  membership_status TEXT NOT NULL CHECK (membership_status IN ('ACTIVE','SUSPENDED','REMOVED','CANDIDATE')),
  included_from DATE NOT NULL,
  included_to DATE,
  reason TEXT NOT NULL,
  PRIMARY KEY(universe_version_id, security_id, included_from)
);

CREATE TABLE eligibility_reviews (
  eligibility_review_id BIGSERIAL PRIMARY KEY,
  universe_version_id VARCHAR(16) REFERENCES universe_versions(universe_version_id),
  security_id VARCHAR(12) REFERENCES securities(security_id),
  review_date DATE NOT NULL,
  overall_status TEXT NOT NULL CHECK (overall_status IN ('PASS','FAIL','MANUAL_REVIEW')),
  market_cap_usd NUMERIC(22,2),
  adv_usd NUMERIC(22,2),
  trading_days INTEGER,
  listing_status TEXT,
  data_complete BOOLEAN,
  UNIQUE(universe_version_id, security_id, review_date)
);

CREATE TABLE data_sources (
  source_id VARCHAR(16) PRIMARY KEY,
  source_name TEXT NOT NULL,
  source_type TEXT NOT NULL,
  is_point_in_time BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE price_daily (
  security_id VARCHAR(12) REFERENCES securities(security_id),
  trading_date DATE NOT NULL,
  adjusted_close NUMERIC(20,6),
  volume NUMERIC(24,2),
  source_id VARCHAR(16) REFERENCES data_sources(source_id),
  available_at TIMESTAMPTZ NOT NULL,
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY(security_id, trading_date, source_id)
);

CREATE TABLE metric_definitions (
  metric_id VARCHAR(20) PRIMARY KEY,
  metric_name TEXT UNIQUE NOT NULL,
  category TEXT NOT NULL,
  unit TEXT,
  higher_is_better BOOLEAN,
  formula_text TEXT
);

CREATE TABLE metric_observations (
  metric_observation_id BIGSERIAL PRIMARY KEY,
  security_id VARCHAR(12) REFERENCES securities(security_id),
  metric_id VARCHAR(20) REFERENCES metric_definitions(metric_id),
  observation_date DATE NOT NULL,
  value_numeric NUMERIC(30,10),
  source_id VARCHAR(16) REFERENCES data_sources(source_id),
  available_at TIMESTAMPTZ NOT NULL,
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  revision_number INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE scoring_model_versions (
  scoring_model_version_id VARCHAR(20) PRIMARY KEY,
  model_name TEXT NOT NULL,
  version_name TEXT NOT NULL,
  effective_from DATE NOT NULL,
  frozen_at TIMESTAMPTZ NOT NULL,
  configuration_json JSONB NOT NULL,
  UNIQUE(model_name, version_name)
);

CREATE TABLE score_runs (
  score_run_id BIGSERIAL PRIMARY KEY,
  scoring_model_version_id VARCHAR(20) REFERENCES scoring_model_versions(scoring_model_version_id),
  universe_version_id VARCHAR(16) REFERENCES universe_versions(universe_version_id),
  as_of_date DATE NOT NULL,
  information_cutoff TIMESTAMPTZ NOT NULL,
  run_status TEXT NOT NULL CHECK (run_status IN ('STARTED','COMPLETED','FAILED')),
  UNIQUE(scoring_model_version_id, universe_version_id, as_of_date)
);

CREATE TABLE security_scores (
  score_run_id BIGINT REFERENCES score_runs(score_run_id),
  security_id VARCHAR(12) REFERENCES securities(security_id),
  total_score NUMERIC(8,4),
  eligible BOOLEAN NOT NULL,
  missing_data_flag BOOLEAN NOT NULL DEFAULT FALSE,
  penalty_score NUMERIC(8,4) NOT NULL DEFAULT 0,
  PRIMARY KEY(score_run_id, security_id)
);

CREATE TABLE rankings (
  score_run_id BIGINT REFERENCES score_runs(score_run_id),
  security_id VARCHAR(12) REFERENCES securities(security_id),
  overall_rank INTEGER,
  rank_status TEXT NOT NULL CHECK (rank_status IN ('PORTFOLIO','RESERVE','WATCH','INELIGIBLE')),
  PRIMARY KEY(score_run_id, security_id)
);

CREATE TABLE portfolio_snapshots (
  portfolio_snapshot_id BIGSERIAL PRIMARY KEY,
  snapshot_date DATE UNIQUE NOT NULL,
  policy_version TEXT NOT NULL,
  score_run_id BIGINT REFERENCES score_runs(score_run_id),
  cash_balance NUMERIC(22,2) NOT NULL DEFAULT 0,
  total_value NUMERIC(22,2)
);

CREATE TABLE portfolio_positions (
  portfolio_snapshot_id BIGINT REFERENCES portfolio_snapshots(portfolio_snapshot_id),
  security_id VARCHAR(12) REFERENCES securities(security_id),
  quantity NUMERIC(24,8) NOT NULL,
  market_value NUMERIC(22,2),
  portfolio_weight NUMERIC(12,8),
  cost_basis NUMERIC(22,2),
  PRIMARY KEY(portfolio_snapshot_id, security_id)
);

CREATE TABLE decision_log (
  decision_id BIGSERIAL PRIMARY KEY,
  decision_date DATE NOT NULL,
  decision_type TEXT NOT NULL,
  entity_type TEXT,
  entity_id TEXT,
  previous_value JSONB,
  new_value JSONB,
  rationale TEXT NOT NULL,
  evidence TEXT,
  version_reference TEXT
);


-- Milestone 3 consolidated additions
-- Winner Tilt AI — Milestone 3 scoring audit patch v1.0
-- PostgreSQL-compatible; additive migration against winner-tilt-schema-v1.0.



ALTER TABLE metric_definitions
  ADD COLUMN IF NOT EXISTS unit_code TEXT,
  ADD COLUMN IF NOT EXISTS default_weight NUMERIC(12,8),
  ADD COLUMN IF NOT EXISTS stage_module TEXT,
  ADD COLUMN IF NOT EXISTS minimum_history TEXT,
  ADD COLUMN IF NOT EXISTS mandatory_rule TEXT,
  ADD COLUMN IF NOT EXISTS active_from DATE NOT NULL DEFAULT DATE '2026-07-23',
  ADD COLUMN IF NOT EXISTS active_to DATE;

ALTER TABLE score_runs
  ADD COLUMN IF NOT EXISTS prototype_flag BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS input_fingerprint_sha256 CHAR(64),
  ADD COLUMN IF NOT EXISTS engine_version TEXT;

CREATE TABLE IF NOT EXISTS score_category_results (
  score_run_id BIGINT NOT NULL REFERENCES score_runs(score_run_id),
  security_id VARCHAR(12) NOT NULL REFERENCES securities(security_id),
  category TEXT NOT NULL CHECK (category IN ('GROWTH','QUALITY','FINANCIAL_STRENGTH','VALUATION','MOMENTUM','CAPITAL_ALLOCATION','RISK')),
  category_score NUMERIC(8,4),
  category_weight NUMERIC(12,8) NOT NULL,
  effective_metric_weight_coverage NUMERIC(12,8),
  valid_metric_count INTEGER NOT NULL DEFAULT 0,
  unavailable_metric_count INTEGER NOT NULL DEFAULT 0,
  not_applicable_metric_count INTEGER NOT NULL DEFAULT 0,
  flags JSONB NOT NULL DEFAULT '[]'::jsonb,
  PRIMARY KEY(score_run_id, security_id, category)
);

CREATE TABLE IF NOT EXISTS score_components (
  score_run_id BIGINT NOT NULL REFERENCES score_runs(score_run_id),
  security_id VARCHAR(12) NOT NULL REFERENCES securities(security_id),
  metric_id VARCHAR(20) NOT NULL REFERENCES metric_definitions(metric_id),
  metric_observation_id BIGINT REFERENCES metric_observations(metric_observation_id),
  raw_value NUMERIC(30,10),
  winsorized_value NUMERIC(30,10),
  universe_percentile NUMERIC(8,4),
  peer_percentile NUMERIC(8,4),
  normalized_score NUMERIC(8,4),
  base_metric_weight NUMERIC(12,8) NOT NULL,
  effective_metric_weight NUMERIC(12,8),
  comparison_group TEXT,
  missing_data_class TEXT NOT NULL CHECK (missing_data_class IN ('VALID','NOT_APPLICABLE','TEMPORARILY_UNAVAILABLE','STRUCTURALLY_UNSUPPORTED')),
  penalty_contribution NUMERIC(8,4) NOT NULL DEFAULT 0,
  flags JSONB NOT NULL DEFAULT '[]'::jsonb,
  PRIMARY KEY(score_run_id, security_id, metric_id)
);

CREATE TABLE IF NOT EXISTS score_run_flags (
  score_run_id BIGINT NOT NULL REFERENCES score_runs(score_run_id),
  security_id VARCHAR(12) NOT NULL REFERENCES securities(security_id),
  flag_code TEXT NOT NULL,
  severity TEXT NOT NULL CHECK (severity IN ('INFO','WARNING','ERROR','EXCLUDE')),
  details JSONB NOT NULL DEFAULT '{}'::jsonb,
  PRIMARY KEY(score_run_id, security_id, flag_code)
);

CREATE INDEX IF NOT EXISTS idx_metric_obs_pit
  ON metric_observations(security_id, metric_id, available_at DESC, observation_date DESC, revision_number DESC);
CREATE INDEX IF NOT EXISTS idx_score_components_metric
  ON score_components(score_run_id, metric_id, normalized_score DESC);
CREATE INDEX IF NOT EXISTS idx_security_scores_rank_input
  ON security_scores(score_run_id, eligible, total_score DESC);




CREATE TABLE IF NOT EXISTS business_model_modules (
  business_model_module_code TEXT PRIMARY KEY,
  module_name TEXT NOT NULL,
  production_supported BOOLEAN NOT NULL,
  rationale TEXT NOT NULL,
  effective_from DATE NOT NULL,
  effective_to DATE
);

CREATE TABLE IF NOT EXISTS company_business_model_modules (
  company_id VARCHAR(12) NOT NULL REFERENCES companies(company_id),
  business_model_module_code TEXT NOT NULL REFERENCES business_model_modules(business_model_module_code),
  valid_from DATE NOT NULL,
  valid_to DATE,
  rationale TEXT NOT NULL,
  PRIMARY KEY(company_id,business_model_module_code,valid_from)
);

ALTER TABLE metric_observations
  ADD COLUMN IF NOT EXISTS missing_data_class TEXT NOT NULL DEFAULT 'VALID'
    CHECK (missing_data_class IN ('VALID','NOT_APPLICABLE','TEMPORARILY_UNAVAILABLE','STRUCTURALLY_UNSUPPORTED')),
  ADD COLUMN IF NOT EXISTS stale_critical BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE security_scores
  ADD COLUMN IF NOT EXISTS pre_penalty_score NUMERIC(8,4),
  ADD COLUMN IF NOT EXISTS weighted_coverage NUMERIC(12,8),
  ADD COLUMN IF NOT EXISTS confidence_score NUMERIC(8,4),
  ADD COLUMN IF NOT EXISTS score_stability NUMERIC(8,4),
  ADD CONSTRAINT security_scores_total_range CHECK (total_score IS NULL OR total_score BETWEEN 0 AND 100),
  ADD CONSTRAINT security_scores_coverage_range CHECK (weighted_coverage IS NULL OR weighted_coverage BETWEEN 0 AND 1);
