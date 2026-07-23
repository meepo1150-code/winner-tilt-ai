-- Winner Tilt AI Portfolio / Backtest schema v1.0 (Milestone 4)
CREATE TABLE portfolio_config_version (
  portfolio_config_id text PRIMARY KEY,
  version text NOT NULL UNIQUE,
  status text NOT NULL CHECK (status IN ('DRAFT','FROZEN','RETIRED')),
  configuration_sha256 char(64) NOT NULL UNIQUE,
  configuration_json jsonb NOT NULL,
  frozen_at timestamptz
);
CREATE TABLE portfolio_run (
  portfolio_run_id bigserial PRIMARY KEY,
  as_of_date date NOT NULL,
  portfolio_config_id text NOT NULL REFERENCES portfolio_config_version,
  score_run_id bigint,
  previous_portfolio_run_id bigint REFERENCES portfolio_run,
  rebalance_executed boolean NOT NULL,
  source_scoring_configuration_sha256 char(64),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(as_of_date, portfolio_config_id)
);
CREATE TABLE portfolio_position_decision (
  portfolio_run_id bigint NOT NULL REFERENCES portfolio_run ON DELETE CASCADE,
  security_id text NOT NULL,
  bucket text NOT NULL CHECK (bucket IN ('HOLDING','RESERVE','EXIT')),
  bucket_rank integer,
  score numeric(12,6),
  target_weight numeric(12,10),
  decision text NOT NULL CHECK (decision IN ('BUY','HOLD','EXIT','WATCH')),
  reason text NOT NULL,
  primary_theme text,
  economic_exposure text,
  audit_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  PRIMARY KEY(portfolio_run_id, security_id, bucket),
  CHECK ((bucket='HOLDING' AND target_weight IS NOT NULL) OR bucket<>'HOLDING')
);
CREATE TABLE backtest_run (
  backtest_run_id bigserial PRIMARY KEY,
  interface_version text NOT NULL,
  validation_status text NOT NULL CHECK (validation_status IN ('PROTOTYPE_ONLY','PIT_VALIDATED')),
  start_date date NOT NULL,
  end_date date NOT NULL,
  initial_capital numeric(20,4) NOT NULL,
  commission_bps numeric(10,4) NOT NULL DEFAULT 0,
  slippage_bps numeric(10,4) NOT NULL DEFAULT 0,
  benchmark_security_id text,
  assumptions_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE backtest_equity_curve (
  backtest_run_id bigint NOT NULL REFERENCES backtest_run ON DELETE CASCADE,
  trading_date date NOT NULL,
  portfolio_value numeric(24,8) NOT NULL,
  benchmark_value numeric(24,8),
  PRIMARY KEY(backtest_run_id,trading_date)
);
CREATE TABLE backtest_metric (
  backtest_run_id bigint NOT NULL REFERENCES backtest_run ON DELETE CASCADE,
  metric_name text NOT NULL,
  metric_value numeric(24,10),
  PRIMARY KEY(backtest_run_id,metric_name)
);
